-- ============================================================================
-- top_authors_by_closures.sql
--
-- WHAT THIS PROJECTION DOES
--   Produces the top 20 users ranked by the number of distinct repositories
--   in which they closed at least one pull request or issue.
--
--   "Closed a PR/issue in repo R" is expressed in the HIN as a two-hop path:
--     user -[closed]-> artifact <-[contains]- repo
--   We join the two edge types on the shared artifact id, deduplicate with
--   DISTINCT, then count repos per user.
--
-- NODES-ONLY TRICK
--   The output contract requires (src_id, src_type, dst_id, dst_type, …).
--   _CursorHandle.iter_nodes() derives nodes from the UNION of src_id and
--   dst_id, so a projection that emits no edges has no nodes either.
--   The workaround: use self-loop edges (src_id = dst_id). The exporter
--   writes them as graph edges from a node to itself; NetworkX and Gephi
--   both handle self-loops gracefully (they appear as looping arrows on the
--   node, or can be filtered out with G.remove_edges_from(nx.selfloop_edges(G))).
--   The attrs carry the real payload: rank and closed_repo_count.
-- ============================================================================

WITH

-- All (user, repo) pairs where the user has at least one 'closed' edge
-- pointing to an artifact that the repo contains.
user_closed_repos AS (
    SELECT DISTINCT
        ue.src_id AS user_id,
        ce.src_id AS repo_id
    FROM {{ source('hin', 'active_edges') }} AS ue
    JOIN {{ source('hin', 'active_edges') }} AS ce
        ON  ce.dst_id  = ue.dst_id    -- same artifact
    WHERE ue.type = 'closed'
      AND ce.type = 'contains'
),

-- Count distinct repos per user, rank them, keep only the top 20.
-- QUALIFY filters on window functions without a subquery.
ranked AS (
    SELECT
        user_id,
        COUNT(DISTINCT repo_id)                                   AS closed_repo_count,
        ROW_NUMBER() OVER (ORDER BY COUNT(DISTINCT repo_id) DESC) AS rank
    FROM user_closed_repos
    GROUP BY user_id
    QUALIFY rank <= 20
)

SELECT
    user_id        AS src_id,
    'user'         AS src_type,
    user_id        AS dst_id,        -- self-loop: same user on both ends
    'user'         AS dst_type,
    'top_author'   AS edge_type,
    to_json({
        'rank':         rank,
        'closed_repos': closed_repo_count
    })             AS attrs
FROM ranked
ORDER BY rank
