{{ config(materialized='table') }}

{{ assert_recipe_supported('fork_repo_repo', ['has_forks']) }}

WITH fork_edges AS (
    {{ slice_edges(
        edge_types=['fork_of'],
        source_types=['repo'],
        target_types=['repo']
    ) }}
)

SELECT
    source_node_id AS src_id,
    'repo' AS src_type,
    target_node_id AS dst_id,
    'repo' AS dst_type,
    'fork_of' AS edge_type,
    to_json({
        'recipe_name': 'fork_repo_repo',
        'recipe_version': '1',
        'directed': true,
        'weight': coalesce(weight, 1.0),
        'weight_kind': 'binary',
        'first_seen_at': occurred_at,
        'last_seen_at': occurred_at,
        'source_record_id': source_record_id
    }) AS attrs
FROM fork_edges
