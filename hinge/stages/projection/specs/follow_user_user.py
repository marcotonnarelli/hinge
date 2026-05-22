from __future__ import annotations

from hinge.kernel.projection.projection_spec import ProjectionSpec

SPEC = ProjectionSpec(
    name="user-user-follow",
    description=(
        "Cookbook user follow network. Emits directed user -> user 'follows' "
        "edges when the active adapter collected follower relations."
    ),
    model_name="follow_user_user",
    output_node_types=["user"],
    output_edge_types=["follows"],
)
