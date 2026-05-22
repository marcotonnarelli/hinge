{% macro _sql_string_list(values) %}
    {%- for value in values -%}
        '{{ value }}'{% if not loop.last %}, {% endif %}
    {%- endfor -%}
{% endmacro %}

{% macro slice_edges(
    edge_types=None,
    source_types=None,
    target_types=None,
    source_subtypes=None,
    target_subtypes=None,
    bot_policy='include_bots',
    start_date=None,
    end_date=None
) %}
SELECT e.*
FROM {{ ref('hin_edges') }} AS e
LEFT JOIN {{ ref('hin_nodes') }} AS source_node
    ON source_node.node_id = e.source_node_id
LEFT JOIN {{ ref('hin_nodes') }} AS target_node
    ON target_node.node_id = e.target_node_id
WHERE true
{% if edge_types is not none %}
  AND e.edge_type IN ({{ _sql_string_list(edge_types) }})
{% endif %}
{% if source_types is not none %}
  AND e.source_node_type IN ({{ _sql_string_list(source_types) }})
{% endif %}
{% if target_types is not none %}
  AND e.target_node_type IN ({{ _sql_string_list(target_types) }})
{% endif %}
{% if source_subtypes is not none %}
  AND e.source_node_subtype IN ({{ _sql_string_list(source_subtypes) }})
{% endif %}
{% if target_subtypes is not none %}
  AND e.target_node_subtype IN ({{ _sql_string_list(target_subtypes) }})
{% endif %}
  AND {{ filter_bots('source_node', 'target_node', bot_policy) }}
  AND {{ apply_time_window('e.occurred_at', start_date, end_date) }}
{% endmacro %}
