{{ config(materialized='table') }}

{{ assert_recipe_supported('pr_reviewer_coreview') }}

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

{{ network_edges(
    relation='co_reviews',
    recipe_name='pr_reviewer_coreview',
    source_node_id='source_node_id',
    source_node_type="'user'",
    target_node_id='target_node_id',
    target_node_type="'user'",
    edge_type="'co_reviewed_pr'",
    directed='false',
    weight='weight',
    weight_kind='weight_kind',
    n_contexts='n_contexts',
    first_seen_at='first_seen_at',
    last_seen_at='last_seen_at',
    properties="to_json({'shared_pull_requests': n_contexts, 'pull_requests': context_node_ids})"
) }}
