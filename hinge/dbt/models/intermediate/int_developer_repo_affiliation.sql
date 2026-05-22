{{ config(materialized='table') }}

WITH contains_edges AS (
    {{ slice_edges(
        edge_types=['contains'],
        source_types=['repo'],
        target_types=['artifact']
    ) }}
),

affiliations AS (
    SELECT
        incidence.left_node_id AS user_node_id,
        contains_edges.source_node_id AS repo_node_id,
        min(incidence.occurred_at) AS first_seen_at,
        max(incidence.occurred_at) AS last_seen_at,
        sum(incidence.weight)::DOUBLE AS weight,
        count(DISTINCT incidence.evidence_edge_id) AS n_events,
        list_distinct(list(incidence.role)) AS roles
    FROM {{ ref('int_user_artifact_incidence') }} AS incidence
    JOIN contains_edges
        ON contains_edges.target_node_id = incidence.right_node_id
    GROUP BY incidence.left_node_id, contains_edges.source_node_id
)

SELECT *
FROM affiliations
