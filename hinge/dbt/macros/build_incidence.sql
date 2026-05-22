{% macro build_incidence(
    left_type,
    right_type,
    edge_types=None,
    left_subtypes=None,
    right_subtypes=None,
    bot_policy='include_bots',
    weight_mode='event_count',
    start_date=None,
    end_date=None
) %}
WITH sliced_edges AS (
    {{ slice_edges(
        edge_types=edge_types,
        source_types=[left_type],
        target_types=[right_type],
        source_subtypes=left_subtypes,
        target_subtypes=right_subtypes,
        bot_policy=bot_policy,
        start_date=start_date,
        end_date=end_date
    ) }}
)

SELECT
    source_node_id AS left_node_id,
    source_node_type AS left_node_type,
    source_node_subtype AS left_node_subtype,
    target_node_id AS right_node_id,
    target_node_type AS right_node_type,
    target_node_subtype AS right_node_subtype,
    edge_id AS evidence_edge_id,
    edge_type AS role,
    occurred_at,
    {% if weight_mode == 'event_count' %}
        coalesce(event_count, 1)
    {% elif weight_mode == 'weight' %}
        coalesce(weight, 1.0)
    {% elif weight_mode == 'binary' %}
        1
    {% else %}
        {{ exceptions.raise_compiler_error('Unknown incidence weight_mode: ' ~ weight_mode) }}
    {% endif %} AS weight,
    '{{ weight_mode }}' AS weight_kind
FROM sliced_edges
{% endmacro %}
