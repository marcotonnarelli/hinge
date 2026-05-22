{{ config(materialized='table') }}

{{ assert_recipe_supported(
    'repo_shared_contributors',
    ['has_commits', 'has_pull_requests', 'has_pr_reviews', 'has_issues', 'has_comments']
) }}

WITH contributor_repo AS (
    SELECT
        repo_node_id,
        user_node_id,
        min(first_seen_at) AS first_seen_at,
        max(last_seen_at) AS last_seen_at,
        sum(weight)::DOUBLE AS weight
    FROM {{ ref('int_developer_repo_affiliation') }}
    GROUP BY repo_node_id, user_node_id
),

shared AS (
    {{ project_bipartite(
        incidence_relation='contributor_repo',
        left_col='repo_node_id',
        right_col='user_node_id',
        directed=false,
        weight_mode='shared_count'
    ) }}
)

SELECT
    source_node_id AS src_id,
    'repo' AS src_type,
    target_node_id AS dst_id,
    'repo' AS dst_type,
    'shared_contributors' AS edge_type,
    to_json({
        'recipe_name': 'repo_shared_contributors',
        'recipe_version': '1',
        'directed': false,
        'weight': weight,
        'weight_kind': weight_kind,
        'shared_contributors': n_contexts,
        'contributors': context_node_ids,
        'first_seen_at': first_seen_at,
        'last_seen_at': last_seen_at
    }) AS attrs
FROM shared
