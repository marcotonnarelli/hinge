{{ config(materialized='table') }}

SELECT
    account_key                             AS node_id,
    github_id,
    login,
    coalesce(account_type, 'unknown')       AS account_type,
    coalesce(is_bot, false)                 AS is_bot,
    bot_confidence,
    bot_source,
    created_at,
    observed_at,
    profile_json                           AS properties
FROM {{ ref('stg_accounts') }}
