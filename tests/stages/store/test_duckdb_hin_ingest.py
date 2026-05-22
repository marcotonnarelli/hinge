from __future__ import annotations

import uuid
from pathlib import Path

from hinge.stages.store.duckdb_store import DuckDBStore

FIXTURE = Path(__file__).parents[2] / "fixtures" / "numfocus_hin_synthetic.jsonl"


def _did() -> str:
    return uuid.uuid4().hex


def test_fast_numfocus_ingest_populates_contract_and_hin_views(tmp_path: Path) -> None:
    did = _did()
    with DuckDBStore(path=tmp_path / "s.duckdb") as store:
        store.begin_dataset(did, reader="numfocus-hin", path=str(FIXTURE))
        records, nodes, edges = store.ingest_numfocus_contracts(did, FIXTURE)
        store.finalise_dataset(did, nodes, edges)

        assert records == 13
        assert nodes > 0
        assert edges > 0

        contract_counts = store._c().execute(
            """
            SELECT
              (SELECT count(*) FROM contract_accounts WHERE dataset_id = ?),
              (SELECT count(*) FROM contract_repositories WHERE dataset_id = ?),
              (SELECT count(*) FROM contract_artifacts WHERE dataset_id = ?),
              (SELECT count(*) FROM contract_relations WHERE dataset_id = ?)
            """,
            [did, did, did, did],
        ).fetchone()
        assert contract_counts is not None
        assert all(count > 0 for count in contract_counts)

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
        store.begin_dataset(did, reader="numfocus-hin", path=str(FIXTURE))
        _, nodes, edges = store.ingest_numfocus_contracts(did, FIXTURE)
        store.finalise_dataset(did, nodes, edges)
        store.scope_to_dataset(did)

        assert store._c().execute("SELECT count(*) FROM active_hin_nodes").fetchone()[0] == nodes
        assert store._c().execute("SELECT count(*) FROM active_hin_edges").fetchone()[0] == edges
        assert store._c().execute("SELECT count(*) FROM active_contract_accounts").fetchone()[0] > 0
        assert store._c().execute("SELECT count(*) FROM active_contract_repositories").fetchone()[0] > 0
        assert store._c().execute("SELECT count(*) FROM active_contract_artifacts").fetchone()[0] > 0
        assert store._c().execute("SELECT count(*) FROM active_contract_relations").fetchone()[0] > 0
        assert (
            store._c().execute("SELECT count(*) FROM active_contract_adapter_manifest").fetchone()[0]
            == 1
        )
