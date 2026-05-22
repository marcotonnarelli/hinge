from __future__ import annotations

import io

from hinge.kernel.projection.projected_graph import ProjectedGraph
from hinge.kernel.schema import TypedEdge, TypedNode
from hinge.stages.exporters.gml_exporter import GmlExporter


def test_gml_node_and_edge_counts() -> None:
    handle = ProjectedGraph(
        nodes=[
            TypedNode(type="user", id="user:alice"),
            TypedNode(type="user", id="user:bob"),
        ],
        edges=[
            TypedEdge(type="opened", src_id="user:alice", dst_id="user:bob"),
        ],
    )
    sink = io.BytesIO()

    receipt = GmlExporter().write(handle, sink)
    output = sink.getvalue().decode()

    assert output.count("node [") == 2
    assert output.count("edge [") == 1
    assert receipt.format == "gml"
    assert receipt.node_count == 2
    assert receipt.edge_count == 1


def test_gml_passes_open_edge_labels_through() -> None:
    """A projection-emitted label like 'interacted_with' is written verbatim."""
    handle = ProjectedGraph(
        nodes=[],
        edges=[TypedEdge(type="interacted_with", src_id="user:a", dst_id="user:b")],
    )
    sink = io.BytesIO()
    GmlExporter().write(handle, sink)
    assert '"interacted_with"' in sink.getvalue().decode()
