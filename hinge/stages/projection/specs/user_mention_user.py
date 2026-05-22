from __future__ import annotations

from hinge.kernel.projection.projection_spec import ProjectionSpec

SPEC = ProjectionSpec(
    name="user-mention-user",
    description=(
        "Cookbook user mention network. Collapses user -> comment artifact -> "
        "mentioned user paths into directed user-user mention edges."
    ),
    model_name="user_mention_user",
    output_node_types=["user"],
    output_edge_types=["mentions_user"],
)
