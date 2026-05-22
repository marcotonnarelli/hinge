from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from hinge.kernel.schema import TypedEdge, TypedNode
from hinge.stages.store.duckdb_store import DuckDBStore, SchemaMismatchError


def _did() -> str:
    return uuid.uuid4().hex


def test_store_requires_context_manager(tmp_path: Path) -> None:
    store = DuckDBStore(path=tmp_path / "s.duckdb")
    with pytest.raises(RuntimeError, match="context manager"):
        store.list_datasets()


def test_round_trip_within_one_dataset(tmp_path: Path) -> None:
    did = _did()
    with DuckDBStore(path=tmp_path / "s.duckdb") as store:
        store.begin_dataset(did, reader="x", path="x.jsonl")
        store.upsert(
            did,
            [TypedNode(type="user", id="user:alice")],
            [TypedEdge(type="opened", src_id="user:alice", dst_id="repo:r")],
        )
        store.finalise_dataset(did, 1, 1)
        census = store.census(did)
        assert census.nodes_by_type == {"user": 1}
        assert census.edges_by_type == {"opened": 1}


def test_fingerprint_is_dataset_scoped(tmp_path: Path) -> None:
    """Fingerprint of dataset A must not change when an unrelated dataset B is added."""
    a, b = _did(), _did()
    path = tmp_path / "s.duckdb"
    with DuckDBStore(path=path) as store:
        store.begin_dataset(a, reader="x", path="a")
        store.upsert(a, [TypedNode(type="user", id="user:alice")], [])
        store.finalise_dataset(a, 1, 0)
        fp_a_before = store.fingerprint(a).content_hash

        store.begin_dataset(b, reader="x", path="b")
        store.upsert(b, [TypedNode(type="user", id="user:zelda")], [])
        store.finalise_dataset(b, 1, 0)
        fp_a_after = store.fingerprint(a).content_hash

    assert fp_a_before == fp_a_after


def test_discard_dataset_removes_all_traces(tmp_path: Path) -> None:
    did = _did()
    with DuckDBStore(path=tmp_path / "s.duckdb") as store:
        store.begin_dataset(did, reader="x", path="x")
        store.upsert(did, [TypedNode(type="user", id="u:1")], [])
        store.discard_dataset(did)
        assert store.list_datasets() == []
        assert store.census(did).nodes_by_type == {}


def test_scope_to_dataset_creates_views(tmp_path: Path) -> None:
    import duckdb

    did = _did()
    path = tmp_path / "s.duckdb"
    with DuckDBStore(path=path) as store:
        store.begin_dataset(did, reader="x", path="x")
        store.upsert(did, [TypedNode(type="user", id="user:alice")], [])
        view = store.scope_to_dataset(did)
        assert view.dataset_id == did
        assert view.nodes_view == "active_nodes"

    # Verify views persist after store closes (so dbt subprocess can read them).
    conn = duckdb.connect(str(path), read_only=True)
    try:
        rows = conn.execute("SELECT id FROM active_nodes").fetchall()
    finally:
        conn.close()
    assert rows == [("user:alice",)]


def test_storage_version_mismatch_is_loud(tmp_path: Path) -> None:
    path = tmp_path / "s.duckdb"
    with DuckDBStore(path=path) as store:
        store.list_datasets()  # creates schema

    # Tamper with the recorded version.
    import duckdb

    c = duckdb.connect(str(path))
    c.execute("UPDATE meta SET value = '999' WHERE key = 'storage_version'")
    c.close()

    with pytest.raises(SchemaMismatchError), DuckDBStore(path=path):
        pass


def test_rejects_non_uuid_dataset_id(tmp_path: Path) -> None:
    with (
        DuckDBStore(path=tmp_path / "s.duckdb") as store,
        pytest.raises(ValueError, match="UUID hex"),
    ):
        store.begin_dataset("not-a-uuid", reader="x", path="x")
