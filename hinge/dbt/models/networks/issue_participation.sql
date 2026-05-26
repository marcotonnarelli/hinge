{{ config(materialized='table') }}

{{ assert_recipe_supported('issue_participation') }}

WITH issue_events AS (
    SELECT *
    FROM {{ ref('int_user_artifact_incidence') }}
    WHERE right_node_subtype = 'issue'
      AND role IN ('opened', 'commented_on', 'closed')
),

participation AS (
    SELECT
        left_node_id AS user_node_id,
        right_node_id AS issue_node_id,
        min(occurred_at) AS first_seen_at,
        max(occurred_at) AS last_seen_at,
        sum(weight)::DOUBLE AS weight,
        count(DISTINCT evidence_edge_id) AS n_events,
        list_distinct(list(role)) AS roles
    FROM issue_events
    GROUP BY left_node_id, right_node_id
)

{{ network_edges(
    relation='participation',
    recipe_name='issue_participation',
    source_node_id='user_node_id',
    source_node_type="'user'",
    target_node_id='issue_node_id',
    target_node_type="'artifact'",
    edge_type="'participated_in_issue'",
    directed='true',
    weight='weight',
    weight_kind="'event_count'",
    n_events='n_events',
    first_seen_at='first_seen_at',
    last_seen_at='last_seen_at',
    properties="to_json({'roles': roles})"
) }}
