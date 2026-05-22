{{ config(materialized='table') }}

{{ assert_recipe_supported('pr_participation', ['has_pull_requests', 'has_pr_reviews']) }}

WITH pr_events AS (
    SELECT *
    FROM {{ ref('int_user_artifact_incidence') }}
    WHERE right_node_subtype = 'pull_request'
      AND role IN ('opened', 'reviewed', 'merged', 'commented_on', 'review_commented_on')
),

participation AS (
    SELECT
        left_node_id AS user_node_id,
        right_node_id AS pr_node_id,
        min(occurred_at) AS first_seen_at,
        max(occurred_at) AS last_seen_at,
        sum(weight)::DOUBLE AS weight,
        count(DISTINCT evidence_edge_id) AS n_events,
        list_distinct(list(role)) AS roles
    FROM pr_events
    GROUP BY left_node_id, right_node_id
)

SELECT
    user_node_id AS src_id,
    'user' AS src_type,
    pr_node_id AS dst_id,
    'artifact' AS dst_type,
    'participated_in_pr' AS edge_type,
    to_json({
        'recipe_name': 'pr_participation',
        'recipe_version': '1',
        'directed': true,
        'weight': weight,
        'weight_kind': 'event_count',
        'n_events': n_events,
        'roles': roles,
        'first_seen_at': first_seen_at,
        'last_seen_at': last_seen_at
    }) AS attrs
FROM participation
