from __future__ import annotations

import os
import subprocess
from pathlib import Path

from hinge.stages.projection.dbt_projection import DbtProjection
from hinge.stages.projection.specs.dev_interaction import SPEC as DEV_INTERACTION
from hinge.stages.projection.specs.top_authors_by_closures import SPEC as TOP_AUTHORS
from hinge.stages.store.duckdb_store import DuckDBStore

FIXTURE = Path("tests/fixtures/numfocus_hin_synthetic.jsonl")
DATASET_ID = "0123456789abcdef0123456789abcdef"
DBT_PROJECT_DIR = Path("hinge/dbt")


def _seed_fast_hin_store(path: Path):
    store = DuckDBStore(path=path)
    with store:
        store.begin_dataset(DATASET_ID, "numfocus-hin", str(FIXTURE))
        _, node_count, edge_count = store.ingest_numfocus_contracts(DATASET_ID, FIXTURE)
        store.finalise_dataset(DATASET_ID, node_count, edge_count)
        return store.scope_to_dataset(DATASET_ID)


def _run_dbt_models(db_path: Path, *models: str) -> None:
    env = os.environ.copy()
    env["HINGE_STORE_PATH"] = str(db_path)
    env["DBT_PROFILES_DIR"] = str(DBT_PROJECT_DIR)
    subprocess.run(
        [
            "dbt",
            "run",
            "--project-dir",
            str(DBT_PROJECT_DIR),
            "--profiles-dir",
            str(DBT_PROJECT_DIR),
            "--select",
            *models,
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_dev_interaction_reads_canonical_hin_views(tmp_path):
    view = _seed_fast_hin_store(tmp_path / "projection.duckdb")

    handle = DbtProjection().run(DEV_INTERACTION, {}, view)

    edges = list(handle.iter_edges())
    assert {edge.type for edge in edges} == {"collaborates_with"}
    assert {(edge.src_id, edge.dst_id) for edge in edges} == {
        ("gh:user:1", "gh:user:2"),
        ("gh:user:1", "gh:user:3"),
        ("gh:user:2", "gh:user:3"),
    }


def test_top_authors_by_closures_reads_canonical_hin_views(tmp_path):
    view = _seed_fast_hin_store(tmp_path / "projection.duckdb")

    handle = DbtProjection().run(TOP_AUTHORS, {}, view)

    edges = list(handle.iter_edges())
    assert len(edges) == 1
    assert edges[0].type == "top_author"
    assert edges[0].src_id == "gh:user:3"
    assert edges[0].dst_id == "gh:user:3"
    assert edges[0].attrs == {"rank": 1, "closed_repos": 1}


def test_typed_hin_models_materialize_from_active_contract_sources(tmp_path):
    db_path = tmp_path / "projection.duckdb"
    _seed_fast_hin_store(db_path)

    _run_dbt_models(
        db_path,
        "hin_accounts",
        "hin_repositories",
        "hin_artifacts",
        "hin_capabilities",
        "hin_nodes",
        "hin_edges",
    )

    import duckdb

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        account_types = dict(
            conn.execute(
                "SELECT account_type, count(*) FROM hin_accounts GROUP BY account_type"
            ).fetchall()
        )
        assert account_types["human"] == 5
        assert account_types["organization"] == 1
        assert conn.execute("SELECT count(*) FROM hin_repositories").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM hin_artifacts").fetchone()[0] > 0
        assert conn.execute("SELECT count(*) FROM hin_nodes").fetchone()[0] == 16
        assert conn.execute("SELECT count(*) FROM hin_edges").fetchone()[0] == 25
        edge_types = {
            row[0]
            for row in conn.execute("SELECT edge_type FROM hin_edges").fetchall()
        }
        assert {"opened", "reviewed", "contains", "fork_of"}.issubset(edge_types)
        capabilities = dict(
            conn.execute(
                "SELECT capability, is_available FROM hin_capabilities"
            ).fetchall()
        )
        assert capabilities["has_pull_requests"] is True
        assert capabilities["has_line_touches"] is False
    finally:
        conn.close()

    with DuckDBStore(path=db_path) as store:
        store.scope_to_dataset(DATASET_ID)
        assert store._c().execute("SELECT count(*) FROM active_hin_nodes").fetchone()[0] == 16
