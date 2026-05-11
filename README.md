# agentic_mining

Mine GitHub OSS repositories (stars ≥ 1000) for **PRs + commits + repo metadata** between **2022-11-01** (ChatGPT release) and **today** to study how agentic AI is changing code development. Three laptops mine disjoint date windows in parallel, then their per-laptop SQLite databases are merged.

Built on the [poolingh](poolingh/) library, which pools multiple GitHub personal-access tokens and transparently pauses/resumes each one when its rate limit is hit.

---

## Repository layout

```
agentic_mining/
  poolingh/                 vendored upstream library (with its own node_modules)
  mining/                   the mining application
    package.json            npm scripts: discover, mine, merge
    .env.example            template for tokens + window
    src/
      db.js                 SQLite schema + row mappers
      discover-repos.js     Phase 1: enumerate all repos with stars >= MIN_STARS
      mine-window.js        Phase 2: per-laptop PR + commit mining
      merge-dbs.js          Phase 3: combine per-laptop DBs into one
      util/
        star-buckets.js     Sharded star ranges to escape Search API 1000-cap
        month-iter.js       Iterate calendar months over [from, to)
    test-laptopA.sh         Constrained dry run (5 repos x 1 week)
```

`poolingh/src/index.js` is imported directly by `mining/src/*` — no build step.

---

## Why this design

- **GitHub Search API caps each query at 1000 results and 30 req/min/token.** We shard the universe by **(month x repo)** so every query stays well under the cap, every failure is retried at single-month granularity, and each laptop works disjointly with no shared runtime state.
- **Discovery happens once.** Each laptop later reads the same `repos.jsonl` and only fetches PRs/commits in its assigned date window.
- **Resumability via SQLite.** A `progress(repo_id, month, kind, status)` table is updated to `done` only when every page of that stream has been written. Re-running after a crash skips completed work.
- **Raw API JSON is preserved on every row.** New analyses (`Co-Authored-By: Claude` trailers, Copilot/Cursor bot accounts, PR-authorship patterns) can be derived later without re-mining.

---

## Date partition (43 months → 14 / 14 / 15)

Half-open `[DATE_FROM, DATE_TO)` so windows tile without overlap.

| Laptop | DATE_FROM   | DATE_TO     | Months |
|--------|-------------|-------------|--------|
| **A**  | 2022-11-01  | 2024-01-01  | 14     |
| **B**  | 2024-01-01  | 2025-03-01  | 14     |
| **C**  | 2025-03-01  | 2026-06-01  | 15     |

---

## Setup (each laptop)

Prerequisites: Node.js >= 18.

```bash
cd mining
npm install
cp .env.example .env
# Edit .env: set GH_TOKEN_1..3, LAPTOP_ID, DATE_FROM, DATE_TO
```

Generate GitHub PATs at **Settings -> Developer Settings -> Personal access tokens (fine-grained)**. Scope: **Public Repositories (read-only)**. 2-3 tokens per laptop is the sweet spot.

---

## Phase 1 — Discovery (Laptop A only, run once)

```bash
cd mining
npm run discover
```

Sweeps GitHub Search API across ~65 star buckets (1000-1099, 1100-1199, …, ≥200000). When a bucket exceeds the 1000-result cap it is auto-halved.

Outputs:
- `mining/repos.jsonl` — one JSON repo per line (~30-40k rows expected)
- `mining/discovery.db` — same data in SQLite

Distribute `repos.jsonl` to the other two laptops:

```bash
scp mining/repos.jsonl userB@laptopB:/path/to/agentic_mining/mining/
scp mining/repos.jsonl userC@laptopC:/path/to/agentic_mining/mining/
```

---

## Phase 2 — Mining (all 3 laptops in parallel)

After each laptop has its own `.env` and `repos.jsonl`:

```bash
cd mining
npm run mine
```

For each `(repo x month)` in `[DATE_FROM, DATE_TO)`:
1. **PR search** — `/search/issues?q=repo:O/R+type:pr+created:FROM..TO`, paginated. If a single month has >1000 PRs (rare; only mega-repos in active months), the script reshards into ~weekly slices.
2. **Commits** — `/repos/O/R/commits?since=FROM&until=TO`, paginated via `Link: rel="next"` (no 1000 cap).
3. PRs go to `prs`, commits go to `commits`. The `progress` row for that stream is marked `done` only after the last page lands.

