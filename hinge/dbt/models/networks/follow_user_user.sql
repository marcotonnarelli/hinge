{{ config(materialized='table') }}

{{ assert_recipe_supported('follow_user_user', ['has_follows']) }}

WITH follow_edges AS (
    {{ slice_edges(
        edge_types=['follows'],
        source_types=['user'],
        target_types=['user']
    ) }}
)

{{ network_edges(
    relation='follow_edges',
    recipe_name='follow_user_user',
    source_node_id='source_node_id',
    source_node_type="'user'",
    target_node_id='target_node_id',
    target_node_type="'user'",
    edge_type="'follows'",
    directed='true',
    weight='coalesce(weight, 1.0)',
    weight_kind="'binary'",
    first_seen_at='occurred_at',
    last_seen_at='occurred_at',
    properties="to_json({'source_record_id': source_record_id})"
) }}
