"""Example DuckDB contract-table adapter for the NumFocus Actions JSONL format.

This module is deliberately source-specific: it knows the JSON paths in the
NumFocus scrape (``actor.login``, ``details.pull_request.id``, etc.) and maps
those fields into the source-agnostic ``contract_*`` tables owned by
``DuckDBStore``.

The reusable/core layer starts after this adapter has populated contract tables:
``contract_*`` -> ``hin_nodes`` / ``hin_edges`` -> dbt projections. New data
sources should copy this shape, not this source mapping.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb


def ingest(
    conn: duckdb.DuckDBPyConnection,
    dataset_id: str,
    path: str | Path,
    *,
    limit: int | None = None,
) -> tuple[int, int, int]:
    source_path = str(Path(path))
    row_limit_sql = "" if limit is None else f" LIMIT {int(limit)}"
    conn.execute("DROP TABLE IF EXISTS _numfocus_raw")
    conn.execute("DROP TABLE IF EXISTS _numfocus_flat")
    conn.execute(
        "CREATE TEMP TABLE _numfocus_raw AS "
        "SELECT row_number() OVER () AS source_line, json "
        "FROM read_json_objects(?)" + row_limit_sql,
        [source_path],
    )
    conn.execute(
        "CREATE TEMP TABLE _numfocus_flat AS "
        "SELECT "
        "  json, source_line, "
        "  json_extract_string(json, '$.action') AS action, "
        "  json_extract_string(json, '$.event_id') AS event_id, "
        "  try_cast(replace(json_extract_string(json, '$.date'), 'Z', '') AS TIMESTAMP) AS occurred_at, "
        "  try_cast(json_extract_string(json, '$.actor.id') AS BIGINT) AS actor_id, "
        "  json_extract_string(json, '$.actor.login') AS actor_login, "
        "  try_cast(json_extract_string(json, '$.repository.id') AS BIGINT) AS repo_id, "
        "  json_extract_string(json, '$.repository.name') AS repo_full_name, "
        "  json_extract_string(json, '$.repository.organisation') AS org_login, "
        "  try_cast(json_extract_string(json, '$.repository.organisation_id') AS BIGINT) AS org_id, "
        "  try_cast(json_extract_string(json, '$.details.pull_request.id') AS BIGINT) AS pr_id, "
        "  try_cast(json_extract_string(json, '$.details.pull_request.number') AS INTEGER) AS pr_number, "
        "  json_extract_string(json, '$.details.pull_request.title') AS pr_title, "
        "  json_extract_string(json, '$.details.pull_request.state') AS pr_state, "
        "  try_cast(json_extract_string(json, '$.details.pull_request.author.id') AS BIGINT) AS pr_author_id, "
        "  json_extract_string(json, '$.details.pull_request.author.login') AS pr_author_login, "
        "  try_cast(replace(json_extract_string(json, '$.details.pull_request.created_date'), 'Z', '') AS TIMESTAMP) AS pr_created_at, "
        "  try_cast(replace(json_extract_string(json, '$.details.pull_request.updated_date'), 'Z', '') AS TIMESTAMP) AS pr_updated_at, "
        "  try_cast(replace(json_extract_string(json, '$.details.pull_request.closed_date'), 'Z', '') AS TIMESTAMP) AS pr_closed_at, "
        "  try_cast(replace(json_extract_string(json, '$.details.pull_request.merged_date'), 'Z', '') AS TIMESTAMP) AS pr_merged_at, "
        "  try_cast(json_extract_string(json, '$.details.review.id') AS BIGINT) AS review_id, "
        "  try_cast(replace(json_extract_string(json, '$.details.review.submitted_date'), 'Z', '') AS TIMESTAMP) AS review_submitted_at, "
        "  try_cast(replace(json_extract_string(json, '$.details.review.updated_date'), 'Z', '') AS TIMESTAMP) AS review_updated_at, "
        "  try_cast(json_extract_string(json, '$.details.comment.id') AS BIGINT) AS comment_id, "
        "  try_cast(json_extract_string(json, '$.details.comment.position') AS INTEGER) AS comment_position, "
        "  try_cast(json_extract_string(json, '$.details.comment.parent_comment_id') AS BIGINT) AS parent_comment_id, "
        "  try_cast(json_extract_string(json, '$.details.issue.id') AS BIGINT) AS issue_id, "
        "  try_cast(json_extract_string(json, '$.details.issue.number') AS INTEGER) AS issue_number, "
        "  json_extract_string(json, '$.details.issue.title') AS issue_title, "
        "  json_extract_string(json, '$.details.issue.state') AS issue_state, "
        "  try_cast(json_extract_string(json, '$.details.issue.author.id') AS BIGINT) AS issue_author_id, "
        "  json_extract_string(json, '$.details.issue.author.login') AS issue_author_login, "
        "  try_cast(replace(json_extract_string(json, '$.details.issue.created_date'), 'Z', '') AS TIMESTAMP) AS issue_created_at, "
        "  try_cast(replace(json_extract_string(json, '$.details.issue.updated_date'), 'Z', '') AS TIMESTAMP) AS issue_updated_at, "
        "  try_cast(replace(json_extract_string(json, '$.details.issue.closed_date'), 'Z', '') AS TIMESTAMP) AS issue_closed_at, "
        "  json_extract_string(json, '$.details.push.id') AS push_id, "
        "  json_extract_string(json, '$.details.push.ref') AS push_ref, "
        "  try_cast(json_extract_string(json, '$.details.push.commits') AS INTEGER) AS push_commits, "
        "  try_cast(json_extract_string(json, '$.details.release.id') AS BIGINT) AS release_id, "
        "  json_extract_string(json, '$.details.release.name') AS release_name, "
        "  json_extract_string(json, '$.details.release.tag') AS release_tag, "
        "  try_cast(json_extract_string(json, '$.details.release.author.id') AS BIGINT) AS release_author_id, "
        "  json_extract_string(json, '$.details.release.author.login') AS release_author_login, "
        "  try_cast(replace(json_extract_string(json, '$.details.release.created_date'), 'Z', '') AS TIMESTAMP) AS release_created_at, "
        "  try_cast(json_extract_string(json, '$.details.fork.id') AS BIGINT) AS fork_repo_id, "
        "  json_extract_string(json, '$.details.fork.name') AS fork_full_name "
        "FROM _numfocus_raw"
    )
    _insert_contract_accounts(conn, dataset_id)
    _insert_contract_repositories(conn, dataset_id)
    _insert_contract_artifacts(conn, dataset_id)
    _insert_contract_relations(conn, dataset_id)
    _insert_contract_manifest(conn, dataset_id, source_path)
    _backfill_graph_from_hin(conn, dataset_id)
    record_count = _scalar(conn.execute("SELECT COUNT(*) FROM _numfocus_flat").fetchone())
    node_count = _scalar(
        conn.execute("SELECT COUNT(*) FROM nodes WHERE dataset_id = ?", [dataset_id]).fetchone()
    )
    edge_count = _scalar(
        conn.execute("SELECT COUNT(*) FROM edges WHERE dataset_id = ?", [dataset_id]).fetchone()
    )
    return int(record_count), int(node_count), int(edge_count)


def _scalar(row: tuple[Any, ...] | None) -> Any:
    if row is None:
        raise RuntimeError("expected one row from scalar query, got none")
    return row[0]


def _insert_contract_accounts(conn: duckdb.DuckDBPyConnection, dataset_id: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO contract_accounts "
        "SELECT ?, account_key, 'github', github_id, login, account_type, is_bot, "
        "       CASE WHEN is_bot THEN 0.8 ELSE 0.0 END, 'heuristic', NULL, NULL, "
        "       to_json({'login': login, 'github_id': github_id}), observed_at, ? "
        "FROM ("
        "  SELECT DISTINCT "
        "    'gh:user:' || coalesce(cast(actor_id AS TEXT), actor_login) AS account_key,"
        "    actor_id AS github_id, actor_login AS login,"
        "    CASE WHEN regexp_matches(lower(actor_login), '(\\[bot\\]|_bot)$') THEN 'bot' ELSE 'human' END AS account_type,"
        "    regexp_matches(lower(actor_login), '(\\[bot\\]|_bot)$') AS is_bot, occurred_at AS observed_at "
        "  FROM _numfocus_flat WHERE actor_login IS NOT NULL "
        "  UNION "
        "  SELECT DISTINCT 'gh:org:' || coalesce(cast(org_id AS TEXT), org_login), org_id, org_login,"
        "    'organization', FALSE, occurred_at "
        "  FROM _numfocus_flat WHERE org_login IS NOT NULL "
        "  UNION "
        "  SELECT DISTINCT 'gh:user:' || coalesce(cast(pr_author_id AS TEXT), pr_author_login),"
        "    pr_author_id, pr_author_login,"
        "    CASE WHEN regexp_matches(lower(pr_author_login), '(\\[bot\\]|_bot)$') THEN 'bot' ELSE 'human' END,"
        "    regexp_matches(lower(pr_author_login), '(\\[bot\\]|_bot)$'), occurred_at "
        "  FROM _numfocus_flat WHERE pr_author_login IS NOT NULL "
        "  UNION "
        "  SELECT DISTINCT 'gh:user:' || coalesce(cast(issue_author_id AS TEXT), issue_author_login),"
        "    issue_author_id, issue_author_login,"
        "    CASE WHEN regexp_matches(lower(issue_author_login), '(\\[bot\\]|_bot)$') THEN 'bot' ELSE 'human' END,"
        "    regexp_matches(lower(issue_author_login), '(\\[bot\\]|_bot)$'), occurred_at "
        "  FROM _numfocus_flat WHERE issue_author_login IS NOT NULL "
        "  UNION "
        "  SELECT DISTINCT 'gh:user:' || coalesce(cast(release_author_id AS TEXT), release_author_login),"
        "    release_author_id, release_author_login,"
        "    CASE WHEN regexp_matches(lower(release_author_login), '(\\[bot\\]|_bot)$') THEN 'bot' ELSE 'human' END,"
        "    regexp_matches(lower(release_author_login), '(\\[bot\\]|_bot)$'), occurred_at "
        "  FROM _numfocus_flat WHERE release_author_login IS NOT NULL "
        ") a(account_key, github_id, login, account_type, is_bot, observed_at)",
        [dataset_id, dataset_id],
    )


def _insert_contract_repositories(conn: duckdb.DuckDBPyConnection, dataset_id: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO contract_repositories "
        "SELECT ?, repo_key, 'github', github_id, full_name, owner_account_key, name, NULL, NULL,"
        "       is_fork, forked_from_repo_key, NULL, NULL, NULL, NULL, NULL, NULL,"
        "       to_json({'full_name': full_name, 'github_id': github_id}), observed_at, ? "
        "FROM ("
        "  SELECT DISTINCT "
        "    'gh:repo:' || coalesce(cast(repo_id AS TEXT), repo_full_name) AS repo_key, repo_id AS github_id,"
        "    repo_full_name AS full_name, 'gh:org:' || coalesce(cast(org_id AS TEXT), org_login) AS owner_account_key,"
        "    regexp_replace(repo_full_name, '^.*/', '') AS name, FALSE AS is_fork, NULL AS forked_from_repo_key, occurred_at AS observed_at "
        "  FROM _numfocus_flat WHERE repo_full_name IS NOT NULL "
        "  UNION "
        "  SELECT DISTINCT "
        "    'gh:repo:' || coalesce(cast(fork_repo_id AS TEXT), fork_full_name), fork_repo_id, fork_full_name, NULL,"
        "    regexp_replace(fork_full_name, '^.*/', ''), TRUE,"
        "    'gh:repo:' || coalesce(cast(repo_id AS TEXT), repo_full_name), occurred_at "
        "  FROM _numfocus_flat WHERE fork_full_name IS NOT NULL OR fork_repo_id IS NOT NULL "
        ") r(repo_key, github_id, full_name, owner_account_key, name, is_fork, forked_from_repo_key, observed_at)",
        [dataset_id, dataset_id],
    )


def _insert_contract_artifacts(conn: duckdb.DuckDBPyConnection, dataset_id: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO contract_artifacts "
        "WITH base AS ("
        "  SELECT *, 'gh:repo:' || coalesce(cast(repo_id AS TEXT), repo_full_name) AS repo_key "
        "  FROM _numfocus_flat"
        "), artifacts AS ("
        "  SELECT 'gh:artifact:pull_request:' || coalesce(cast(pr_id AS TEXT), repo_key || ':' || cast(pr_number AS TEXT)) AS artifact_key,"
        "    'pull_request' AS artifact_type, repo_key, NULL AS parent_artifact_key, pr_id AS github_id, pr_number AS number, NULL AS sha,"
        "    pr_title AS title, pr_state AS state, pr_created_at AS created_at, pr_updated_at AS updated_at, pr_closed_at AS closed_at, pr_merged_at AS merged_at,"
        "    json_extract(json, '$.details.pull_request') AS artifact_json, occurred_at AS observed_at "
        "  FROM base WHERE pr_id IS NOT NULL OR pr_number IS NOT NULL "
        "  UNION ALL "
        "  SELECT 'gh:artifact:issue:' || coalesce(cast(issue_id AS TEXT), repo_key || ':' || cast(issue_number AS TEXT)),"
        "    'issue', repo_key, NULL, issue_id, issue_number, NULL, issue_title, issue_state, issue_created_at, issue_updated_at, issue_closed_at, NULL,"
        "    json_extract(json, '$.details.issue'), occurred_at "
        "  FROM base WHERE issue_id IS NOT NULL OR issue_number IS NOT NULL "
        "  UNION ALL "
        "  SELECT 'gh:artifact:push:' || coalesce(cast(push_id AS TEXT), event_id),"
        "    'push', repo_key, NULL, try_cast(push_id AS BIGINT), NULL, NULL, push_ref, NULL, occurred_at, occurred_at, NULL, NULL,"
        "    json_extract(json, '$.details.push'), occurred_at "
        "  FROM base WHERE action = 'PushCommits' AND (push_id IS NOT NULL OR event_id IS NOT NULL) "
        "  UNION ALL "
        "  SELECT 'gh:artifact:release:' || coalesce(cast(release_id AS TEXT), repo_key || ':' || release_tag),"
        "    'release', repo_key, NULL, release_id, NULL, release_tag, release_name, NULL, release_created_at, NULL, NULL, NULL,"
        "    json_extract(json, '$.details.release'), occurred_at "
        "  FROM base WHERE release_id IS NOT NULL OR release_tag IS NOT NULL "
        "  UNION ALL "
        "  SELECT 'gh:artifact:comment:' || cast(comment_id AS TEXT),"
        "    CASE WHEN action = 'CreateIssueComment' THEN 'issue_comment' WHEN action = 'CreatePullRequestReviewComment' THEN 'review_comment' ELSE 'comment' END,"
        "    repo_key, coalesce("
        "      CASE WHEN pr_id IS NOT NULL OR pr_number IS NOT NULL THEN 'gh:artifact:pull_request:' || coalesce(cast(pr_id AS TEXT), repo_key || ':' || cast(pr_number AS TEXT)) END,"
        "      CASE WHEN issue_id IS NOT NULL OR issue_number IS NOT NULL THEN 'gh:artifact:issue:' || coalesce(cast(issue_id AS TEXT), repo_key || ':' || cast(issue_number AS TEXT)) END"
        "    ), comment_id, NULL, NULL, NULL, NULL, occurred_at, NULL, NULL, NULL,"
        "    json_extract(json, '$.details.comment'), occurred_at "
        "  FROM base WHERE comment_id IS NOT NULL "
        "  UNION ALL "
        "  SELECT 'gh:artifact:review:' || cast(review_id AS TEXT),"
        "    'review', repo_key, 'gh:artifact:pull_request:' || coalesce(cast(pr_id AS TEXT), repo_key || ':' || cast(pr_number AS TEXT)),"
        "    review_id, NULL, NULL, NULL, NULL, review_submitted_at, review_updated_at, NULL, NULL,"
        "    json_extract(json, '$.details.review'), occurred_at "
        "  FROM base WHERE review_id IS NOT NULL "
        "  UNION ALL "
        "  SELECT 'gh:artifact:wiki_page:' || event_id, 'wiki_page', repo_key, NULL, NULL, NULL, NULL, 'wiki edit', NULL, occurred_at, NULL, NULL, NULL,"
        "    json_extract(json, '$.details.pages'), occurred_at "
        "  FROM base WHERE action = 'ManageWikiPage' AND event_id IS NOT NULL "
        ") "
        "SELECT ?, artifact_key, 'github', artifact_type, repo_key, parent_artifact_key, github_id, NULL, number, sha, NULL,"
        "       title, state, NULL, NULL, NULL, NULL, NULL, NULL, created_at, updated_at, closed_at, merged_at, artifact_json, observed_at, ? "
        "FROM artifacts WHERE artifact_key IS NOT NULL",
        [dataset_id, dataset_id],
    )


def _insert_contract_relations(conn: duckdb.DuckDBPyConnection, dataset_id: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO contract_relations "
        "WITH base AS ("
        "  SELECT *, 'gh:user:' || coalesce(cast(actor_id AS TEXT), actor_login) AS actor_key,"
        "    'gh:repo:' || coalesce(cast(repo_id AS TEXT), repo_full_name) AS repo_key,"
        "    'gh:artifact:pull_request:' || coalesce(cast(pr_id AS TEXT), 'gh:repo:' || coalesce(cast(repo_id AS TEXT), repo_full_name) || ':' || cast(pr_number AS TEXT)) AS pr_key,"
        "    'gh:artifact:issue:' || coalesce(cast(issue_id AS TEXT), 'gh:repo:' || coalesce(cast(repo_id AS TEXT), repo_full_name) || ':' || cast(issue_number AS TEXT)) AS issue_key,"
        "    'gh:artifact:push:' || coalesce(cast(push_id AS TEXT), event_id) AS push_key,"
        "    'gh:artifact:release:' || coalesce(cast(release_id AS TEXT), 'gh:repo:' || coalesce(cast(repo_id AS TEXT), repo_full_name) || ':' || release_tag) AS release_key,"
        "    'gh:repo:' || coalesce(cast(fork_repo_id AS TEXT), fork_full_name) AS fork_key "
        "  FROM _numfocus_flat WHERE actor_login IS NOT NULL"
        "), event_relations AS ("
        "  SELECT 'gh:event:' || event_id || ':actor' AS relation_key, actor_key AS source_node_key, 'account' AS source_node_type,"
        "    CASE WHEN action IN ('StarRepository', 'AddMember') THEN repo_key ELSE "
        "      CASE "
        "        WHEN action IN ('OpenPullRequest','CreatePullRequestReview','CreatePullRequestComment','CreatePullRequestReviewComment','MergePullRequest','ClosePullRequest','ReopenPullRequest') THEN pr_key "
        "        WHEN action IN ('OpenIssue','CreateIssueComment','CloseIssue','ReopenIssue') THEN issue_key "
        "        WHEN action = 'PushCommits' THEN push_key "
        "        WHEN action = 'PublishRelease' THEN release_key "
        "        WHEN action = 'ForkRepository' THEN fork_key "
        "        WHEN action = 'ManageWikiPage' THEN 'gh:artifact:wiki_page:' || event_id "
        "      END END AS target_node_key,"
        "    CASE WHEN action IN ('StarRepository','AddMember','ForkRepository') THEN 'repo' ELSE 'artifact' END AS target_node_type,"
        "    CASE action "
        "      WHEN 'OpenPullRequest' THEN 'opened' WHEN 'OpenIssue' THEN 'opened'"
        "      WHEN 'CreatePullRequestReview' THEN 'reviewed'"
        "      WHEN 'CreatePullRequestComment' THEN 'commented_on' WHEN 'CreateIssueComment' THEN 'commented_on'"
        "      WHEN 'CreatePullRequestReviewComment' THEN 'review_commented_on'"
        "      WHEN 'MergePullRequest' THEN 'merged' WHEN 'ClosePullRequest' THEN 'closed' WHEN 'CloseIssue' THEN 'closed'"
        "      WHEN 'ReopenPullRequest' THEN 'reopened' WHEN 'ReopenIssue' THEN 'reopened'"
        "      WHEN 'PushCommits' THEN 'pushed' WHEN 'StarRepository' THEN 'starred' WHEN 'ForkRepository' THEN 'created_fork'"
        "      WHEN 'PublishRelease' THEN 'released' WHEN 'ManageWikiPage' THEN 'wiki_edited' WHEN 'AddMember' THEN 'member_of'"
        "    END AS relation_type, action AS relation_subtype, occurred_at, event_id, json AS properties "
        "  FROM base WHERE action NOT IN ('CreateBranch','DeleteBranch','CreateTag','DeleteTag','CreateRepository','MakeRepositoryPublic') "
        "), contains_relations AS ("
        "  SELECT DISTINCT 'gh:contains:' || artifact_key AS relation_key, repo_key AS source_node_key, 'repo' AS source_node_type,"
        "    artifact_key AS target_node_key, 'artifact' AS target_node_type, 'contains' AS relation_type, artifact_type AS relation_subtype,"
        "    observed_at AS occurred_at, NULL AS event_id, artifact_json AS properties "
        "  FROM contract_artifacts WHERE dataset_id = ? AND repo_key IS NOT NULL "
        "), parent_relations AS ("
        "  SELECT DISTINCT 'gh:parent:' || parent_artifact_key || ':' || artifact_key AS relation_key, parent_artifact_key, 'artifact',"
        "    artifact_key, 'artifact', 'contains', artifact_type, observed_at, NULL, artifact_json "
        "  FROM contract_artifacts WHERE dataset_id = ? AND parent_artifact_key IS NOT NULL "
        "), fork_relations AS ("
        "  SELECT DISTINCT 'gh:fork_of:' || fork_key || ':' || repo_key, fork_key, 'repo', repo_key, 'repo', 'fork_of', NULL, occurred_at, event_id, json "
        "  FROM base WHERE action = 'ForkRepository' AND fork_key IS NOT NULL AND repo_key IS NOT NULL "
        ") "
        "SELECT ?, relation_key, source_node_key, source_node_type, target_node_key, target_node_type, relation_type, relation_subtype,"
        "       TRUE, occurred_at, occurred_at, NULL, NULL, 1, 1.0, event_id, 'numfocus_actions', ?, properties "
        "FROM (SELECT * FROM event_relations UNION ALL SELECT * FROM contains_relations UNION ALL SELECT * FROM parent_relations UNION ALL SELECT * FROM fork_relations) "
        "WHERE relation_type IS NOT NULL AND target_node_key IS NOT NULL",
        [dataset_id, dataset_id, dataset_id, dataset_id],
    )


def _insert_contract_manifest(
    conn: duckdb.DuckDBPyConnection, dataset_id: str, source_path: str
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO contract_adapter_manifest "
        "SELECT ?, 'numfocus-actions-duckdb', '0.1.0', ?, now(), TRUE, TRUE, TRUE, FALSE, FALSE,"
        "       TRUE, TRUE, TRUE, TRUE, TRUE, FALSE, TRUE, FALSE, FALSE, FALSE,"
        "       min(occurred_at), max(occurred_at), list_distinct(list('gh:repo:' || coalesce(cast(repo_id AS TEXT), repo_full_name))),"
        "       'Example fast DuckDB adapter for NumFocus GH_Actions.jsonl; source-specific, not core HIN logic.' "
        "FROM _numfocus_flat",
        [dataset_id, source_path],
    )


def _backfill_graph_from_hin(conn: duckdb.DuckDBPyConnection, dataset_id: str) -> None:
    conn.execute("DELETE FROM nodes WHERE dataset_id = ?", [dataset_id])
    conn.execute("DELETE FROM edges WHERE dataset_id = ?", [dataset_id])
    conn.execute(
        "INSERT OR REPLACE INTO nodes "
        "SELECT dataset_id, node_type AS type, node_id AS id, coalesce(updated_at, created_at, observed_at) AS ts,"
        "       to_json({'subtype': node_subtype, 'natural_key': natural_key, 'display_name': display_name}) AS attrs "
        "FROM hin_nodes WHERE dataset_id = ?",
        [dataset_id],
    )
    conn.execute(
        "INSERT INTO edges "
        "SELECT dataset_id, edge_type AS type, source_node_id AS src_id, target_node_id AS dst_id, occurred_at AS ts,"
        "       to_json({'subtype': relation_subtype, 'source_record_id': source_record_id, 'weight': weight}) AS attrs "
        "FROM hin_edges WHERE dataset_id = ?",
        [dataset_id],
    )
