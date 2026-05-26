{{ config(materialized='table') }}

{{ assert_recipe_supported('co_edit_line_user_user', ['has_commits', 'has_line_touches']) }}

WITH line_touch_events AS (
    SELECT *
    FROM {{ ref('int_user_artifact_incidence') }}
    WHERE right_node_subtype = 'line_span'
      AND role = 'touched'
),

user_line AS (
    SELECT
        left_node_id AS user_node_id,
        right_node_id AS line_node_id,
        min(occurred_at) AS first_seen_at,
        max(occurred_at) AS last_seen_at,
        sum(weight)::DOUBLE AS weight
    FROM line_touch_events
    GROUP BY left_node_id, right_node_id
),

co_edits AS (
    {{ project_bipartite(
        incidence_relation='user_line',
        left_col='user_node_id',
        right_col='line_node_id',
        directed=false,
        weight_mode='shared_count'
    ) }}
)

{{ network_edges(
    relation='co_edits',
    recipe_name='co_edit_line_user_user',
    source_node_id='source_node_id',
    source_node_type="'user'",
    target_node_id='target_node_id',
    target_node_type="'user'",
    edge_type="'co_edited_line'",
    directed='false',
    weight='weight',
    weight_kind='weight_kind',
    n_contexts='n_contexts',
    first_seen_at='first_seen_at',
    last_seen_at='last_seen_at',
    properties="to_json({'shared_lines': n_contexts, 'line_spans': context_node_ids})"
) }}
