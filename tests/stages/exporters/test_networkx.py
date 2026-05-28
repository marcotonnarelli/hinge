from __future__ import annotations

import io
import json

from hinge.kernel.projection.projected_graph import ProjectedGraph
from hinge.kernel.schema import TypedEdge, TypedNode
from hinge.stages.exporters.networkx_exporter import NetworkXExporter


def test_networkx_exports_weighted_graph_with_node_attributes() -> None:
    handle = ProjectedGraph(
        nodes=[
            TypedNode(
                type="user",
                id="user:alice",
                attrs={"display_name": "Alice", "node_subtype": "human"},
            ),
            TypedNode(type="repo", id="repo:example", attrs={"display_name": "org/example"}),
        ],
        edges=[
            TypedEdge(
                type="contributed_to",
                src_id="user:alice",
                dst_id="repo:example",
                attrs={"weight": 3.0, "weight_kind": "event_count"},
            ),
        ],
    )
    sink = io.BytesIO()

    receipt = NetworkXExporter().write(handle, sink)
    data = json.loads(sink.getvalue().decode())

    assert receipt.format == "networkx"
    assert receipt.node_count == 2
    assert receipt.edge_count == 1
    assert data["directed"] is True
    assert data["multigraph"] is True
    assert data["nodes"][0]["display_name"] == "Alice"
    assert data["edges"][0]["type"] == "contributed_to"
    assert data["edges"][0]["weight"] == 3.0


def test_networkx_defaults_missing_weight_to_one() -> None:
    handle = ProjectedGraph(
        nodes=[],
        edges=[TypedEdge(type="related", src_id="a", dst_id="b")],
    )
    sink = io.BytesIO()

    NetworkXExporter().write(handle, sink)
    data = json.loads(sink.getvalue().decode())

    assert data["edges"][0]["weight"] == 1.0
