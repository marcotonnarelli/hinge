{% macro filter_bots(source_alias='source_node', target_alias='target_node', policy='include_bots') %}
(
    {% if policy == 'include_bots' %}
        true
    {% elif policy == 'exclude_bots' %}
        coalesce({{ source_alias }}.node_subtype, '') != 'bot'
        AND coalesce({{ target_alias }}.node_subtype, '') != 'bot'
    {% elif policy == 'only_bots' %}
        (
            coalesce({{ source_alias }}.node_subtype, '') = 'bot'
            OR coalesce({{ target_alias }}.node_subtype, '') = 'bot'
        )
    {% elif policy == 'human_to_bot' %}
        coalesce({{ source_alias }}.node_subtype, '') != 'bot'
        AND coalesce({{ target_alias }}.node_subtype, '') = 'bot'
    {% elif policy == 'bot_to_human' %}
        coalesce({{ source_alias }}.node_subtype, '') = 'bot'
        AND coalesce({{ target_alias }}.node_subtype, '') != 'bot'
    {% else %}
        {{ exceptions.raise_compiler_error('Unknown bot_policy: ' ~ policy) }}
    {% endif %}
)
{% endmacro %}
