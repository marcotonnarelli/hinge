{{ config(materialized='table') }}

{{ assert_recipe_supported('co_edit_file_user_user', ['has_commits', 'has_file_touches']) }}

WITH file_touch_events AS (
    SELECT *
    FROM {{ ref('int_user_artifact_incidence') }}
    WHERE right_node_subtype = 'file'
      AND role = 'touched'
),

user_file AS (
    SELECT
        left_node_id AS user_node_id,
        right_node_id AS file_node_id,
        min(occurred_at) AS first_seen_at,
        max(occurred_at) AS last_seen_at,
        sum(weight)::DOUBLE AS weight
    FROM file_touch_events
    GROUP BY left_node_id, right_node_id
),

co_edits AS (
    {{ project_bipartite(
        incidence_relation='user_file',
        left_col='user_node_id',
        right_col='file_node_id',
        directed=false,
        weight_mode='shared_count'
    ) }}
)

SELECT
    source_node_id AS src_id,
    'user' AS src_type,
    target_node_id AS dst_id,
    'user' AS dst_type,
    'co_edited_file' AS edge_type,
    to_json({
        'recipe_name': 'co_edit_file_user_user',
        'recipe_version': '1',
        'directed': false,
        'weight': weight,
        'weight_kind': weight_kind,
        'shared_files': n_contexts,
        'files': context_node_ids,
        'first_seen_at': first_seen_at,
        'last_seen_at': last_seen_at
    }) AS attrs
FROM co_edits
