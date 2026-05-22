from __future__ import annotations

from hinge.kernel.projection.projection_spec import ProjectionSpec

SPEC = ProjectionSpec(
    name="user-user-pr-co-review",
    description=(
        "Cookbook reviewer-reviewer PR network. Connects users who reviewed "
        "the same pull request, weighted by shared PR count."
    ),
    model_name="pr_reviewer_coreview",
    output_node_types=["user"],
    output_edge_types=["co_reviewed_pr"],
)
