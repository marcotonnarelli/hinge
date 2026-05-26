{{ config(materialized='table') }}

{{ assert_recipe_supported('watch_user_repo') }}

WITH watch_edges AS (
    {{ slice_edges(
        edge_types=['watches'],
        source_types=['user'],
        target_types=['repo']
    ) }}
)

{{ network_edges(
    relation='watch_edges',
    recipe_name='watch_user_repo',
    source_node_id='source_node_id',
    source_node_type="'user'",
    target_node_id='target_node_id',
    target_node_type="'repo'",
    edge_type="'watches'",
    directed='true',
    weight='coalesce(weight, 1.0)',
    weight_kind="'binary'",
    first_seen_at='occurred_at',
    last_seen_at='occurred_at',
    properties="to_json({'source_record_id': source_record_id})"
) }}
