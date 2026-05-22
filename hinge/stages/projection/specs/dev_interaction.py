"""Projection spec: user-user-repo-collaboration.

The SQL lives at ``hinge/dbt/models/networks/dev_interaction.sql``.
This module exposes the spec under the ``hinge.projection_specs`` entry-point
group so the registry can discover it like any other plugin.

To add a new projection: copy this file, point ``model_name`` at your SQL
file's stem, register the entry-point in pyproject.toml.
"""

from __future__ import annotations

from hinge.kernel.projection.projection_spec import ProjectionSpec

SPEC = ProjectionSpec(
    name="user-user-repo-collaboration",
    description=(
        "Undirected user-to-user collaboration graph. Two developers are "
        "connected by a 'collaborates_with' edge if they both made code "
        "contributions (opened/reviewed/merged PRs, commented, pushed) to "
        "the same repository. Edge attrs carry the count and list of shared repos."
    ),
    model_name="dev_interaction",
    output_node_types=["user"],
    output_edge_types=["collaborates_with"],
)
