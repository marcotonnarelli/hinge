from __future__ import annotations

from hinge.kernel.projection.projection_spec import ProjectionSpec

SPEC = ProjectionSpec(
    name="user-pr-participation",
    description=(
        "Cookbook user-pull-request participation network. Emits user -> PR "
        "edges carrying roles such as opener, reviewer, commenter, and merger."
    ),
    model_name="pr_participation",
    output_node_types=["user", "artifact"],
    output_edge_types=["participated_in_pr"],
)
