{{ config(materialized='table') }}

{{ assert_recipe_supported('star_user_repo', ['has_stars']) }}

WITH starred_edges AS (
    {{ slice_edges(
        edge_types=['starred'],
        source_types=['user'],
        target_types=['repo']
    ) }}
)

SELECT
    source_node_id AS src_id,
    'user' AS src_type,
    target_node_id AS dst_id,
    'repo' AS dst_type,
    'starred' AS edge_type,
    to_json({
        'recipe_name': 'star_user_repo',
        'recipe_version': '1',
        'directed': true,
        'weight': coalesce(weight, 1.0),
        'weight_kind': 'binary',
        'first_seen_at': occurred_at,
        'last_seen_at': occurred_at,
        'source_record_id': source_record_id
    }) AS attrs
FROM starred_edges
