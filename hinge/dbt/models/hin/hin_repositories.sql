{{ config(materialized='table') }}

SELECT
    repo_key                        AS node_id,
    github_id,
    full_name,
    owner_account_key               AS owner_account_node_id,
    primary_language,
    coalesce(is_fork, false)        AS is_fork,
    forked_from_repo_key            AS forked_from_repo_node_id,
    created_at,
    archived_at,
    observed_at,
    repo_json                       AS properties
FROM {{ ref('stg_repositories') }}
