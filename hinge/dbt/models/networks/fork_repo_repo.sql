{{ config(materialized='table') }}

{{ assert_recipe_supported('fork_repo_repo', ['has_forks']) }}

WITH fork_edges AS (
    {{ slice_edges(
        edge_types=['fork_of'],
        source_types=['repo'],
        target_types=['repo']
    ) }}
)

{{ network_edges(
    relation='fork_edges',
    recipe_name='fork_repo_repo',
    source_node_id='source_node_id',
    source_node_type="'repo'",
    target_node_id='target_node_id',
    target_node_type="'repo'",
    edge_type="'fork_of'",
    directed='true',
    weight='coalesce(weight, 1.0)',
    weight_kind="'binary'",
    first_seen_at='occurred_at',
    last_seen_at='occurred_at',
    properties="to_json({'source_record_id': source_record_id})"
) }}
