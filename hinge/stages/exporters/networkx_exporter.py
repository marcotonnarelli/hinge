from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, BinaryIO, cast

from hinge.kernel.projection.projected_graph import ProjectedGraphHandle
from hinge.kernel.protocols.exporter_stage import ExportReceipt

logger = logging.getLogger(__name__)


class NetworkXExporter:
    """Write a projected graph as NetworkX node-link JSON."""

    def write(self, handle: ProjectedGraphHandle, sink: BinaryIO) -> ExportReceipt:
        logger.debug("networkx exporter started")
        data: dict[str, Any] = {
            "directed": True,
            "multigraph": True,
            "graph": {},
            "nodes": [],
            "edges": [],
        }
        node_count = 0
        edge_count = 0

        for node in handle.iter_nodes():
            attrs = _json_safe(node.attrs)
            data["nodes"].append({"id": node.id, "type": node.type, **attrs})
            node_count += 1

        for edge in handle.iter_edges():
            attrs = _json_safe(edge.attrs)
            weight = attrs.get("weight")
            if weight is None:
                weight = 1.0
            attrs["weight"] = weight
            attrs["type"] = edge.type
            data["edges"].append({"source": edge.src_id, "target": edge.dst_id, **attrs})
            edge_count += 1

        payload = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
        sink.write(payload)

        return ExportReceipt(
            format="networkx",
            content_hash=hashlib.sha256(payload).hexdigest(),
            schema_version=0,
            node_count=node_count,
            edge_count=edge_count,
        )


def _json_safe(attrs: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(json.dumps(attrs, default=str)))
