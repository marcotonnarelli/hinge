{% macro assert_recipe_supported(recipe_name, required_capabilities) %}
    {% if execute %}
        {% set missing_query %}
            WITH required(capability) AS (
                VALUES
                {%- for capability in required_capabilities %}
                    ('{{ capability }}'){% if not loop.last %},{% endif %}
                {%- endfor %}
            ),

            manifest AS (
                SELECT *
                FROM {{ source('hin', 'active_contract_adapter_manifest') }}
            ),

            available AS (
                SELECT 'has_accounts' AS capability, bool_or(coalesce(has_accounts, false)) AS is_available FROM manifest
                UNION ALL SELECT 'has_repositories', bool_or(coalesce(has_repositories, false)) FROM manifest
                UNION ALL SELECT 'has_commits', bool_or(coalesce(has_commits, false)) FROM manifest
                UNION ALL SELECT 'has_file_touches', bool_or(coalesce(has_file_touches, false)) FROM manifest
                UNION ALL SELECT 'has_line_touches', bool_or(coalesce(has_line_touches, false)) FROM manifest
                UNION ALL SELECT 'has_pull_requests', bool_or(coalesce(has_pull_requests, false)) FROM manifest
                UNION ALL SELECT 'has_pr_reviews', bool_or(coalesce(has_pr_reviews, false)) FROM manifest
                UNION ALL SELECT 'has_issues', bool_or(coalesce(has_issues, false)) FROM manifest
                UNION ALL SELECT 'has_comments', bool_or(coalesce(has_comments, false)) FROM manifest
                UNION ALL SELECT 'has_stars', bool_or(coalesce(has_stars, false)) FROM manifest
                UNION ALL SELECT 'has_watches', bool_or(coalesce(has_watches, false)) FROM manifest
                UNION ALL SELECT 'has_forks', bool_or(coalesce(has_forks, false)) FROM manifest
                UNION ALL SELECT 'has_follows', bool_or(coalesce(has_follows, false)) FROM manifest
                UNION ALL SELECT 'has_mentions', bool_or(coalesce(has_mentions, false)) FROM manifest
                UNION ALL SELECT 'has_artifact_refs', bool_or(coalesce(has_artifact_refs, false)) FROM manifest
            )

            SELECT required.capability
            FROM required
            LEFT JOIN available USING (capability)
            WHERE coalesce(available.is_available, false) = false
        {% endset %}
        {% set missing = run_query(missing_query) %}
        {% if missing is not none and missing.rows | length > 0 %}
            {% set missing_names = [] %}
            {% for row in missing.rows %}
                {% do missing_names.append(row[0]) %}
            {% endfor %}
            {{ exceptions.raise_compiler_error(
                'Cannot build `' ~ recipe_name ~ '` from this adapter run. Missing capabilities: ' ~ (missing_names | join(', '))
            ) }}
        {% endif %}
    {% endif %}
{% endmacro %}
