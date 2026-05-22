{{ config(materialized='table') }}

WITH manifest AS (
    SELECT *
    FROM {{ source('hin', 'active_contract_adapter_manifest') }}
),

capabilities AS (
    SELECT adapter_run_id, adapter_name, adapter_version, source_name, coverage_start, coverage_end,
           'has_accounts' AS capability, has_accounts AS is_available FROM manifest
    UNION ALL SELECT adapter_run_id, adapter_name, adapter_version, source_name, coverage_start, coverage_end,
           'has_repositories', has_repositories FROM manifest
    UNION ALL SELECT adapter_run_id, adapter_name, adapter_version, source_name, coverage_start, coverage_end,
           'has_commits', has_commits FROM manifest
    UNION ALL SELECT adapter_run_id, adapter_name, adapter_version, source_name, coverage_start, coverage_end,
           'has_file_touches', has_file_touches FROM manifest
    UNION ALL SELECT adapter_run_id, adapter_name, adapter_version, source_name, coverage_start, coverage_end,
           'has_line_touches', has_line_touches FROM manifest
    UNION ALL SELECT adapter_run_id, adapter_name, adapter_version, source_name, coverage_start, coverage_end,
           'has_pull_requests', has_pull_requests FROM manifest
    UNION ALL SELECT adapter_run_id, adapter_name, adapter_version, source_name, coverage_start, coverage_end,
           'has_pr_reviews', has_pr_reviews FROM manifest
    UNION ALL SELECT adapter_run_id, adapter_name, adapter_version, source_name, coverage_start, coverage_end,
           'has_issues', has_issues FROM manifest
    UNION ALL SELECT adapter_run_id, adapter_name, adapter_version, source_name, coverage_start, coverage_end,
           'has_comments', has_comments FROM manifest
    UNION ALL SELECT adapter_run_id, adapter_name, adapter_version, source_name, coverage_start, coverage_end,
           'has_stars', has_stars FROM manifest
    UNION ALL SELECT adapter_run_id, adapter_name, adapter_version, source_name, coverage_start, coverage_end,
           'has_watches', has_watches FROM manifest
    UNION ALL SELECT adapter_run_id, adapter_name, adapter_version, source_name, coverage_start, coverage_end,
           'has_forks', has_forks FROM manifest
    UNION ALL SELECT adapter_run_id, adapter_name, adapter_version, source_name, coverage_start, coverage_end,
           'has_follows', has_follows FROM manifest
    UNION ALL SELECT adapter_run_id, adapter_name, adapter_version, source_name, coverage_start, coverage_end,
           'has_mentions', has_mentions FROM manifest
    UNION ALL SELECT adapter_run_id, adapter_name, adapter_version, source_name, coverage_start, coverage_end,
           'has_artifact_refs', has_artifact_refs FROM manifest
)

SELECT *
FROM capabilities
