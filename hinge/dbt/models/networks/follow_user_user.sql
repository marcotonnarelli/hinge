{{ config(materialized='table') }}

{{ assert_recipe_supported('follow_user_user', ['has_follows']) }}

WITH follow_edges AS (
    {{ slice_edges(
        edge_types=['follows'],
        source_types=['user'],
        target_types=['user']
    ) }}
)

SELECT
    source_node_id AS src_id,
    'user' AS src_type,
    target_node_id AS dst_id,
    'user' AS dst_type,
    'follows' AS edge_type,
    to_json({
        'recipe_name': 'follow_user_user',
        'recipe_version': '1',
        'directed': true,
        'weight': coalesce(weight, 1.0),
        'weight_kind': 'binary',
        'first_seen_at': occurred_at,
        'last_seen_at': occurred_at,
        'source_record_id': source_record_id
    }) AS attrs
FROM follow_edges
