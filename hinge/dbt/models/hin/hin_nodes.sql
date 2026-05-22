{{ config(materialized='table') }}

SELECT
    node_id,
    'user' AS node_type,
    account_type AS node_subtype,
    node_id AS natural_key,
    login AS display_name,
    created_at,
    NULL::TIMESTAMP AS updated_at,
    observed_at,
    false AS is_stub,
    properties
FROM {{ ref('hin_accounts') }}

UNION ALL

SELECT
    node_id,
    'repo' AS node_type,
    CASE WHEN is_fork THEN 'fork' ELSE 'repository' END AS node_subtype,
    full_name AS natural_key,
    full_name AS display_name,
    created_at,
    NULL::TIMESTAMP AS updated_at,
    observed_at,
    false AS is_stub,
    properties
FROM {{ ref('hin_repositories') }}

UNION ALL

SELECT
    node_id,
    'artifact' AS node_type,
    artifact_type AS node_subtype,
    node_id AS natural_key,
    coalesce(title, node_id) AS display_name,
    created_at,
    updated_at,
    observed_at,
    false AS is_stub,
    properties
FROM {{ ref('hin_artifacts') }}
