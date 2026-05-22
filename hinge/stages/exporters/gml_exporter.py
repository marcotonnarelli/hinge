from __future__ import annotations

import hashlib
import json
import logging
from typing import BinaryIO

from hinge.kernel.projection.projected_graph import ProjectedGraphHandle
from hinge.kernel.protocols.exporter_stage import ExportReceipt

logger = logging.getLogger(__name__)


class GmlExporter:
    """Stream a projected graph as GML plain-text.

    Edge labels are written through unchanged — the kernel uses an open
    label vocabulary, so the exporter does not need to consult any enum.
    """

    def write(self, handle: ProjectedGraphHandle, sink: BinaryIO) -> ExportReceipt:
        logger.debug("gml exporter started")
        node_ids: dict[str, int] = {}
        digest = hashlib.sha256()
        node_count = 0
        edge_count = 0

        def emit(line: str) -> None:
            payload = line.encode("utf-8")
            sink.write(payload)
            digest.update(payload)

        emit("graph [\n  directed 1\n")

        for node in handle.iter_nodes():
            idx = len(node_ids)
            node_ids[node.id] = idx
            emit(
                f"  node [\n"
                f"    id {idx}\n"
                f"    label {json.dumps(node.id)}\n"
                f"    type {json.dumps(node.type)}\n"
                f"  ]\n"
            )
            node_count += 1

        for edge in handle.iter_edges():
            if edge.src_id not in node_ids:
                node_ids[edge.src_id] = len(node_ids)
                emit(
                    f"  node [\n    id {node_ids[edge.src_id]}\n"
                    f"    label {json.dumps(edge.src_id)}\n  ]\n"
                )
                node_count += 1
            if edge.dst_id not in node_ids:
                node_ids[edge.dst_id] = len(node_ids)
                emit(
                    f"  node [\n    id {node_ids[edge.dst_id]}\n"
                    f"    label {json.dumps(edge.dst_id)}\n  ]\n"
                )
                node_count += 1
            emit(
                f"  edge [\n"
                f"    source {node_ids[edge.src_id]}\n"
                f"    target {node_ids[edge.dst_id]}\n"
                f"    label {json.dumps(edge.type)}\n"
                f"  ]\n"
            )
            edge_count += 1

        emit("]\n")

        return ExportReceipt(
            format="gml",
            content_hash=digest.hexdigest(),
            schema_version=0,  # set by runner.run_export when schema is passed
            node_count=node_count,
            edge_count=edge_count,
        )
