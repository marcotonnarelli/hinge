from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from hinge.kernel import runner
from hinge.kernel.protocols.reader_stage import ReaderDescriptor
from hinge.kernel.schema import HINSchema, SchemaViolation, TypedEdge, TypedNode
from hinge.stages.store.duckdb_store import DuckDBStore


class _FakeReader:
    def __init__(self, elements: list[TypedNode | TypedEdge | SchemaViolation]) -> None:
        self._elements = elements

    def iter_elements(self) -> Iterator[TypedNode | TypedEdge | SchemaViolation]:
        yield from self._elements

    def describe(self) -> ReaderDescriptor:
        return ReaderDescriptor(dataset="fake", format="jsonl", path=Path("fake"), byte_size=0)


class _ExplodingReader(_FakeReader):
    def iter_elements(self) -> Iterator[TypedNode | TypedEdge | SchemaViolation]:
        yield self._elements[0]
        raise RuntimeError("boom")


_SCHEMA = HINSchema(schema_version=1, node_types={"user"}, edge_types={"opened"})


def test_ingest_success_persists_dataset(tmp_path: Path) -> None:
    reader = _FakeReader(
        [
            TypedNode(type="user", id="user:alice"),
            TypedEdge(type="opened", src_id="user:alice", dst_id="user:bob"),
        ]
    )
    with DuckDBStore(path=tmp_path / "s.duckdb") as store:
        report = runner.run_ingest(reader, store, _SCHEMA)
        assert report.nodes_upserted == 1
        assert report.edges_upserted == 1
        assert store.list_datasets()[0].dataset_id == report.dataset_id


def test_ingest_failure_discards_dataset(tmp_path: Path) -> None:
    """Transactional: a mid-ingest exception leaves no half-written dataset."""
    reader = _ExplodingReader([TypedNode(type="user", id="user:alice")])
    with DuckDBStore(path=tmp_path / "s.duckdb") as store:
        with pytest.raises(RuntimeError, match="boom"):
            runner.run_ingest(reader, store, _SCHEMA)
        assert store.list_datasets() == []


def test_ingest_counts_violations_for_unknown_labels(tmp_path: Path) -> None:
    reader = _FakeReader(
        [
            TypedNode(type="user", id="user:alice"),
            TypedNode(type="alien", id="?:bad"),
            TypedEdge(type="ghosted", src_id="user:alice", dst_id="user:bob"),
        ]
    )
    with DuckDBStore(path=tmp_path / "s.duckdb") as store:
        report = runner.run_ingest(reader, store, _SCHEMA)
    assert report.nodes_upserted == 1
    assert report.edges_upserted == 0
    assert report.violation_count == 2
