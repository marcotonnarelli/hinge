{{ config(materialized='table') }}

{{ assert_recipe_supported('artifact_reference', ['has_artifact_refs']) }}

WITH reference_edges AS (
    {{ slice_edges(
        edge_types=['references', 'closes', 'fixes', 'duplicates', 'relates_to'],
        source_types=['artifact'],
        target_types=['artifact']
    ) }}
)

{{ network_edges(
    relation='reference_edges',
    recipe_name='artifact_reference',
    source_node_id='source_node_id',
    source_node_type="'artifact'",
    target_node_id='target_node_id',
    target_node_type="'artifact'",
    edge_type='edge_type',
    directed='true',
    weight='coalesce(weight, 1.0)',
    weight_kind="'binary'",
    first_seen_at='occurred_at',
    last_seen_at='occurred_at',
    properties="to_json({'source_record_id': source_record_id, 'reference_type': edge_type})"
) }}
