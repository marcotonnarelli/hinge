from __future__ import annotations

import os
import subprocess
from pathlib import Path

import duckdb
import pytest

from hinge.stages.projection.dbt_projection import DbtProjection
from hinge.stages.projection.specs.dev_interaction import SPEC as DEV_INTERACTION
from hinge.stages.projection.specs.follow_user_user import SPEC as FOLLOW_USER_USER
from hinge.stages.projection.specs.fork_repo_repo import SPEC as FORK_REPO_REPO
from hinge.stages.projection.specs.issue_co_participation import SPEC as ISSUE_CO_PARTICIPATION
from hinge.stages.projection.specs.issue_participation import SPEC as ISSUE_PARTICIPATION
from hinge.stages.projection.specs.pr_author_reviewer import SPEC as PR_AUTHOR_REVIEWER
from hinge.stages.projection.specs.pr_participation import SPEC as PR_PARTICIPATION
from hinge.stages.projection.specs.pr_reviewer_coreview import SPEC as PR_REVIEWER_COREVIEW
from hinge.stages.projection.specs.repo_shared_contributors import SPEC as REPO_SHARED_CONTRIBUTORS
from hinge.stages.projection.specs.star_user_repo import SPEC as STAR_USER_REPO
from hinge.stages.projection.specs.watch_user_repo import SPEC as WATCH_USER_REPO
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
    db_path = tmp_path / "projection.duckdb"
    view = _seed_fast_hin_store(db_path)

    handle = DbtProjection().run(DEV_INTERACTION, {}, view)

    edges = list(handle.iter_edges())
    assert {edge.type for edge in edges} == {"collaborates_with"}
    assert {(edge.src_id, edge.dst_id) for edge in edges} == {
        ("gh:user:1", "gh:user:2"),
        ("gh:user:1", "gh:user:3"),
        ("gh:user:2", "gh:user:3"),
    }
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        assert conn.execute("SELECT count(*) FROM int_user_artifact_incidence").fetchone()[0] > 0
        assert conn.execute("SELECT count(*) FROM int_developer_repo_affiliation").fetchone()[0] > 0
    finally:
        conn.close()


def test_dev_interaction_rejects_missing_adapter_capability(tmp_path):
    db_path = tmp_path / "projection.duckdb"
    view = _seed_fast_hin_store(db_path)
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE contract_adapter_manifest SET has_pr_reviews = false "
            "WHERE adapter_run_id = ?",
            [DATASET_ID],
        )
    finally:
        conn.close()

    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        DbtProjection().run(DEV_INTERACTION, {}, view)

    output = f"{exc_info.value.output}\n{exc_info.value.stderr}"
    assert "Missing capabilities: has_pr_reviews" in output


def test_follow_user_user_rejects_missing_adapter_capability(tmp_path):
    view = _seed_fast_hin_store(tmp_path / "projection.duckdb")

    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        DbtProjection().run(FOLLOW_USER_USER, {}, view)

    output = f"{exc_info.value.output}\n{exc_info.value.stderr}"
    assert "Missing capabilities: has_follows" in output


def test_fork_repo_repo_slices_native_fork_edges(tmp_path):
    view = _seed_fast_hin_store(tmp_path / "projection.duckdb")

    handle = DbtProjection().run(FORK_REPO_REPO, {}, view)

    edges = list(handle.iter_edges())
    assert len(edges) == 1
    assert edges[0].type == "fork_of"
    assert edges[0].src_id == "gh:repo:11"
    assert edges[0].dst_id == "gh:repo:10"
    assert edges[0].attrs["recipe_name"] == "fork_repo_repo"
    assert edges[0].attrs["directed"] is True


def test_issue_co_participation_projects_users_over_shared_issues(tmp_path):
    view = _seed_fast_hin_store(tmp_path / "projection.duckdb")

    handle = DbtProjection().run(ISSUE_CO_PARTICIPATION, {}, view)

    edges = list(handle.iter_edges())
    assert len(edges) == 1
    assert edges[0].type == "co_participates_issue"
    assert edges[0].src_id == "gh:user:1"
    assert edges[0].dst_id == "gh:user:3"
    assert edges[0].attrs["shared_issues"] == 1
    assert edges[0].attrs["issues"] == ["gh:artifact:issue:200"]


def test_issue_participation_emits_user_issue_roles(tmp_path):
    view = _seed_fast_hin_store(tmp_path / "projection.duckdb")

    handle = DbtProjection().run(ISSUE_PARTICIPATION, {}, view)

    by_pair = {(edge.src_id, edge.dst_id): edge for edge in handle.iter_edges()}
    assert set(by_pair) == {
        ("gh:user:1", "gh:artifact:issue:200"),
        ("gh:user:1", "gh:artifact:issue:201"),
        ("gh:user:3", "gh:artifact:issue:200"),
    }
    assert by_pair[("gh:user:1", "gh:artifact:issue:200")].attrs["roles"] == ["commented_on"]
    assert by_pair[("gh:user:1", "gh:artifact:issue:201")].attrs["roles"] == ["opened"]
    assert set(by_pair[("gh:user:3", "gh:artifact:issue:200")].attrs["roles"]) == {
        "opened",
        "closed",
    }


