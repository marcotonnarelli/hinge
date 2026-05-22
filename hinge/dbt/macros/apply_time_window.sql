{% macro apply_time_window(timestamp_col='occurred_at', start_date=None, end_date=None) %}
(
    true
    {% if start_date is not none %}
        AND {{ timestamp_col }} >= CAST('{{ start_date }}' AS TIMESTAMP)
    {% endif %}
    {% if end_date is not none %}
        AND {{ timestamp_col }} < CAST('{{ end_date }}' AS TIMESTAMP)
    {% endif %}
)
{% endmacro %}
