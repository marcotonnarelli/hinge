from __future__ import annotations

from hinge.kernel.projection.projection_spec import ProjectionSpec

SPEC = ProjectionSpec(
    name="user-user-co-edit-file",
    description=(
        "Cookbook user-user co-edit network. Connects users who touched the "
        "same file when commit/file-touch data exists."
    ),
    model_name="co_edit_file_user_user",
    output_node_types=["user"],
    output_edge_types=["co_edited_file"],
)
