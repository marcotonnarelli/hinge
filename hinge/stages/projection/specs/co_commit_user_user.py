from __future__ import annotations

from hinge.kernel.projection.projection_spec import ProjectionSpec

SPEC = ProjectionSpec(
    name="user-user-co-commit",
    description=(
        "Cookbook user-user co-commit network. Connects users who authored, "
        "committed, or coauthored the same commit when commit-level data exists."
    ),
    model_name="co_commit_user_user",
    output_node_types=["user"],
    output_edge_types=["co_committed"],
)
