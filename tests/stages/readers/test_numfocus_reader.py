from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from hinge.kernel.protocols.reader_stage import BulkIngestReader
from hinge.stages.readers.numfocus_reader import NumFocusReader
from hinge.stages.store.duckdb_store import DuckDBStore

FIXTURE = Path(__file__).parents[2] / "fixtures" / "numfocus_hin_synthetic.jsonl"


def _did() -> str:
    return uuid.uuid4().hex


def test_satisfies_bulk_ingest_protocol() -> None:
    assert isinstance(NumFocusReader(FIXTURE), BulkIngestReader)


def test_describe_reports_numfocus_hin_dataset() -> None:
    desc = NumFocusReader(FIXTURE).describe()
    assert desc.dataset == "numfocus-hin"
    assert desc.format == "jsonl"
    assert desc.byte_size > 0


def test_bulk_ingest_populates_contract_and_graph_tables(tmp_path: Path) -> None:
    did = _did()
    reader = NumFocusReader(FIXTURE)
    with DuckDBStore(path=tmp_path / "s.duckdb") as store:
        store.begin_dataset(did, reader=reader.describe().dataset, path=str(FIXTURE))
        records, nodes, edges = reader.bulk_ingest(store, did)
        store.finalise_dataset(did, nodes, edges)

        assert records == 14
        assert nodes > 0
        assert edges > 0

        contract_counts = (
            store._c()
            .execute(
                """
            SELECT
              (SELECT count(*) FROM contract_accounts WHERE dataset_id = ?),
              (SELECT count(*) FROM contract_repositories WHERE dataset_id = ?),
              (SELECT count(*) FROM contract_artifacts WHERE dataset_id = ?),
              (SELECT count(*) FROM contract_relations WHERE dataset_id = ?)
            """,
                [did, did, did, did],
            )
            .fetchone()
        )
        assert contract_counts is not None
        assert all(count > 0 for count in contract_counts)


def test_unknown_extension_raises(tmp_path: Path) -> None:
    f = tmp_path / "data.xyz"
    f.write_bytes(b"")
    with pytest.raises(ValueError, match="Cannot infer format"):
        NumFocusReader(f)
