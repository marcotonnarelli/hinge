from __future__ import annotations

from typing import BinaryIO

from hinge.kernel.projection.projected_graph import ProjectedGraphHandle
from hinge.kernel.protocols.exporter_stage import ExportReceipt


class GexfExporter:
    def write(self, handle: ProjectedGraphHandle, sink: BinaryIO) -> ExportReceipt:
        raise NotImplementedError(
            "GexfExporter is a stub. Implement before registering an entry-point."
        )
