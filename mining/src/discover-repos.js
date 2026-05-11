// Phase 1 — discover all OSS repos with stars >= MIN_STARS using sharded star buckets.
// Run ONCE on Laptop A. Output: repos.jsonl + discovery.db.
//
// Usage:
//   GH_TOKEN_1=... GH_TOKEN_2=... node src/discover-repos.js
//
// Env:
//   GH_TOKEN_1..3   GitHub PATs (any subset)
//   MIN_STARS       lower bound for stars (default 1000)

import 'dotenv/config';
import fs from 'node:fs';
import chalk from 'chalk';
import {
  GitHubApiClient,
  GitHubApiQueue,
  GitHubApiRequest,
} from '../../poolingh/src/index.js';
import { openDb, repoToRow } from './db.js';
import {
  defaultStarBuckets,
  bucketToQuery,
  halveBucket,
} from './util/star-buckets.js';

const MIN_STARS = Number(process.env.MIN_STARS || 1000);
const OUT_JSONL = 'repos.jsonl';
const OUT_DB = 'discovery.db';
const PER_PAGE = 100;
const MAX_PAGES = 10; // GitHub Search API hard cap.

const tokens = [process.env.GH_TOKEN_1, process.env.GH_TOKEN_2, process.env.GH_TOKEN_3]
  .filter((t) => t && t.trim().length > 0);
if (tokens.length === 0) {
  console.error('ERROR: set at least one of GH_TOKEN_1, GH_TOKEN_2, GH_TOKEN_3');
  process.exit(1);
}

const clients = tokens.map((t) => new GitHubApiClient(t, 10, 5000, './logs'));
const queue = new GitHubApiQueue(clients, 8, 20000, './logs');
// Stagger startup to avoid IP-level secondary rate limits.
for (let i = 1; i < clients.length; i++) {
  clients[i].pause(Date.now() + i * 60_000);
}

const db = openDb(OUT_DB);
const jsonlStream = fs.createWriteStream(OUT_JSONL, { flags: 'a' });
const seenRepoIds = new Set();
let inflight = 0;
let totalEnqueued = 0;
let totalRepos = 0;

function searchUrl(query, page) {
  const q = encodeURIComponent(query);
  return `https://api.github.com/search/repositories?q=${q}&sort=stars&order=desc&per_page=${PER_PAGE}&page=${page}`;
}

function enqueueBucketPage(bucket, page, knownTotal = null) {
  const query = bucketToQuery(bucket);
  const url = searchUrl(query, page);
  totalEnqueued++;
  inflight++;
  const req = new GitHubApiRequest(url, {}, (response) => {
    try {
      const data = response?.data ?? {};
      const items = data.items ?? [];
      const total = data.total_count ?? 0;

      if (page === 1 && total > 1000 && knownTotal === null) {
        // Bucket too dense — split and skip processing this page's results
        // (we'll re-fetch via the halved sub-buckets which are guaranteed disjoint).
        const halves = halveBucket(bucket);
        if (halves) {
          console.log(chalk.yellow(
            `[discover] bucket ${query} has ${total} repos (>1000); splitting`,
          ));
          for (const h of halves) enqueueBucketPage(h, 1);
          return;
        }
        console.warn(chalk.yellow(
          `[discover] cannot split bucket ${query} (open-ended); will only get first 1000`,
        ));
      }

      // Persist items.
      for (const item of items) {
        if (seenRepoIds.has(item.id)) continue;
        seenRepoIds.add(item.id);
        const row = repoToRow(item);
        db.upsertRepo(row);
        jsonlStream.write(JSON.stringify(row) + '\n');
        totalRepos++;
      }

      // On page 1, enqueue further pages.
      if (page === 1) {
        const pages = Math.min(MAX_PAGES, Math.ceil(Math.min(total, 1000) / PER_PAGE));
        for (let p = 2; p <= pages; p++) enqueueBucketPage(bucket, p, total);
      }

      if (totalRepos % 500 < items.length) {
        console.log(chalk.cyan(
          `[discover] repos=${totalRepos} bucket=${query} page=${page} (q=${queue.getQueueLength()}, inflight=${inflight})`,
        ));
      }
    } catch (err) {
      console.error(chalk.red(`[discover] callback error: ${err.message}`));
    } finally {
      inflight--;
    }
  });
  queue.push(req);
}

// Seed buckets.
const buckets = defaultStarBuckets(MIN_STARS);
console.log(chalk.cyan(`[discover] starting with ${buckets.length} star buckets, MIN_STARS=${MIN_STARS}`));
for (const b of buckets) enqueueBucketPage(b, 1);

queue.start();

// Completion watcher.
const watcher = setInterval(() => {
  if (inflight === 0 && queue.getQueueLength() === 0) {
    clearInterval(watcher);
    queue.stop();
    jsonlStream.end();
    db.close();
    console.log(chalk.green(
      `[discover] DONE — ${totalRepos} unique repos, ${totalEnqueued} requests, ${queue.getRequestFailCount()} failed`,
    ));
    process.exit(0);
  }
}, 2000);
