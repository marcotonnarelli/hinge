from __future__ import annotations

from hinge.kernel.projection.projection_spec import ProjectionSpec

SPEC = ProjectionSpec(
    name="repo-shared-contributors",
    description=(
        "Cookbook repo-repo projection. Connects repositories that share at "
        "least one active contributor, weighted by number of shared users."
    ),
    model_name="repo_shared_contributors",
    output_node_types=["repo"],
    output_edge_types=["shared_contributors"],
)
