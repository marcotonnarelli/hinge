{{ config(materialized='table') }}

{{ assert_recipe_supported('user_mention_user', ['has_mentions', 'has_comments']) }}

WITH authored_comments AS (
    SELECT
        source_node_id AS author_node_id,
        target_node_id AS comment_node_id,
        min(occurred_at) AS first_seen_at,
        max(occurred_at) AS last_seen_at
    FROM {{ ref('hin_edges') }}
    WHERE source_node_type = 'user'
      AND target_node_type = 'artifact'
      AND target_node_subtype IN ('comment', 'issue_comment', 'review_comment', 'commit_comment')
      AND edge_type IN ('authored', 'commented_on', 'review_commented_on')
    GROUP BY source_node_id, target_node_id
),

comment_mentions AS (
    SELECT
        source_node_id AS comment_node_id,
        target_node_id AS mentioned_user_node_id,
        min(occurred_at) AS first_seen_at,
        max(occurred_at) AS last_seen_at
    FROM {{ ref('hin_edges') }}
    WHERE source_node_type = 'artifact'
      AND source_node_subtype IN ('comment', 'issue_comment', 'review_comment', 'commit_comment')
      AND target_node_type = 'user'
      AND edge_type = 'mentions'
    GROUP BY source_node_id, target_node_id
),

collapsed AS (
    {{ collapse_two_hop_path(
        first_relation='authored_comments',
        second_relation='comment_mentions',
        source_col='author_node_id',
        mediator_col='comment_node_id',
        second_source_col='comment_node_id',
        target_col='mentioned_user_node_id',
        directed=true
    ) }}
)

{{ network_edges(
    relation='collapsed',
    recipe_name='user_mention_user',
    source_node_id='source_node_id',
    source_node_type="'user'",
    target_node_id='target_node_id',
    target_node_type="'user'",
    edge_type="'mentions_user'",
    directed='true',
    weight='n_contexts',
    weight_kind="'count'",
    n_contexts='n_contexts',
    first_seen_at='first_seen_at',
    last_seen_at='last_seen_at',
    properties="to_json({'comments': context_node_ids})"
) }}
