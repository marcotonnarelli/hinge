from __future__ import annotations

from hinge.kernel.projection.projection_spec import ProjectionSpec

SPEC = ProjectionSpec(
    name="developer-repo-affiliation",
    description=(
        "Cookbook user-repository affiliation network. Connects active "
        "contributors to repositories through issue, PR, review, comment, "
        "push, and lifecycle participation, excluding passive star/watch ties."
    ),
    model_name="developer_repo_affiliation",
    output_node_types=["user", "repo"],
    output_edge_types=["affiliated_with"],
)
