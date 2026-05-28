from __future__ import annotations

import uuid
from pathlib import Path

from hinge.stages.readers.numfocus_reader import NumFocusReader
from hinge.stages.store.duckdb_store import DuckDBStore

FIXTURE = Path(__file__).parents[2] / "fixtures" / "numfocus_hin_synthetic.jsonl"


def _did() -> str:
    return uuid.uuid4().hex


def _bulk_ingest(store: DuckDBStore, did: str) -> tuple[int, int, int]:
    reader = NumFocusReader(FIXTURE)
    store.begin_dataset(did, reader=reader.describe().dataset, path=str(FIXTURE))
    records, nodes, edges = reader.bulk_ingest(store, did)
    store.finalise_dataset(did, nodes, edges)
    return records, nodes, edges


def test_numfocus_bulk_ingest_populates_hin_views(tmp_path: Path) -> None:
    did = _did()
    with DuckDBStore(path=tmp_path / "s.duckdb") as store:
        records, nodes, edges = _bulk_ingest(store, did)

        assert records == 14
        assert nodes > 0
        assert edges > 0

        hin_node_types = dict(
            store._c()
            .execute(
                "SELECT node_type, count(*) FROM _store_hin_nodes WHERE dataset_id = ? GROUP BY node_type",
                [did],
            )
            .fetchall()
        )
        assert {"user", "repo", "artifact"}.issubset(hin_node_types)

        hin_edge_types = {
            row[0]
            for row in store._c()
            .execute("SELECT edge_type FROM _store_hin_edges WHERE dataset_id = ?", [did])
            .fetchall()
        }
        assert {"opened", "reviewed", "commented_on", "contains", "starred", "fork_of"}.issubset(
            hin_edge_types
        )


def test_scope_to_dataset_exposes_active_hin_views(tmp_path: Path) -> None:
    did = _did()
    with DuckDBStore(path=tmp_path / "s.duckdb") as store:
        _, nodes, edges = _bulk_ingest(store, did)
        store.scope_to_dataset(did)

        assert store._c().execute("SELECT count(*) FROM active_hin_nodes").fetchone()[0] == nodes
        assert store._c().execute("SELECT count(*) FROM active_hin_edges").fetchone()[0] == edges
        assert store._c().execute("SELECT count(*) FROM active_contract_accounts").fetchone()[0] > 0
        assert (
            store._c().execute("SELECT count(*) FROM active_contract_repositories").fetchone()[0]
            > 0
        )
        assert (
            store._c().execute("SELECT count(*) FROM active_contract_artifacts").fetchone()[0] > 0
        )
        assert (
            store._c().execute("SELECT count(*) FROM active_contract_relations").fetchone()[0] > 0
        )
        assert (
            store._c()
            .execute("SELECT count(*) FROM active_contract_adapter_manifest")
            .fetchone()[0]
            == 1
        )
