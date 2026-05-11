// Phase 2 — mine PRs + commits per (repo, month) within [DATE_FROM, DATE_TO).
// Run on each laptop with disjoint date windows.
//
// Usage:
//   LAPTOP_ID=A DATE_FROM=2022-11-01 DATE_TO=2024-01-01 \
//     GH_TOKEN_1=... GH_TOKEN_2=... node src/mine-window.js
//
// Input:  repos.jsonl in cwd (produced by discover-repos.js).
// Output: mining_<LAPTOP_ID>.db.

import 'dotenv/config';
import fs from 'node:fs';
import readline from 'node:readline';
import chalk from 'chalk';
import {
  GitHubApiClient,
  GitHubApiQueue,
  GitHubApiRequest,
} from '../../poolingh/src/index.js';
import { openDb, prToRow, commitToRow } from './db.js';
import { monthIter } from './util/month-iter.js';

const LAPTOP_ID = process.env.LAPTOP_ID || 'A';
const DATE_FROM = process.env.DATE_FROM;
const DATE_TO = process.env.DATE_TO;
const REPO_LIMIT = process.env.REPO_LIMIT ? Number(process.env.REPO_LIMIT) : null;
const REPOS_FILE = process.env.REPOS_FILE || 'repos.jsonl';
const WATCH_INTERVAL_MS = Number(process.env.WATCH_INTERVAL_MS || 30_000);
const PER_PAGE = 100;
const MAX_SEARCH_PAGES = 10;

if (!DATE_FROM || !DATE_TO) {
  console.error('ERROR: set DATE_FROM and DATE_TO (YYYY-MM-DD)');
  process.exit(1);
}

const tokens = [process.env.GH_TOKEN_1, process.env.GH_TOKEN_2, process.env.GH_TOKEN_3]
  .filter((t) => t && t.trim().length > 0);
if (tokens.length === 0) {
  console.error('ERROR: set at least one of GH_TOKEN_1, GH_TOKEN_2, GH_TOKEN_3');
  process.exit(1);
}

const clients = tokens.map((t) => new GitHubApiClient(t, 10, 5000, './logs'));
const queue = new GitHubApiQueue(clients, 8, 20000, './logs');
for (let i = 1; i < clients.length; i++) {
  clients[i].pause(Date.now() + i * 60_000);
}

const db = openDb(`mining_${LAPTOP_ID}.db`);
const months = monthIter(DATE_FROM, DATE_TO);
console.log(chalk.cyan(
  `[mine ${LAPTOP_ID}] window ${DATE_FROM}..${DATE_TO} = ${months.length} months, ${tokens.length} tokens`,
));

// outstanding[`${repoId}:${monthKey}:${kind}`] = N pending streams.
const outstanding = new Map();
function bumpOutstanding(repoId, monthKey, kind, delta) {
  const key = `${repoId}:${monthKey}:${kind}`;
  const cur = (outstanding.get(key) || 0) + delta;
  if (cur <= 0) {
    outstanding.delete(key);
    db.markProgress(repoId, monthKey, kind, 'done');
  } else {
    outstanding.set(key, cur);
  }
}

let stats = { prPages: 0, commitPages: 0, prsInserted: 0, commitsInserted: 0, errors: 0 };

// ---- PR search ---------------------------------------------------------

