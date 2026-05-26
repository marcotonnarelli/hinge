{% macro network_edges(
    relation,
    recipe_name,
    source_node_id,
    source_node_type,
    target_node_id,
    target_node_type,
    edge_type,
    directed,
    weight='NULL',
    weight_kind='NULL',
    n_contexts='NULL',
    n_events='NULL',
    first_seen_at='NULL',
    last_seen_at='NULL',
    time_bin='NULL',
    bot_policy="'include'",
    properties="'{}'"
) %}
SELECT
    '{{ recipe_name }}'::TEXT AS recipe_name,
    '1'::TEXT AS recipe_version,
    {{ source_node_id }}::TEXT AS source_node_id,
    {{ source_node_type }}::TEXT AS source_node_type,
    {{ target_node_id }}::TEXT AS target_node_id,
    {{ target_node_type }}::TEXT AS target_node_type,
    {{ directed }}::BOOLEAN AS directed,
    {{ edge_type }}::TEXT AS edge_type,
    {{ weight }}::DOUBLE AS weight,
    {{ weight_kind }}::TEXT AS weight_kind,
    {{ n_contexts }}::INTEGER AS n_contexts,
    {{ n_events }}::INTEGER AS n_events,
    {{ first_seen_at }}::TIMESTAMP AS first_seen_at,
    {{ last_seen_at }}::TIMESTAMP AS last_seen_at,
    {{ time_bin }}::TEXT AS time_bin,
    {{ bot_policy }}::TEXT AS bot_policy,
    {{ properties }} AS properties
FROM {{ relation }}
{% endmacro %}
