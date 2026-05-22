{{ config(materialized='table') }}

{{ assert_recipe_supported('issue_co_participation', ['has_issues', 'has_comments']) }}

WITH issue_events AS (
    SELECT *
    FROM {{ ref('int_user_artifact_incidence') }}
    WHERE right_node_subtype = 'issue'
      AND role IN ('opened', 'commented_on', 'closed')
),

issue_participation AS (
    SELECT
        left_node_id AS user_node_id,
        right_node_id AS issue_node_id,
        min(occurred_at) AS first_seen_at,
        max(occurred_at) AS last_seen_at,
        sum(weight)::DOUBLE AS weight,
        count(DISTINCT evidence_edge_id) AS n_events,
        list_distinct(list(role)) AS roles
    FROM issue_events
    GROUP BY left_node_id, right_node_id
),

co_participation AS (
    {{ project_bipartite(
        incidence_relation='issue_participation',
        left_col='user_node_id',
        right_col='issue_node_id',
        directed=false,
        weight_mode='shared_count'
    ) }}
)

SELECT
    source_node_id AS src_id,
    'user' AS src_type,
    target_node_id AS dst_id,
    'user' AS dst_type,
    'co_participates_issue' AS edge_type,
    to_json({
        'recipe_name': 'issue_co_participation',
        'recipe_version': '1',
        'directed': false,
        'weight': weight,
        'weight_kind': weight_kind,
        'shared_issues': n_contexts,
        'issues': context_node_ids,
        'first_seen_at': first_seen_at,
        'last_seen_at': last_seen_at
    }) AS attrs
FROM co_participation