def test_pr_author_reviewer_connects_pr_openers_to_reviewers(tmp_path):
    view = _seed_fast_hin_store(tmp_path / "projection.duckdb")

    handle = DbtProjection().run(PR_AUTHOR_REVIEWER, {}, view)

    by_pair = {(edge.src_id, edge.dst_id): edge for edge in handle.iter_edges()}
    assert set(by_pair) == {("gh:user:1", "gh:user:2"), ("gh:user:1", "gh:user:3")}
    assert by_pair[("gh:user:1", "gh:user:2")].type == "reviewed_pr_from"
    assert by_pair[("gh:user:1", "gh:user:2")].attrs["pull_requests"] == [
        "gh:artifact:pull_request:100"
    ]
    assert by_pair[("gh:user:1", "gh:user:3")].attrs["directed"] is True


def test_pr_participation_emits_user_pull_request_roles(tmp_path):
    view = _seed_fast_hin_store(tmp_path / "projection.duckdb")

    handle = DbtProjection().run(PR_PARTICIPATION, {}, view)

    by_user = {edge.src_id: edge for edge in handle.iter_edges()}
    assert set(by_user) == {"gh:user:1", "gh:user:2", "gh:user:3"}
    assert by_user["gh:user:1"].dst_id == "gh:artifact:pull_request:100"
    assert by_user["gh:user:1"].attrs["roles"] == ["opened"]
    assert "reviewed" in by_user["gh:user:2"].attrs["roles"]
    assert "commented_on" in by_user["gh:user:3"].attrs["roles"]
    assert "reviewed" in by_user["gh:user:3"].attrs["roles"]


def test_pr_reviewer_coreview_projects_reviewers_over_shared_prs(tmp_path):
    view = _seed_fast_hin_store(tmp_path / "projection.duckdb")

    handle = DbtProjection().run(PR_REVIEWER_COREVIEW, {}, view)

    edges = list(handle.iter_edges())
    assert len(edges) == 1
    assert edges[0].type == "co_reviewed_pr"
    assert edges[0].src_id == "gh:user:2"
    assert edges[0].dst_id == "gh:user:3"
    assert edges[0].attrs["shared_pull_requests"] == 1
    assert edges[0].attrs["pull_requests"] == ["gh:artifact:pull_request:100"]


def test_repo_shared_contributors_projects_developer_repo_affiliation(tmp_path):
    view = _seed_fast_hin_store(tmp_path / "projection.duckdb")

    handle = DbtProjection().run(REPO_SHARED_CONTRIBUTORS, {}, view)

    edges = list(handle.iter_edges())
    assert len(edges) == 1
    assert edges[0].type == "shared_contributors"
    assert edges[0].src_id == "gh:repo:10"
    assert edges[0].dst_id == "gh:repo:20"
    assert edges[0].attrs["shared_contributors"] == 1
    assert edges[0].attrs["contributors"] == ["gh:user:1"]


def test_star_user_repo_slices_native_star_edges(tmp_path):
    view = _seed_fast_hin_store(tmp_path / "projection.duckdb")

    handle = DbtProjection().run(STAR_USER_REPO, {}, view)

    edges = list(handle.iter_edges())
    assert len(edges) == 1
    assert edges[0].type == "starred"
    assert edges[0].src_id == "gh:user:4"
    assert edges[0].dst_id == "gh:repo:10"
    assert edges[0].attrs["recipe_name"] == "star_user_repo"
    assert edges[0].attrs["weight_kind"] == "binary"


def test_watch_user_repo_rejects_missing_adapter_capability(tmp_path):
    view = _seed_fast_hin_store(tmp_path / "projection.duckdb")

    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        DbtProjection().run(WATCH_USER_REPO, {}, view)

    output = f"{exc_info.value.output}\n{exc_info.value.stderr}"
    assert "Missing capabilities: has_watches" in output


def test_typed_hin_models_materialize_from_active_contract_sources(tmp_path):
    db_path = tmp_path / "projection.duckdb"
    _seed_fast_hin_store(db_path)

    _run_dbt_models(db_path, "+hin_edges", "+hin_capabilities")

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        account_types = dict(
            conn.execute(
                "SELECT account_type, count(*) FROM hin_accounts GROUP BY account_type"
            ).fetchall()
        )
        assert account_types["human"] == 5
        assert account_types["organization"] == 1
        assert conn.execute("SELECT count(*) FROM hin_repositories").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM hin_artifacts").fetchone()[0] > 0
        assert conn.execute("SELECT count(*) FROM hin_nodes").fetchone()[0] == 19
        assert conn.execute("SELECT count(*) FROM hin_edges").fetchone()[0] == 30
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
        assert capabilities["has_commits"] is False
        assert capabilities["has_line_touches"] is False
    finally:
        conn.close()

    with DuckDBStore(path=db_path) as store:
        store.scope_to_dataset(DATASET_ID)
        assert store._c().execute("SELECT count(*) FROM active_hin_nodes").fetchone()[0] == 19
