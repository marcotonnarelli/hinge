{% macro project_bipartite(
    incidence_relation,
    left_col,
    right_col,
    directed=false,
    weight_mode='shared_count'
) %}
SELECT
    a.{{ left_col }} AS source_node_id,
    b.{{ left_col }} AS target_node_id,
    {% if weight_mode == 'shared_count' %}
        count(DISTINCT a.{{ right_col }})::DOUBLE AS weight,
        'shared_count' AS weight_kind,
    {% elif weight_mode == 'event_weighted' %}
        sum(coalesce(a.weight, 1.0) * coalesce(b.weight, 1.0))::DOUBLE AS weight,
        'event_weighted' AS weight_kind,
    {% else %}
        {{ exceptions.raise_compiler_error('Unknown projection weight_mode: ' ~ weight_mode) }}
    {% endif %}
    count(DISTINCT a.{{ right_col }}) AS n_contexts,
    list_distinct(list(a.{{ right_col }})) AS context_node_ids,
    min(least(a.first_seen_at, b.first_seen_at)) AS first_seen_at,
    max(greatest(a.last_seen_at, b.last_seen_at)) AS last_seen_at
FROM {{ incidence_relation }} AS a
JOIN {{ incidence_relation }} AS b
    ON a.{{ right_col }} = b.{{ right_col }}
    {% if directed %}
        AND a.{{ left_col }} != b.{{ left_col }}
    {% else %}
        AND a.{{ left_col }} < b.{{ left_col }}
    {% endif %}
GROUP BY a.{{ left_col }}, b.{{ left_col }}
{% endmacro %}
