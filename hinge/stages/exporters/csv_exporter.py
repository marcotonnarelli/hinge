from __future__ import annotations

import csv
import hashlib
import json
import logging
from io import BytesIO, StringIO
from typing import Any, BinaryIO
from zipfile import ZIP_DEFLATED, ZipFile

from hinge.kernel.projection.projected_graph import ProjectedGraphHandle
from hinge.kernel.protocols.exporter_stage import ExportReceipt

logger = logging.getLogger(__name__)

_NODE_COLUMNS = ["id", "type", "attrs"]
_EDGE_COLUMNS = ["source", "target", "type", "weight", "attrs"]


class CsvExporter:
    """Write nodes.csv and edges.csv into one zip archive."""

    def write(self, handle: ProjectedGraphHandle, sink: BinaryIO) -> ExportReceipt:
        logger.debug("csv exporter started")
        digest = hashlib.sha256()
        node_count = 0
        edge_count = 0

        nodes = StringIO()
        node_writer = csv.DictWriter(nodes, fieldnames=_NODE_COLUMNS)
        node_writer.writeheader()
        for node in handle.iter_nodes():
            node_writer.writerow(
                {
                    "id": node.id,
                    "type": node.type,
                    "attrs": _json_dumps(node.attrs),
                }
            )
            node_count += 1

        edges = StringIO()
        edge_writer = csv.DictWriter(edges, fieldnames=_EDGE_COLUMNS)
        edge_writer.writeheader()
        for edge in handle.iter_edges():
            attrs = dict(edge.attrs)
            edge_writer.writerow(
                {
                    "source": edge.src_id,
                    "target": edge.dst_id,
                    "type": edge.type,
                    "weight": attrs.get("weight", ""),
                    "attrs": _json_dumps(attrs),
                }
            )
            edge_count += 1

        payload = BytesIO()
        with ZipFile(payload, mode="w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("nodes.csv", nodes.getvalue())
            archive.writestr("edges.csv", edges.getvalue())

        data = payload.getvalue()
        sink.write(data)
        digest.update(data)

        return ExportReceipt(
            format="csv",
            content_hash=digest.hexdigest(),
            schema_version=0,
            node_count=node_count,
            edge_count=edge_count,
        )


def _json_dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, default=str)
