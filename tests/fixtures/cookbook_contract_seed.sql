INSERT INTO contract_accounts (dataset_id, account_key, platform, github_id, login, account_type, is_bot, observed_at, adapter_run_id)
VALUES
  ('$DATASET_ID', 'gh:user:1', 'github', 1, 'alice', 'human', false, TIMESTAMP '2024-01-01', '$DATASET_ID'),
  ('$DATASET_ID', 'gh:user:2', 'github', 2, 'bob', 'human', false, TIMESTAMP '2024-01-01', '$DATASET_ID'),
  ('$DATASET_ID', 'gh:user:3', 'github', 3, 'carol', 'human', false, TIMESTAMP '2024-01-01', '$DATASET_ID');

INSERT INTO contract_repositories (dataset_id, repo_key, platform, github_id, full_name, name, is_fork, observed_at, adapter_run_id)
VALUES
  ('$DATASET_ID', 'gh:repo:10', 'github', 10, 'org/repo', 'repo', false, TIMESTAMP '2024-01-01', '$DATASET_ID'),
  ('$DATASET_ID', 'gh:repo:11', 'github', 11, 'alice/repo', 'repo', true, TIMESTAMP '2024-01-01', '$DATASET_ID');

INSERT INTO contract_artifacts (dataset_id, artifact_key, platform, artifact_type, repo_key, title, created_at, observed_at, adapter_run_id)
VALUES
  ('$DATASET_ID', 'gh:artifact:commit:c1', 'github', 'commit', 'gh:repo:10', 'commit c1', TIMESTAMP '2024-01-02', TIMESTAMP '2024-01-02', '$DATASET_ID'),
  ('$DATASET_ID', 'gh:artifact:file:src/app.py', 'github', 'file', 'gh:repo:10', 'src/app.py', TIMESTAMP '2024-01-02', TIMESTAMP '2024-01-02', '$DATASET_ID'),
  ('$DATASET_ID', 'gh:artifact:issue:1', 'github', 'issue', 'gh:repo:10', 'issue 1', TIMESTAMP '2024-01-03', TIMESTAMP '2024-01-03', '$DATASET_ID'),
  ('$DATASET_ID', 'gh:artifact:issue:2', 'github', 'issue', 'gh:repo:10', 'issue 2', TIMESTAMP '2024-01-03', TIMESTAMP '2024-01-03', '$DATASET_ID'),
  ('$DATASET_ID', 'gh:artifact:comment:1', 'github', 'comment', 'gh:repo:10', 'comment 1', TIMESTAMP '2024-01-04', TIMESTAMP '2024-01-04', '$DATASET_ID');

INSERT INTO contract_relations (
  dataset_id, relation_key, source_node_key, source_node_type, target_node_key, target_node_type,
  relation_type, relation_subtype, directed, occurred_at, observed_at, event_count, weight,
  source_record_id, source_table, adapter_run_id, properties
)
VALUES
  ('$DATASET_ID', 'rel:follow:1:2', 'gh:user:1', 'account', 'gh:user:2', 'account', 'follows', null, true, TIMESTAMP '2024-01-01', TIMESTAMP '2024-01-01', 1, 1.0, 'follow-1', 'synthetic', '$DATASET_ID', '{}'),
  ('$DATASET_ID', 'rel:watch:1:10', 'gh:user:1', 'account', 'gh:repo:10', 'repo', 'watches', null, true, TIMESTAMP '2024-01-01', TIMESTAMP '2024-01-01', 1, 1.0, 'watch-1', 'synthetic', '$DATASET_ID', '{}'),
  ('$DATASET_ID', 'rel:author:1:c1', 'gh:user:1', 'account', 'gh:artifact:commit:c1', 'artifact', 'authored', null, true, TIMESTAMP '2024-01-02', TIMESTAMP '2024-01-02', 1, 1.0, 'commit-1', 'synthetic', '$DATASET_ID', '{}'),
  ('$DATASET_ID', 'rel:coauthor:2:c1', 'gh:user:2', 'account', 'gh:artifact:commit:c1', 'artifact', 'coauthored', null, true, TIMESTAMP '2024-01-02', TIMESTAMP '2024-01-02', 1, 1.0, 'commit-2', 'synthetic', '$DATASET_ID', '{}'),
  ('$DATASET_ID', 'rel:touch:1:file', 'gh:user:1', 'account', 'gh:artifact:file:src/app.py', 'artifact', 'touched', null, true, TIMESTAMP '2024-01-02', TIMESTAMP '2024-01-02', 1, 1.0, 'touch-1', 'synthetic', '$DATASET_ID', '{}'),
  ('$DATASET_ID', 'rel:touch:3:file', 'gh:user:3', 'account', 'gh:artifact:file:src/app.py', 'artifact', 'touched', null, true, TIMESTAMP '2024-01-02', TIMESTAMP '2024-01-02', 1, 1.0, 'touch-3', 'synthetic', '$DATASET_ID', '{}'),
  ('$DATASET_ID', 'rel:ref:issue1:issue2', 'gh:artifact:issue:1', 'artifact', 'gh:artifact:issue:2', 'artifact', 'references', null, true, TIMESTAMP '2024-01-03', TIMESTAMP '2024-01-03', 1, 1.0, 'ref-1', 'synthetic', '$DATASET_ID', '{}'),
  ('$DATASET_ID', 'rel:author:1:comment', 'gh:user:1', 'account', 'gh:artifact:comment:1', 'artifact', 'authored', null, true, TIMESTAMP '2024-01-04', TIMESTAMP '2024-01-04', 1, 1.0, 'comment-1', 'synthetic', '$DATASET_ID', '{}'),
  ('$DATASET_ID', 'rel:mention:comment:2', 'gh:artifact:comment:1', 'artifact', 'gh:user:2', 'account', 'mentions', null, true, TIMESTAMP '2024-01-04', TIMESTAMP '2024-01-04', 1, 1.0, 'mention-1', 'synthetic', '$DATASET_ID', '{}');

INSERT INTO contract_adapter_manifest (
  adapter_run_id, adapter_name, adapter_version, source_name, extracted_at,
  has_accounts, has_repositories, has_commits, has_file_touches, has_line_touches,
  has_pull_requests, has_pr_reviews, has_issues, has_comments, has_stars, has_watches,
  has_forks, has_follows, has_mentions, has_artifact_refs, coverage_start, coverage_end, notes
)
VALUES (
  '$DATASET_ID', 'synthetic-cookbook-contract', '0.1.0', 'tests/fixtures/cookbook_contract_seed.sql', now(),
  true, true, true, true, false,
  false, false, true, true, false, true,
  false, true, true, true, TIMESTAMP '2024-01-01', TIMESTAMP '2024-01-04',
  'Minimal contract-level fixture for cookbook recipes unsupported by the NumFocus adapter.'
);
