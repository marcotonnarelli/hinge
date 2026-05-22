from __future__ import annotations

from hinge.kernel.projection.projection_spec import ProjectionSpec

SPEC = ProjectionSpec(
    name="repo-repo-fork",
    description=(
        "Cookbook repository fork network. Emits directed fork repo -> "
        "upstream repo 'fork_of' edges when fork metadata is available."
    ),
    model_name="fork_repo_repo",
    output_node_types=["repo"],
    output_edge_types=["fork_of"],
)
