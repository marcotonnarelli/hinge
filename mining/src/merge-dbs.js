// Phase 3 — merge per-laptop SQLite DBs into one.
//
// Usage:
//   node src/merge-dbs.js mining_A.db mining_B.db mining_C.db -o mining_merged.db

import Database from 'better-sqlite3';
import path from 'node:path';
import fs from 'node:fs';
import chalk from 'chalk';
import { openDb } from './db.js';

const args = process.argv.slice(2);
const outIdx = args.indexOf('-o');
if (outIdx === -1 || outIdx === args.length - 1) {
  console.error('Usage: node src/merge-dbs.js <db1> <db2> ... -o <out.db>');
  process.exit(1);
}
const outPath = args[outIdx + 1];
const inPaths = args.filter((_, i) => i !== outIdx && i !== outIdx + 1);
if (inPaths.length === 0) {
  console.error('No input DBs provided.');
  process.exit(1);
}

if (fs.existsSync(outPath)) {
  console.error(`Refusing to overwrite existing ${outPath}. Delete it first.`);
  process.exit(1);
}

// Initialize schema in the output DB by opening it through openDb.
openDb(outPath).close();

const out = new Database(path.resolve(outPath));
out.pragma('journal_mode = WAL');
out.pragma('synchronous = NORMAL');

for (const src of inPaths) {
  console.log(chalk.cyan(`[merge] attaching ${src}`));
  out.exec(`ATTACH DATABASE '${path.resolve(src).replace(/'/g, "''")}' AS src`);
  const t0 = Date.now();
  out.exec('BEGIN');
  try {
    out.exec('INSERT OR IGNORE INTO repos    SELECT * FROM src.repos');
    out.exec('INSERT OR IGNORE INTO prs      SELECT * FROM src.prs');
    out.exec('INSERT OR IGNORE INTO commits  SELECT * FROM src.commits');
    out.exec('INSERT OR IGNORE INTO progress SELECT * FROM src.progress');
    out.exec('COMMIT');
  } catch (err) {
    out.exec('ROLLBACK');
    throw err;
  }
  out.exec('DETACH DATABASE src');
  console.log(chalk.green(`[merge] merged ${src} in ${Math.round((Date.now() - t0) / 1000)}s`));
}

const counts = {
  repos: out.prepare('SELECT COUNT(*) c FROM repos').get().c,
  prs: out.prepare('SELECT COUNT(*) c FROM prs').get().c,
  commits: out.prepare('SELECT COUNT(*) c FROM commits').get().c,
  progress: out.prepare('SELECT COUNT(*) c FROM progress').get().c,
};
console.log(chalk.green(`[merge] DONE → ${outPath}`));
console.table(counts);
out.close();
