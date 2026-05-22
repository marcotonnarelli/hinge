from __future__ import annotations

from hinge.kernel.projection.projection_spec import ProjectionSpec

SPEC = ProjectionSpec(
    name="user-issue-participation",
    description=(
        "Cookbook user-issue participation network. Emits user -> issue "
        "edges carrying roles such as opener, commenter, and closer."
    ),
    model_name="issue_participation",
    output_node_types=["user", "artifact"],
    output_edge_types=["participated_in_issue"],
)
