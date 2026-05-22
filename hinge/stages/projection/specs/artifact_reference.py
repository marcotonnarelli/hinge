from __future__ import annotations

from hinge.kernel.projection.projection_spec import ProjectionSpec

SPEC = ProjectionSpec(
    name="artifact-reference",
    description=(
        "Cookbook artifact-artifact reference network. Emits issue/PR/comment "
        "reference, close, fix, duplicate, and related-to edges when collected."
    ),
    model_name="artifact_reference",
    output_node_types=["artifact"],
    output_edge_types=["references", "closes", "fixes", "duplicates", "relates_to"],
)
