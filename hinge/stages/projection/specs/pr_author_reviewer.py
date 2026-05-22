from __future__ import annotations

from hinge.kernel.projection.projection_spec import ProjectionSpec

SPEC = ProjectionSpec(
    name="pr-author-reviewer",
    description=(
        "Cookbook directed pull-request review network. Connects a PR opener "
        "to users who reviewed that pull request."
    ),
    model_name="pr_author_reviewer",
    output_node_types=["user"],
    output_edge_types=["reviewed_pr_from"],
)
