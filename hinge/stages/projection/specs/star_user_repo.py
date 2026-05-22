from __future__ import annotations

from hinge.kernel.projection.projection_spec import ProjectionSpec

SPEC = ProjectionSpec(
    name="star-user-repo",
    description=(
        "Cookbook user-repository attention network. Emits one directed "
        "user -> repo 'starred' edge for each GitHub star event available "
        "in the active adapter run."
    ),
    model_name="star_user_repo",
    output_node_types=["user", "repo"],
    output_edge_types=["starred"],
)
