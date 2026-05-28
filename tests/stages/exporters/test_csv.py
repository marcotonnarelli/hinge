from __future__ import annotations

import csv
import io
import json
from zipfile import ZipFile

from hinge.kernel.projection.projected_graph import ProjectedGraph
from hinge.kernel.schema import TypedEdge, TypedNode
from hinge.stages.exporters.csv_exporter import CsvExporter


def test_csv_exports_nodes_and_edges() -> None:
    handle = ProjectedGraph(
        nodes=[
            TypedNode(type="user", id="user:alice", attrs={"display_name": "Alice"}),
            TypedNode(type="repo", id="repo:example", attrs={"stars": 10}),
        ],
        edges=[
            TypedEdge(
                type="contributed_to",
                src_id="user:alice",
                dst_id="repo:example",
                attrs={"weight": 2.5, "weight_kind": "event_count"},
            )
        ],
    )
    sink = io.BytesIO()

    receipt = CsvExporter().write(handle, sink)

    assert receipt.format == "csv"
    assert receipt.node_count == 2
    assert receipt.edge_count == 1

    with ZipFile(io.BytesIO(sink.getvalue())) as archive:
        assert sorted(archive.namelist()) == ["edges.csv", "nodes.csv"]
        nodes = list(csv.DictReader(io.StringIO(archive.read("nodes.csv").decode())))
        edges = list(csv.DictReader(io.StringIO(archive.read("edges.csv").decode())))

    assert nodes[0]["id"] == "user:alice"
    assert json.loads(nodes[0]["attrs"])["display_name"] == "Alice"
    assert edges[0]["source"] == "user:alice"
    assert edges[0]["target"] == "repo:example"
    assert edges[0]["weight"] == "2.5"
    assert json.loads(edges[0]["attrs"])["weight_kind"] == "event_count"
