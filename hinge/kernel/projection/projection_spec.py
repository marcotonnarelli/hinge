from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProjectionParams(BaseModel):
    """Free-form key/value parameters passed to a projection at run time.

    Examples: window start/end dates, minimum interaction count, repo filter.
    Each projection documents which keys it consumes in its SQL header.
    """

    values: dict[str, Any] = Field(default_factory=dict)


class ProjectionSpec(BaseModel):
    """Declarative description of one projection.

    A spec is *metadata only*. It points the projection stage at a SQL model
    file and tells callers what the output looks like. Specs are discovered
    by the registry through the ``hinge.projection_specs`` entry-point group;
    third-party packages register new projections the same way readers and
    exporters are registered.

    See ``hinge/stages/projection/models/dev_interaction.sql`` for the
    contract every model must satisfy.
    """

    name: str
    description: str
    model_name: str
    output_node_types: list[str]
    output_edge_types: list[str]
