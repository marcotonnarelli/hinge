from __future__ import annotations

from pathlib import Path

from hinge.frontends import lib

FIXTURE = Path(__file__).parents[1] / "fixtures" / "numfocus_hin_synthetic.jsonl"


def test_numfocus_ingest_uses_duckdb_contract_adapter_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("HINGE_STORE_PATH", str(tmp_path / "store.duckdb"))

    report = lib.ingest(FIXTURE, reader="numfocus")

    assert report.elements_read == 14
    assert report.nodes_upserted > 0
    assert report.edges_upserted > 0
    assert report.violation_count == 0
    dataset = lib.list_datasets()[0]
    assert dataset.dataset_id == report.dataset_id
    assert dataset.reader == "numfocus-hin"