Outputs:
- `mining/mining_<LAPTOP_ID>.db`
- `mining/logs/{info,warn,error,combined}.log`

Re-running the script picks up where it left off.

---

## Phase 3 — Merge (run once, on whichever laptop you'll analyze on)

Collect all three `.db` files into one directory, then:

```bash
cd mining
npm run merge -- mining_A.db mining_B.db mining_C.db -o mining_merged.db
```

Uses `ATTACH DATABASE` + `INSERT OR IGNORE` per table. PRs and commits are disjoint by date window; `repos` is identical across laptops (the first wins).

---

## SQLite schema

| Table      | Key                          | Notable columns                                                                 |
|------------|------------------------------|---------------------------------------------------------------------------------|
| `repos`    | `id` (GitHub repo id)        | `full_name, stars, language, license, default_branch, created_at, pushed_at, archived, fork, raw` |
| `prs`      | `id` (GitHub PR id)          | `repo_id, number, title, body, user_login, state, created_at, closed_at, merged_at, draft, raw`   |
| `commits`  | `sha`                        | `repo_id, author_login, author_email, author_date, committer_login, message, raw` |
| `progress` | `(repo_id, month, kind)` PK  | `status in {pending,done,error}, pages_done, updated_at`                          |

Every data table keeps a `raw` JSON column with the full API response.

---

## Tuning (poolingh non-default settings used here)

- `safetyRemainingRequestCount = 10` (default 5) — safer with concurrent tokens
- `tokenResumeBufferTime = 5000ms` (default 2000) — avoids premature resume
- `maxErrorCountPerRequest = 8`, `maxErrorCountInTotal = 20000` — tolerates long runs
- **Staggered startup**: client `i` paused for `i x 60s` to avoid IP-level secondary rate limits when 2-3 tokens come from the same network

If your IP triggers secondary limits, increase the stagger or reduce concurrent clients per laptop.

---

## Throughput planning

- Per-token caps: Search API **30 req/min**; Core REST **5000 req/hr**.
- Per laptop with 3 tokens: ~90 req/min Search, ~15k req/hr REST.
- ~35k repos x 14 months x ~2 calls (PR search + commits, plus pagination) ≈ several hundred thousand calls per laptop.
- Plan for **2-4 days** of continuous mining per laptop. Crashes are safe — the script resumes.

---

## Testing — Laptop A constrained dry run

[mining/test-laptopA.sh](mining/test-laptopA.sh) runs `mine-window.js` against **5 well-known active repos** for **one week** (2023-01-01 → 2023-01-08), then re-runs to verify resumability.

```bash
cd mining
GH_TOKEN_1=ghp_yourtoken ./test-laptopA.sh
```

The script:
1. Builds a tiny test `repos.jsonl` of 5 repos (facebook/react, vercel/next.js, microsoft/vscode, kubernetes/kubernetes, pytorch/pytorch).
2. Runs `mine-window.js` with `LAPTOP_ID=test`, `DATE_FROM=2023-01-01`, `DATE_TO=2023-01-08`, `REPO_LIMIT=5`.
3. Asserts: `prs`, `commits`, `progress` tables are populated; PR `created_at` values fall inside the window; all 10 `(repo, week, kind)` progress rows are `done`.
4. Re-runs the script and asserts that **zero new HTTP requests** hit the network (resumability check via log line-count diff).
5. Cleans up `mining_test.db` so a real run starts fresh.

Expected wall time: ~1 minute on a single token.

---

## Verification of a real run

1. **Phase 1 sanity** — `wc -l mining/repos.jsonl` should be 30k-40k; spot-check 5 random rows have `stars >= 1000`.
2. **Token health** — `tail -f mining/logs/error.log` during the first 10 min: pause/resume messages are normal, but a 401/403 storm means a bad token.
3. **Date-window correctness** — `sqlite3 mining_A.db 'SELECT MIN(created_at), MAX(created_at) FROM prs'` must lie within Laptop A's window.
4. **Coverage probe** — pick `facebook/react`; compare `SELECT COUNT(*) FROM prs WHERE repo_id = ?` against the GitHub UI's PR count for the period.
5. **Merge integrity** — `SELECT COUNT(*) FROM prs` on `mining_merged.db` equals the sum across the three sources.
