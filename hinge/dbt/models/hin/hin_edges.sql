{{ config(materialized='table') }}

WITH relations AS (
    SELECT
        relation_key AS edge_id,
        source_node_key AS source_node_id,
        CASE WHEN source_node_type = 'account' THEN 'user' ELSE source_node_type END AS source_node_type,
        target_node_key AS target_node_id,
        CASE WHEN target_node_type = 'account' THEN 'user' ELSE target_node_type END AS target_node_type,
        relation_type AS edge_type,
        relation_subtype AS edge_subtype,
        directed,
        occurred_at,
        observed_at,
        valid_from,
        valid_to,
        weight,
        event_count,
        adapter_run_id,
        source_record_id,
        properties
    FROM {{ ref('stg_relations') }}
)

SELECT
    r.edge_id,
    r.source_node_id,
    r.source_node_type,
    sn.node_subtype AS source_node_subtype,
    r.target_node_id,
    r.target_node_type,
    tn.node_subtype AS target_node_subtype,
    r.edge_type,
    r.edge_subtype,
    r.directed,
    r.occurred_at,
    r.observed_at,
    r.valid_from,
    r.valid_to,
    r.weight,
    r.event_count,
    CASE
        WHEN r.source_node_type = 'repo' THEN r.source_node_id
        WHEN r.target_node_type = 'repo' THEN r.target_node_id
    END AS context_repo_node_id,
    CASE
        WHEN r.source_node_type = 'artifact' THEN r.source_node_id
        WHEN r.target_node_type = 'artifact' THEN r.target_node_id
    END AS context_artifact_node_id,
    r.adapter_run_id,
    r.source_record_id,
    r.properties
FROM relations AS r
LEFT JOIN {{ ref('hin_nodes') }} AS sn
    ON sn.node_id = r.source_node_id
LEFT JOIN {{ ref('hin_nodes') }} AS tn
    ON tn.node_id = r.target_node_id
