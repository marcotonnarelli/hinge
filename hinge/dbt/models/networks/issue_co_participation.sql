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

{{ network_edges(
    relation='co_participation',
    recipe_name='issue_co_participation',
    source_node_id='source_node_id',
    source_node_type="'user'",
    target_node_id='target_node_id',
    target_node_type="'user'",
    edge_type="'co_participates_issue'",
    directed='false',
    weight='weight',
    weight_kind='weight_kind',
    n_contexts='n_contexts',
    first_seen_at='first_seen_at',
    last_seen_at='last_seen_at',
    properties="to_json({'shared_issues': n_contexts, 'issues': context_node_ids})"
) }}
