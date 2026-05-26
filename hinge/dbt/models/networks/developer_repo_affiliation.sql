{{ config(materialized='table') }}

{{ assert_recipe_supported('developer_repo_affiliation') }}

{{ network_edges(
    relation=ref('int_developer_repo_affiliation'),
    recipe_name='developer_repo_affiliation',
    source_node_id='user_node_id',
    source_node_type="'user'",
    target_node_id='repo_node_id',
    target_node_type="'repo'",
    edge_type="'affiliated_with'",
    directed='true',
    weight='weight',
    weight_kind="'event_count'",
    n_events='n_events',
    first_seen_at='first_seen_at',
    last_seen_at='last_seen_at',
    properties="to_json({'roles': roles})"
) }}
