#!/usr/bin/env bash
# Constrained dry run for Laptop A: 5 well-known repos x 1 week (2023-01-01..2023-01-08).
# Verifies: data lands in SQLite, dates are inside the window, all progress rows are 'done',
# and a second run is a no-op (resumability).
#
# Usage:
#   GH_TOKEN_1=ghp_yourtoken ./test-laptopA.sh
#
# Run from the mining/ directory.

set -euo pipefail

if [ -z "${GH_TOKEN_1:-}" ]; then
  echo "ERROR: set GH_TOKEN_1=<github_pat> in env" >&2
  exit 1
fi

cd "$(dirname "$0")"

TEST_DB="mining_test.db"
TEST_REPOS="test_repos.jsonl"
DATE_FROM="2023-01-01"
DATE_TO="2023-01-08"
RUN1_LOG="logs/test_run1.log"
RUN2_LOG="logs/test_run2.log"

mkdir -p logs
rm -f "$TEST_DB" "$TEST_REPOS" "$RUN1_LOG" "$RUN2_LOG"

echo "==> [1/5] Building test_repos.jsonl from GitHub API"
node - <<'NODE_EOF'
import fs from 'node:fs';
import axios from 'axios';
const token = process.env.GH_TOKEN_1;
const slugs = [
  'facebook/react',
  'vercel/next.js',
  'microsoft/vscode',
  'kubernetes/kubernetes',
  'pytorch/pytorch',
];
const out = fs.createWriteStream('test_repos.jsonl');
for (const slug of slugs) {
  const r = await axios.get(`https://api.github.com/repos/${slug}`, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github.v3+json' },
  });
  const item = r.data;
  out.write(JSON.stringify({
    id: item.id,
    full_name: item.full_name,
    owner: item.owner?.login,
    name: item.name,
    stars: item.stargazers_count,
    language: item.language,
    license: item.license?.spdx_id,
    default_branch: item.default_branch,
    created_at: item.created_at,
    pushed_at: item.pushed_at,
    archived: item.archived ? 1 : 0,
    fork: item.fork ? 1 : 0,
  }) + '\n');
  console.log(`  - ${item.full_name} (id=${item.id}, stars=${item.stargazers_count})`);
}
out.end();
NODE_EOF

echo
echo "==> [2/5] First mining run (LAPTOP_ID=test, ${DATE_FROM}..${DATE_TO}, 5 repos)"
LAPTOP_ID=test \
DATE_FROM="$DATE_FROM" \
DATE_TO="$DATE_TO" \
REPOS_FILE="$TEST_REPOS" \
REPO_LIMIT=5 \
WATCH_INTERVAL_MS=5000 \
GH_TOKEN_1="$GH_TOKEN_1" \
  node src/mine-window.js | tee "$RUN1_LOG"

echo
echo "==> [3/5] Asserting data + window + progress"
node - <<NODE_EOF
import Database from 'better-sqlite3';
const db = new Database('$TEST_DB', { readonly: true });
const reposCount   = db.prepare('SELECT COUNT(*) c FROM repos').get().c;
const prsCount     = db.prepare('SELECT COUNT(*) c FROM prs').get().c;
const commitsCount = db.prepare('SELECT COUNT(*) c FROM commits').get().c;
const progressRows = db.prepare('SELECT status, COUNT(*) c FROM progress GROUP BY status').all();
const prDates      = db.prepare('SELECT MIN(created_at) lo, MAX(created_at) hi FROM prs').get();
const commitDates  = db.prepare('SELECT MIN(committer_date) lo, MAX(committer_date) hi FROM commits').get();
console.log('  counts:', { repos: reposCount, prs: prsCount, commits: commitsCount });
console.log('  progress:', progressRows);
console.log('  pr   dates:', prDates);
console.log('  commit dates:', commitDates);

let ok = true;
if (reposCount !== 5) { console.error('  FAIL: expected 5 repos'); ok = false; }
if (prsCount === 0)   { console.error('  FAIL: no PRs ingested (window may legitimately be quiet, but 5 mega-repos in a week should have many)'); ok = false; }
if (commitsCount === 0) { console.error('  FAIL: no commits ingested'); ok = false; }
const allDone = progressRows.every(r => r.status === 'done');
const expectedProgress = 5 * 2; // 5 repos x {pr, commit} (1 month covers the week)
const totalProgress = progressRows.reduce((a, r) => a + r.c, 0);
if (!allDone || totalProgress !== expectedProgress) {
  console.error(\`  FAIL: progress should be \${expectedProgress} rows all 'done'; got \${totalProgress}, statuses=\${JSON.stringify(progressRows)}\`);
  ok = false;
}
if (prsCount > 0 && (prDates.lo < '$DATE_FROM' || prDates.hi >= '$DATE_TO')) {
  console.error(\`  FAIL: PR dates outside [$DATE_FROM, $DATE_TO): \${JSON.stringify(prDates)}\`);
  ok = false;
}
if (commitsCount > 0 && (commitDates.lo < '${DATE_FROM}T00:00:00Z' || commitDates.hi >= '${DATE_TO}T00:00:00Z')) {
  console.error(\`  FAIL: commit dates outside window: \${JSON.stringify(commitDates)}\`);
  ok = false;
}
db.close();
if (!ok) process.exit(1);
console.log('  OK');
NODE_EOF

echo
echo "==> [4/5] Second mining run (must be a no-op — resumability check)"
LAPTOP_ID=test \
DATE_FROM="$DATE_FROM" \
DATE_TO="$DATE_TO" \
REPOS_FILE="$TEST_REPOS" \
REPO_LIMIT=5 \
WATCH_INTERVAL_MS=5000 \
GH_TOKEN_1="$GH_TOKEN_1" \
  node src/mine-window.js | tee "$RUN2_LOG"

if grep -q "scheduled 0 (repo,month,kind) streams" "$RUN2_LOG"; then
  echo "  OK: second run scheduled 0 streams"
else
  echo "  FAIL: second run scheduled non-zero streams (resumability broken)" >&2
  grep "scheduled" "$RUN2_LOG" >&2 || true
  exit 1
fi

echo
echo "==> [5/5] Cleanup"
rm -f "$TEST_DB" "$TEST_REPOS"
echo "  removed $TEST_DB and $TEST_REPOS"

echo
echo "All Laptop A test assertions passed."
