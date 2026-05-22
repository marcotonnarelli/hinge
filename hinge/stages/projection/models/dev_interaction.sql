-- ============================================================================
-- dev_interaction.sql  —  developer collaboration network
--
-- READ THIS BEFORE WRITING A NEW PROJECTION. Every .sql file in this folder
-- must satisfy the contract documented in the header below.
-- ============================================================================
--
-- WHAT THIS PROJECTION DOES
--   Builds an undirected user-to-user "collaborator" graph. Two developers
--   are collaborators if they both made code contributions to the same
--   repository. A contribution is any of: opening a PR or issue, reviewing,
--   merging, commenting on a PR or issue, or pushing commits.
--
--   "Shared a repo" is derived from the HIN structure using two hops:
--     user → <contribution edge> → artifact ← contains ← repo
--   The self-join on repo then finds all pairs of contributors per repo.
--
--   Starring, forking, and wiki edits are intentionally excluded — they
--   do not constitute active development collaboration.
--
-- ─── INPUT CONTRACT ─────────────────────────────────────────────────────────
--   Every projection reads from exactly two dbt sources:
--
--     {{ source('hin', 'active_nodes') }}   columns: type, id, ts, attrs
--     {{ source('hin', 'active_edges') }}   columns: type, src_id, dst_id, ts, attrs
--
--   The store (DuckDBStore) rewrites these views before each projection run
--   to point at the requested dataset_id. Do NOT touch any other table.
--   If you need helper logic, put it in a CTE — do not create intermediate
--   dbt models unless the projection genuinely needs to be split.
--
-- ─── OUTPUT CONTRACT ────────────────────────────────────────────────────────
--   Every projection model MUST produce a table with exactly these columns,
--   in this order, with these types:
--
--     src_id     TEXT     stable node id (e.g. 'user:torvalds')
--     src_type   TEXT     node label — any string; the vocabulary is open
--     dst_id     TEXT     stable node id
--     dst_type   TEXT     node label
--     edge_type  TEXT     edge label. Projections may introduce labels not
--                         listed in types.yaml; downstream stages treat
--                         labels as opaque strings.
--     attrs      JSON     any extra payload — weights, timestamps, counts.
--                         Use JSON-encoded objects, not raw maps.
--
--   The DbtProjection stage discovers the result table by its dbt model
--   name (this file's stem, `dev_interaction`). dbt's default
--   materialisation is `table`, set globally in dbt_project.yml.
--
-- ─── HOW TO REGISTER THIS FILE ──────────────────────────────────────────────
--   1. Save the .sql file in hinge/stages/projection/models/<name>.sql.
--   2. Add a sibling Python module under
--      hinge/stages/projection/specs/<name>.py exposing a `SPEC` constant
--      (see specs/dev_interaction.py for the template).
--   3. Register the entry-point in pyproject.toml under
--      [project.entry-points."hinge.projection_specs"].
--   4. Write a test in tests/stages/projection/test_<name>.py against a
--      seeded :memory: DuckDB fixture.
--
-- ─── PARAMETERS ─────────────────────────────────────────────────────────────
--   Projections can accept run-time parameters via dbt vars (passed by
--   DbtProjection from the ProjectionParams object). Read them with
--   {{ var('name', default) }}.
--   This template ignores all vars — keep it that way until a real use case
--   appears.
-- ============================================================================

WITH

-- (user, repo) pairs: user made at least one code contribution to that repo.
-- The two-hop path is: user -[contribution]-> artifact <-[contains]- repo.
-- We join on artifact id (ce.dst_id = ue.dst_id) to traverse the HIN.
user_repo AS (
    SELECT DISTINCT
        ue.src_id AS user_id,
        ce.src_id AS repo_id
    FROM {{ source('hin', 'active_edges') }} AS ue
    JOIN {{ source('hin', 'active_edges') }} AS ce
        ON ce.dst_id = ue.dst_id
    WHERE ue.type IN (
              'opened',
              'reviewed',
              'merged',
              'commented_on',
              'review_commented_on',
              'pushed'
          )
      AND ce.type = 'contains'
),

-- Collaborator pairs: users who share at least one repo.
-- src_id < dst_id eliminates both self-edges and mirrored duplicates,
-- making the relation undirected (one row per unordered pair).
collaborators AS (
    SELECT
        a.user_id                       AS src_id,
        b.user_id                       AS dst_id,
        COUNT(DISTINCT a.repo_id)       AS shared_repo_count,
        list_distinct(list(a.repo_id))  AS shared_repos
    FROM user_repo AS a
    JOIN user_repo AS b
        ON  a.repo_id  = b.repo_id
        AND a.user_id  < b.user_id
    GROUP BY a.user_id, b.user_id
)

SELECT
    src_id,
    'user'                                     AS src_type,
    dst_id,
    'user'                                     AS dst_type,
    'collaborates_with'                        AS edge_type,
    to_json({
        'shared_repos': shared_repo_count,
        'repos':        shared_repos
    })                                         AS attrs
FROM collaborators
