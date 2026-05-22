{{ config(materialized='table') }}

{{ assert_recipe_supported('pr_author_reviewer', ['has_pull_requests', 'has_pr_reviews']) }}

WITH pr_events AS (
    SELECT *
    FROM {{ ref('int_user_artifact_incidence') }}
    WHERE right_node_subtype = 'pull_request'
      AND role IN ('opened', 'reviewed')
),

openers AS (
    SELECT
        left_node_id AS author_node_id,
        right_node_id AS pr_node_id,
        min(occurred_at) AS first_seen_at
    FROM pr_events
    WHERE role = 'opened'
    GROUP BY left_node_id, right_node_id
),

reviewers AS (
    SELECT
        left_node_id AS reviewer_node_id,
        right_node_id AS pr_node_id,
        min(occurred_at) AS first_seen_at,
        max(occurred_at) AS last_seen_at,
        count(DISTINCT evidence_edge_id) AS n_reviews
    FROM pr_events
    WHERE role = 'reviewed'
    GROUP BY left_node_id, right_node_id
),

author_reviewer AS (
    SELECT
        openers.author_node_id,
        reviewers.reviewer_node_id,
        count(DISTINCT openers.pr_node_id) AS n_contexts,
        sum(reviewers.n_reviews) AS n_events,
        list_distinct(list(openers.pr_node_id)) AS pull_requests,
        min(least(openers.first_seen_at, reviewers.first_seen_at)) AS first_seen_at,
        max(reviewers.last_seen_at) AS last_seen_at
    FROM openers
    JOIN reviewers
        ON reviewers.pr_node_id = openers.pr_node_id
       AND reviewers.reviewer_node_id != openers.author_node_id
    GROUP BY openers.author_node_id, reviewers.reviewer_node_id
)

SELECT
    author_node_id AS src_id,
    'user' AS src_type,
    reviewer_node_id AS dst_id,
    'user' AS dst_type,
    'reviewed_pr_from' AS edge_type,
    to_json({
        'recipe_name': 'pr_author_reviewer',
        'recipe_version': '1',
        'directed': true,
        'weight': n_contexts,
        'weight_kind': 'shared_count',
        'pull_requests': pull_requests,
        'n_events': n_events,
        'first_seen_at': first_seen_at,
        'last_seen_at': last_seen_at
    }) AS attrs
FROM author_reviewer
