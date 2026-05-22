from __future__ import annotations

from hinge.kernel.projection.projection_spec import ProjectionSpec

SPEC = ProjectionSpec(
    name="issue-co-participation",
    description=(
        "Cookbook user-user issue participation network. Connects users who "
        "opened, commented on, or closed the same issue."
    ),
    model_name="issue_co_participation",
    output_node_types=["user"],
    output_edge_types=["co_participates_issue"],
)
