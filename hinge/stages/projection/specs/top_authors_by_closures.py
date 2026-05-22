from __future__ import annotations

from hinge.kernel.projection.projection_spec import ProjectionSpec

SPEC = ProjectionSpec(
    name="top-authors-by-closures",
    description=(
        "Top 20 users ranked by the number of distinct repositories in which "
        "they closed at least one pull request or issue. "
        "Emits 20 user nodes with no inter-user edges. Each node carries "
        "attrs.rank (1 = highest) and attrs.closed_repos (count of repos)."
    ),
    model_name="top_authors_by_closures",
    output_node_types=["user"],
    output_edge_types=["top_author"],
)
