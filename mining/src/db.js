import Database from 'better-sqlite3';
import path from 'node:path';

const SCHEMA = `
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS repos (
  id INTEGER PRIMARY KEY,
  full_name TEXT UNIQUE,
  owner TEXT,
  name TEXT,
  stars INTEGER,
  language TEXT,
  license TEXT,
  default_branch TEXT,
  created_at TEXT,
  pushed_at TEXT,
  archived INTEGER,
  fork INTEGER,
  raw TEXT
);
CREATE INDEX IF NOT EXISTS repos_stars ON repos(stars);

CREATE TABLE IF NOT EXISTS prs (
  id INTEGER PRIMARY KEY,
  repo_id INTEGER NOT NULL,
  number INTEGER,
  title TEXT,
  body TEXT,
  user_login TEXT,
  state TEXT,
  created_at TEXT,
  closed_at TEXT,
  merged_at TEXT,
  draft INTEGER,
  raw TEXT
);
CREATE INDEX IF NOT EXISTS prs_repo_created ON prs(repo_id, created_at);

CREATE TABLE IF NOT EXISTS commits (
  sha TEXT PRIMARY KEY,
  repo_id INTEGER NOT NULL,
  author_login TEXT,
  author_email TEXT,
  author_date TEXT,
  committer_login TEXT,
  committer_date TEXT,
  message TEXT,
  raw TEXT
);
CREATE INDEX IF NOT EXISTS commits_repo_committer ON commits(repo_id, committer_date);

CREATE TABLE IF NOT EXISTS progress (
  repo_id INTEGER NOT NULL,
  month TEXT NOT NULL,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  pages_done INTEGER DEFAULT 0,
  updated_at TEXT,
  PRIMARY KEY (repo_id, month, kind)
);
`;

export function openDb(filePath) {
  const db = new Database(path.resolve(filePath));
  db.exec(SCHEMA);

  const stmts = {
    upsertRepo: db.prepare(`
      INSERT INTO repos (id, full_name, owner, name, stars, language, license,
                         default_branch, created_at, pushed_at, archived, fork, raw)
      VALUES (@id, @full_name, @owner, @name, @stars, @language, @license,
              @default_branch, @created_at, @pushed_at, @archived, @fork, @raw)
      ON CONFLICT(id) DO UPDATE SET
        stars = excluded.stars,
        pushed_at = excluded.pushed_at,
        archived = excluded.archived,
        raw = excluded.raw
    `),
    insertPr: db.prepare(`
      INSERT OR IGNORE INTO prs (id, repo_id, number, title, body, user_login, state,
                                  created_at, closed_at, merged_at, draft, raw)
      VALUES (@id, @repo_id, @number, @title, @body, @user_login, @state,
              @created_at, @closed_at, @merged_at, @draft, @raw)
    `),
    insertCommit: db.prepare(`
      INSERT OR IGNORE INTO commits (sha, repo_id, author_login, author_email, author_date,
                                      committer_login, committer_date, message, raw)
      VALUES (@sha, @repo_id, @author_login, @author_email, @author_date,
              @committer_login, @committer_date, @message, @raw)
    `),
    getProgress: db.prepare(`
      SELECT status, pages_done FROM progress
      WHERE repo_id = ? AND month = ? AND kind = ?
    `),
    setProgress: db.prepare(`
      INSERT INTO progress (repo_id, month, kind, status, pages_done, updated_at)
      VALUES (?, ?, ?, ?, ?, ?)
      ON CONFLICT(repo_id, month, kind) DO UPDATE SET
        status = excluded.status,
        pages_done = excluded.pages_done,
        updated_at = excluded.updated_at
    `),
  };

  function isDone(repoId, month, kind) {
    const row = stmts.getProgress.get(repoId, month, kind);
    return row && row.status === 'done';
  }

  function markProgress(repoId, month, kind, status, pagesDone = 0) {
    stmts.setProgress.run(repoId, month, kind, status, pagesDone, new Date().toISOString());
  }

  const insertManyPrs = db.transaction((prs) => {
    for (const pr of prs) stmts.insertPr.run(pr);
  });
  const insertManyCommits = db.transaction((commits) => {
    for (const c of commits) stmts.insertCommit.run(c);
  });

  return {
    raw: db,
    upsertRepo: (repo) => stmts.upsertRepo.run(repo),
    insertPrs: insertManyPrs,
    insertCommits: insertManyCommits,
    isDone,
    markProgress,
    close: () => db.close(),
  };
}

// Maps a GitHub Search API repo `item` into the row shape expected by upsertRepo.
export function repoToRow(item) {
  return {
    id: item.id,
    full_name: item.full_name,
    owner: item.owner?.login ?? null,
    name: item.name,
    stars: item.stargazers_count ?? null,
    language: item.language ?? null,
    license: item.license?.spdx_id ?? null,
    default_branch: item.default_branch ?? null,
    created_at: item.created_at ?? null,
    pushed_at: item.pushed_at ?? null,
    archived: item.archived ? 1 : 0,
    fork: item.fork ? 1 : 0,
    raw: JSON.stringify(item),
  };
}

// Maps a Search API issue (when `type:pr`) into the prs row shape.
export function prToRow(item, repoId) {
  return {
    id: item.id,
    repo_id: repoId,
    number: item.number ?? null,
    title: item.title ?? null,
    body: item.body ?? null,
    user_login: item.user?.login ?? null,
    state: item.state ?? null,
    created_at: item.created_at ?? null,
    closed_at: item.closed_at ?? null,
    merged_at: item.pull_request?.merged_at ?? null,
    draft: item.draft ? 1 : 0,
    raw: JSON.stringify(item),
  };
}

// Maps a REST commit object into the commits row shape.
export function commitToRow(item, repoId) {
  return {
    sha: item.sha,
    repo_id: repoId,
    author_login: item.author?.login ?? null,
    author_email: item.commit?.author?.email ?? null,
    author_date: item.commit?.author?.date ?? null,
    committer_login: item.committer?.login ?? null,
    committer_date: item.commit?.committer?.date ?? null,
    message: item.commit?.message ?? null,
    raw: JSON.stringify(item),
  };
}
