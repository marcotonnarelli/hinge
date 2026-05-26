{{ config(materialized='table') }}

{{ assert_recipe_supported('repo_shared_contributors') }}

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

{{ network_edges(
    relation='shared',
    recipe_name='repo_shared_contributors',
    source_node_id='source_node_id',
    source_node_type="'repo'",
    target_node_id='target_node_id',
    target_node_type="'repo'",
    edge_type="'shared_contributors'",
    directed='false',
    weight='weight',
    weight_kind='weight_kind',
    n_contexts='n_contexts',
    first_seen_at='first_seen_at',
    last_seen_at='last_seen_at',
    properties="to_json({'shared_contributors': n_contexts, 'contributors': context_node_ids})"
) }}
