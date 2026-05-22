{{ config(materialized='table') }}

{{ assert_recipe_supported('pr_reviewer_coreview', ['has_pull_requests', 'has_pr_reviews']) }}

WITH review_events AS (
    SELECT *
    FROM {{ ref('int_user_artifact_incidence') }}
    WHERE right_node_subtype = 'pull_request'
      AND role = 'reviewed'
),

reviewer_pr AS (
    SELECT
        left_node_id AS reviewer_node_id,
        right_node_id AS pr_node_id,
        min(occurred_at) AS first_seen_at,
        max(occurred_at) AS last_seen_at,
        sum(weight)::DOUBLE AS weight
    FROM review_events
    GROUP BY left_node_id, right_node_id
),

co_reviews AS (
    {{ project_bipartite(
        incidence_relation='reviewer_pr',
        left_col='reviewer_node_id',
        right_col='pr_node_id',
        directed=false,
        weight_mode='shared_count'
    ) }}
)

SELECT
    source_node_id AS src_id,
    'user' AS src_type,
    target_node_id AS dst_id,
    'user' AS dst_type,
    'co_reviewed_pr' AS edge_type,
    to_json({
        'recipe_name': 'pr_reviewer_coreview',
        'recipe_version': '1',
        'directed': false,
        'weight': weight,
        'weight_kind': weight_kind,
        'shared_pull_requests': n_contexts,
        'pull_requests': context_node_ids,
        'first_seen_at': first_seen_at,
        'last_seen_at': last_seen_at
    }) AS attrs
FROM co_reviews
