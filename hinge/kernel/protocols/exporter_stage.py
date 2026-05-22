from __future__ import annotations

from typing import BinaryIO, Protocol

from pydantic import BaseModel

from hinge.kernel.projection.projected_graph import ProjectedGraphHandle


class ExportReceipt(BaseModel):
    """Result of one export. ``snapshot_id`` is set by the runner when both
    store and projection fingerprints are available; otherwise it stays None.
    """

    format: str
    content_hash: str
    schema_version: int
    node_count: int
    edge_count: int
    snapshot_id: str | None = None


class ExporterStage(Protocol):
    def write(self, handle: ProjectedGraphHandle, sink: BinaryIO) -> ExportReceipt: ...
