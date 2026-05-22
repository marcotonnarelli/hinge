from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel

from hinge.kernel.projection.projected_graph import ProjectedGraphHandle
from hinge.kernel.projection.projection_spec import ProjectionSpec
from hinge.kernel.protocols.dataset_view import DatasetView


class EngineFingerprint(BaseModel):
    """Hash of the projection engine's own code (e.g. dbt project files).
    Combined with the store fingerprint and schema version to make snapshot_id.
    """

    engine: str
    project_hash: str


class ProjectionStage(Protocol):
    """Materialises a typed sub-graph from a dataset.

    The projection takes a :class:`ProjectionSpec` (what to compute) and a
    :class:`DatasetView` (where to read from). It never touches the store
    directly — the store handed it everything it needs.
    """

    def run(
        self,
        spec: ProjectionSpec,
        params: dict[str, Any],
        view: DatasetView,
    ) -> ProjectedGraphHandle: ...

    def fingerprint(self) -> EngineFingerprint: ...
