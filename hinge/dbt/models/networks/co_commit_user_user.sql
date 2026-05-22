{{ config(materialized='table') }}

{{ assert_recipe_supported('co_commit_user_user', ['has_commits']) }}

WITH commit_events AS (
    SELECT *
    FROM {{ ref('int_user_artifact_incidence') }}
    WHERE right_node_subtype = 'commit'
      AND role IN ('authored', 'committed', 'coauthored')
),

user_commit AS (
    SELECT
        left_node_id AS user_node_id,
        right_node_id AS commit_node_id,
        min(occurred_at) AS first_seen_at,
        max(occurred_at) AS last_seen_at,
        sum(weight)::DOUBLE AS weight
    FROM commit_events
    GROUP BY left_node_id, right_node_id
),

co_commits AS (
    {{ project_bipartite(
        incidence_relation='user_commit',
        left_col='user_node_id',
        right_col='commit_node_id',
        directed=false,
        weight_mode='shared_count'
    ) }}
)

SELECT
    source_node_id AS src_id,
    'user' AS src_type,
    target_node_id AS dst_id,
    'user' AS dst_type,
    'co_committed' AS edge_type,
    to_json({
        'recipe_name': 'co_commit_user_user',
        'recipe_version': '1',
        'directed': false,
        'weight': weight,
        'weight_kind': weight_kind,
        'shared_commits': n_contexts,
        'commits': context_node_ids,
        'first_seen_at': first_seen_at,
        'last_seen_at': last_seen_at
    }) AS attrs
FROM co_commits
