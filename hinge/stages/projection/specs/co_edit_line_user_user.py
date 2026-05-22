from __future__ import annotations

from hinge.kernel.projection.projection_spec import ProjectionSpec

SPEC = ProjectionSpec(
    name="co-edit-line-user-user",
    description=(
        "Cookbook user-user line-level co-edit network. Connects users who "
        "touched the same line span when line-touch data exists."
    ),
    model_name="co_edit_line_user_user",
    output_node_types=["user"],
    output_edge_types=["co_edited_line"],
)
