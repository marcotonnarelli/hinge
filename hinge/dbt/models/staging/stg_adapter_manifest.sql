{{ config(materialized='view') }}

SELECT *
FROM {{ source('hin', 'active_contract_adapter_manifest') }}
