{{ config(materialized='table') }}

SELECT
    artifact_key            AS node_id,
    artifact_type,
    repo_key                AS repo_node_id,
    parent_artifact_key     AS parent_artifact_node_id,
    github_id,
    number,
    sha,
    url,
    title,
    state,
    file_path,
    start_line,
    end_line,
    created_at,
    updated_at,
    closed_at,
    merged_at,
    observed_at,
    artifact_json           AS properties
FROM {{ ref('stg_artifacts') }}
