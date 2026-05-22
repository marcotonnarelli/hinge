{{ config(materialized='table') }}

{{ assert_recipe_supported('artifact_reference', ['has_artifact_refs']) }}

WITH reference_edges AS (
    {{ slice_edges(
        edge_types=['references', 'closes', 'fixes', 'duplicates', 'relates_to'],
        source_types=['artifact'],
        target_types=['artifact']
    ) }}
)

SELECT
    source_node_id AS src_id,
    'artifact' AS src_type,
    target_node_id AS dst_id,
    'artifact' AS dst_type,
    edge_type,
    to_json({
        'recipe_name': 'artifact_reference',
        'recipe_version': '1',
        'directed': true,
        'weight': coalesce(weight, 1.0),
        'weight_kind': 'binary',
        'first_seen_at': occurred_at,
        'last_seen_at': occurred_at,
        'source_record_id': source_record_id,
        'reference_type': edge_type
    }) AS attrs
FROM reference_edges