// GitHub `created:A..B` is INCLUSIVE on both ends, but our windows are half-open [from, to).
// Subtract one day from the upper bound so we don't double-count the boundary.
function isoMinusOneDay(iso) {
  const d = new Date(iso + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

function prSearchUrl(repo, fromIso, toIso, page) {
  const upper = isoMinusOneDay(toIso);
  const q = encodeURIComponent(`repo:${repo.full_name} type:pr created:${fromIso}..${upper}`);
  return `https://api.github.com/search/issues?q=${q}&per_page=${PER_PAGE}&page=${page}`;
}

function enqueuePrSubWindow(repo, monthKey, fromIso, toIso, page) {
  const url = prSearchUrl(repo, fromIso, toIso, page);
  const req = new GitHubApiRequest(url, {}, (response) => {
    try {
      const data = response?.data ?? {};
      const items = data.items ?? [];
      const total = data.total_count ?? 0;

      // Reshard if first page of full month exceeds 1000.
      if (page === 1 && total > 1000 && fromIso === monthKey + '-01') {
        const weeks = splitMonthIntoWeeks(monthKey);
        console.log(chalk.yellow(
          `[mine] ${repo.full_name} ${monthKey}: ${total} PRs, sharding into ${weeks.length} weeks`,
        ));
        bumpOutstanding(repo.id, monthKey, 'pr', weeks.length); // add new streams
        bumpOutstanding(repo.id, monthKey, 'pr', -1);            // remove this stream
        for (const [wf, wt] of weeks) enqueuePrSubWindow(repo, monthKey, wf, wt, 1);
        return;
      }

      if (items.length > 0) {
        db.insertPrs(items.map((it) => prToRow(it, repo.id)));
        stats.prsInserted += items.length;
      }
      stats.prPages++;

      // Continue pagination on the same sub-window.
      const cappedTotal = Math.min(total, 1000);
      const lastPage = Math.min(MAX_SEARCH_PAGES, Math.ceil(cappedTotal / PER_PAGE));
      if (page < lastPage) {
        enqueuePrSubWindow(repo, monthKey, fromIso, toIso, page + 1);
        return; // do not decrement outstanding; we handed off the stream.
      }

      // Stream complete.
      bumpOutstanding(repo.id, monthKey, 'pr', -1);
    } catch (err) {
      stats.errors++;
      console.error(chalk.red(`[mine] pr callback error ${repo.full_name} ${monthKey}: ${err.message}`));
      bumpOutstanding(repo.id, monthKey, 'pr', -1);
    }
  });
  queue.push(req);
}

function splitMonthIntoWeeks(monthKey) {
  // Returns half-open [fromIso, toIso) slices that tile the calendar month exactly.
  // prSearchUrl converts each into an inclusive GitHub query, so slices stay contiguous
  // with no boundary day double-counted.
  const [y, m] = monthKey.split('-').map(Number);
  const nextMonth = new Date(Date.UTC(y, m, 1));
  const slices = [];
  let cur = new Date(Date.UTC(y, m - 1, 1));
  while (cur < nextMonth) {
    const next = new Date(cur.getTime() + 7 * 24 * 3600 * 1000);
    const end = next < nextMonth ? next : nextMonth;
    slices.push([cur.toISOString().slice(0, 10), end.toISOString().slice(0, 10)]);
    cur = end;
  }
  return slices;
}

// ---- Commits -----------------------------------------------------------

function commitsUrl(repo, sinceIso, untilIso, page) {
  return `https://api.github.com/repos/${repo.full_name}/commits` +
    `?since=${sinceIso}T00:00:00Z&until=${untilIso}T00:00:00Z&per_page=${PER_PAGE}&page=${page}`;
}

function enqueueCommitsPage(repo, month, page) {
  const url = commitsUrl(repo, month.from, month.to, page);
  const req = new GitHubApiRequest(url, {}, (response) => {
    try {
      const data = response?.data ?? [];
      const items = Array.isArray(data) ? data : [];

      if (items.length > 0) {
        db.insertCommits(items.map((it) => commitToRow(it, repo.id)));
        stats.commitsInserted += items.length;
      }
      stats.commitPages++;

      // Has-next based on Link header.
      const link = response?.headers?.link || '';
      const hasNext = /<[^>]+>;\s*rel="next"/.test(link);
      if (hasNext) {
        enqueueCommitsPage(repo, month, page + 1);
        return;
      }
      bumpOutstanding(repo.id, month.key, 'commit', -1);
    } catch (err) {
      // 409 Conflict on empty repos is common; treat as done.
      stats.errors++;
      console.error(chalk.red(`[mine] commit callback error ${repo.full_name} ${month.key}: ${err.message}`));
      bumpOutstanding(repo.id, month.key, 'commit', -1);
    }
  });
  queue.push(req);
}

// ---- Driver ------------------------------------------------------------

async function loadRepos() {
  const repos = [];
  const rl = readline.createInterface({
    input: fs.createReadStream(REPOS_FILE),
    crlfDelay: Infinity,
  });
  for await (const line of rl) {
    const t = line.trim();
    if (!t) continue;
    repos.push(JSON.parse(t));
  }
  return repos;
}

const repos = await loadRepos();
console.log(chalk.cyan(`[mine ${LAPTOP_ID}] loaded ${repos.length} repos from ${REPOS_FILE}`));
const slice = REPO_LIMIT ? repos.slice(0, REPO_LIMIT) : repos;

// Upsert every repo we'll touch so the `repos` table is populated even when
// repos.jsonl was produced elsewhere (or by the test harness).
for (const repo of slice) {
  db.upsertRepo({
    id: repo.id,
    full_name: repo.full_name,
    owner: repo.owner ?? null,
    name: repo.name ?? null,
    stars: repo.stars ?? null,
    language: repo.language ?? null,
    license: repo.license ?? null,
    default_branch: repo.default_branch ?? null,
    created_at: repo.created_at ?? null,
    pushed_at: repo.pushed_at ?? null,
    archived: repo.archived ?? 0,
    fork: repo.fork ?? 0,
    raw: repo.raw ?? null,
  });
}

let scheduled = 0;
for (const repo of slice) {
  for (const month of months) {
    if (!db.isDone(repo.id, month.key, 'pr')) {
      bumpOutstanding(repo.id, month.key, 'pr', 1);
      enqueuePrSubWindow(repo, month.key, month.from, month.to, 1);
      scheduled++;
    }
    if (!db.isDone(repo.id, month.key, 'commit')) {
      bumpOutstanding(repo.id, month.key, 'commit', 1);
      enqueueCommitsPage(repo, month, 1);
      scheduled++;
    }
  }
}
console.log(chalk.cyan(`[mine ${LAPTOP_ID}] scheduled ${scheduled} (repo,month,kind) streams`));

queue.start();

// Periodic stats + completion check.
const t0 = Date.now();
const watcher = setInterval(() => {
  console.log(chalk.cyan(
    `[mine ${LAPTOP_ID}] q=${queue.getQueueLength()} streams=${outstanding.size} ` +
    `prPages=${stats.prPages} commitPages=${stats.commitPages} ` +
    `prs=${stats.prsInserted} commits=${stats.commitsInserted} errors=${stats.errors} ` +
    `elapsed=${Math.round((Date.now() - t0) / 1000)}s`,
  ));
  if (queue.getQueueLength() === 0 && outstanding.size === 0) {
    clearInterval(watcher);
    queue.stop();
    db.close();
    console.log(chalk.green(`[mine ${LAPTOP_ID}] DONE`));
    process.exit(0);
  }
}, WATCH_INTERVAL_MS);
