from __future__ import annotations

from pathlib import Path

from hinge.stages.projection.dbt_projection import DbtProjection
from hinge.stages.projection.specs.dev_interaction import SPEC as DEV_INTERACTION
from hinge.stages.projection.specs.top_authors_by_closures import SPEC as TOP_AUTHORS
from hinge.stages.store.duckdb_store import DuckDBStore

FIXTURE = Path("tests/fixtures/numfocus_hin_synthetic.jsonl")
DATASET_ID = "0123456789abcdef0123456789abcdef"


def _seed_fast_hin_store(path: Path):
    store = DuckDBStore(path=path)
    with store:
        store.begin_dataset(DATASET_ID, "numfocus-hin", str(FIXTURE))
        _, node_count, edge_count = store.ingest_numfocus_contracts(DATASET_ID, FIXTURE)
        store.finalise_dataset(DATASET_ID, node_count, edge_count)
        return store.scope_to_dataset(DATASET_ID)


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
