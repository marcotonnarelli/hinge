{% macro collapse_two_hop_path(
    first_relation,
    second_relation,
    source_col,
    mediator_col,
    second_source_col,
    target_col,
    directed=true
) %}
SELECT
    first_hop.{{ source_col }} AS source_node_id,
    second_hop.{{ target_col }} AS target_node_id,
    count(DISTINCT first_hop.{{ mediator_col }}) AS n_contexts,
    list_distinct(list(first_hop.{{ mediator_col }})) AS context_node_ids,
    min(least(first_hop.first_seen_at, second_hop.first_seen_at)) AS first_seen_at,
    max(greatest(first_hop.last_seen_at, second_hop.last_seen_at)) AS last_seen_at
FROM {{ first_relation }} AS first_hop
JOIN {{ second_relation }} AS second_hop
    ON first_hop.{{ mediator_col }} = second_hop.{{ second_source_col }}
{% if directed %}
WHERE first_hop.{{ source_col }} != second_hop.{{ target_col }}
{% else %}
WHERE first_hop.{{ source_col }} < second_hop.{{ target_col }}
{% endif %}
GROUP BY first_hop.{{ source_col }}, second_hop.{{ target_col }}
{% endmacro %}
