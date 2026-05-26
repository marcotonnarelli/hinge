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
--     {{ ref('hin_nodes') }}  canonical HIN node model
--     {{ ref('hin_edges') }}  canonical HIN edge model
--
--   The store (DuckDBStore) rewrites these views before each projection run
--   to point at the requested dataset_id. Do NOT touch any other table.
--   If you need helper logic, put it in a CTE — do not create intermediate
--   dbt models unless the projection genuinely needs to be split.
--
-- ─── OUTPUT CONTRACT ────────────────────────────────────────────────────────
--   Every projection model should use the network_edges macro. It emits the
--   standard cookbook shape:
--
--     recipe_name, recipe_version,
--     source_node_id, source_node_type, target_node_id, target_node_type,
--     directed, edge_type,
--     weight, weight_kind, n_contexts, n_events,
--     first_seen_at, last_seen_at, time_bin, bot_policy, properties
--
--   DbtProjection converts this richer table into TypedEdge objects for the
--   current exporter API, merging standard fields and properties into attrs.
--
--   The DbtProjection stage discovers the result table by its dbt model
--   name (this file's stem, `dev_interaction`). dbt's default
--   materialisation is `table`, set globally in dbt_project.yml.
--
-- ─── HOW TO REGISTER THIS FILE ──────────────────────────────────────────────
--   1. Save the .sql file in hinge/dbt/models/networks/<name>.sql.
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

{{ assert_recipe_supported(
    'dev_interaction',
    ['has_pull_requests', 'has_pr_reviews', 'has_issues', 'has_comments']
) }}

WITH

-- Collaborator pairs: users who share at least one active development repo.
-- This is the generic bipartite projection pattern: user -> repo <- user.
collaborators AS (
    {{ project_bipartite(
        incidence_relation=ref('int_developer_repo_affiliation'),
        left_col='user_node_id',
        right_col='repo_node_id',
        directed=false,
        weight_mode='shared_count'
    ) }}
)

{{ network_edges(
    relation='collaborators',
    recipe_name='dev_interaction',
    source_node_id='source_node_id',
    source_node_type="'user'",
    target_node_id='target_node_id',
    target_node_type="'user'",
    edge_type="'collaborates_with'",
    directed='false',
    weight='weight',
    weight_kind='weight_kind',
    n_contexts='n_contexts',
    first_seen_at='first_seen_at',
    last_seen_at='last_seen_at',
    properties="to_json({'shared_repos': n_contexts, 'repos': context_node_ids})"
) }}
