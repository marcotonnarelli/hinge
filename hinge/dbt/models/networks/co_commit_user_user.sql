{{ config(materialized='table') }}

{{ assert_recipe_supported('co_commit_user_user') }}

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

{{ network_edges(
    relation='co_commits',
    recipe_name='co_commit_user_user',
    source_node_id='source_node_id',
    source_node_type="'user'",
    target_node_id='target_node_id',
    target_node_type="'user'",
    edge_type="'co_committed'",
    directed='false',
    weight='weight',
    weight_kind='weight_kind',
    n_contexts='n_contexts',
    first_seen_at='first_seen_at',
    last_seen_at='last_seen_at',
    properties="to_json({'shared_commits': n_contexts, 'commits': context_node_ids})"
) }}
