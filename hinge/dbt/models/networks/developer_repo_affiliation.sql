{{ config(materialized='table') }}

{{ assert_recipe_supported(
    'developer_repo_affiliation',
    ['has_pull_requests', 'has_pr_reviews', 'has_issues', 'has_comments']
) }}

SELECT
    user_node_id AS src_id,
    'user' AS src_type,
    repo_node_id AS dst_id,
    'repo' AS dst_type,
    'affiliated_with' AS edge_type,
    to_json({
        'recipe_name': 'developer_repo_affiliation',
        'recipe_version': '1',
        'directed': true,
        'weight': weight,
        'weight_kind': 'event_count',
        'n_events': n_events,
        'roles': roles,
        'first_seen_at': first_seen_at,
        'last_seen_at': last_seen_at
    }) AS attrs
FROM {{ ref('int_developer_repo_affiliation') }}
