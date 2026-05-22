from __future__ import annotations

from hinge.kernel.projection.projection_spec import ProjectionSpec

SPEC = ProjectionSpec(
    name="user-repo-watch",
    description=(
        "Cookbook user-repository watch/subscription network. Emits directed "
        "user -> repo 'watches' edges when the active adapter collected watch data."
    ),
    model_name="watch_user_repo",
    output_node_types=["user", "repo"],
    output_edge_types=["watches"],
)
