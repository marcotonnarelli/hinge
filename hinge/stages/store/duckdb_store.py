"""DuckDB-backed implementation of StoreStage.

Tables
------
meta        key/value store for the storage-layout version.
datasets    one row per ingest run — tracks dataset_id, reader, path, counts.
nodes       typed nodes, partitioned by dataset_id.
edges       typed edges, partitioned by dataset_id.

Each ingest run gets a unique dataset_id (UUID hex). Projections reference a
specific dataset_id so multiple datasets can coexist in the same file.

The class is a context manager. Open it in a ``with`` block — DuckDB's single-
writer lock is released on exit, which is what lets the dbt subprocess take
over the file during a projection run.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any

import duckdb

from hinge.config import settings
from hinge.kernel.protocols.store_stage import DatasetMeta, StoreCensus, StoreFingerprint
from hinge.kernel.schema.typed_edge import TypedEdge
from hinge.kernel.schema.typed_node import TypedNode

logger = logging.getLogger(__name__)

_STORAGE_VERSION = 2  # storage layout version (table shapes). Independent of HIN schema_version.
_UUID_HEX = re.compile(r"^[0-9a-f]{32}$")


def _scalar(row: tuple[Any, ...] | None) -> Any:
    if row is None:
        raise RuntimeError("expected one row from scalar query, got none")
    return row[0]


class SchemaMismatchError(RuntimeError):
    """Raised when an existing .duckdb file was written by a different storage version."""


@dataclass(frozen=True)
class DuckDbDatasetView:
    """DatasetView returned by DuckDBStore. SQL-backed by definition.

    The views ``active_nodes`` / ``active_edges`` are reused across runs;
    ``scope_to_dataset`` rewrites them to point at the requested dataset_id.
    Concurrent projections against different datasets are therefore *not*
    supported — sequential runs only.
    """

    dataset_id: str
    db_path: Path
    nodes_view: str = "active_nodes"
    edges_view: str = "active_edges"

    def close(self) -> None:
        # Views are kept; the next scope_to_dataset overwrites them.
        return None


class DuckDBStore:
    def __init__(self, path: str | Path | None = None, read_only: bool = False) -> None:
        self._path = Path(path) if path is not None else settings.store_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._read_only = read_only
        self._conn: duckdb.DuckDBPyConnection | None = None

    # ---- context manager ----

    def __enter__(self) -> DuckDBStore:
        self._conn = duckdb.connect(str(self._path), read_only=self._read_only)
        logger.debug("store opened — path=%s read_only=%s", self._path, self._read_only)
        if not self._read_only:
            self._init_schema()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.debug("store closed — path=%s", self._path)

    # ---- ingest ----

    def begin_dataset(self, dataset_id: str, reader: str, path: str) -> None:
        self._require_dataset_id(dataset_id)
        self._c().execute(
            "INSERT INTO datasets (dataset_id, reader, path, ingested_at) VALUES (?, ?, ?, ?)",
            [dataset_id, reader, path, datetime.now(UTC)],
        )
        logger.debug("dataset created — dataset_id=%s reader=%s", dataset_id, reader)

    def finalise_dataset(self, dataset_id: str, node_count: int, edge_count: int) -> None:
        self._c().execute(
            "UPDATE datasets SET node_count = ?, edge_count = ? WHERE dataset_id = ?",
            [node_count, edge_count, dataset_id],
        )
        logger.debug(
            "dataset finalised — dataset_id=%s nodes=%d edges=%d",
            dataset_id,
            node_count,
            edge_count,
        )

    def upsert(
        self, dataset_id: str, nodes: Iterable[TypedNode], edges: Iterable[TypedEdge]
    ) -> int:
        self._require_dataset_id(dataset_id)
        n_rows = [
            (dataset_id, n.type, n.id, n.timestamp, json.dumps(n.attrs, default=str)) for n in nodes
        ]
        e_rows = [
            (dataset_id, e.type, e.src_id, e.dst_id, e.timestamp, json.dumps(e.attrs, default=str))
            for e in edges
        ]
        if n_rows:
            self._c().executemany(
                "INSERT OR REPLACE INTO nodes (dataset_id, type, id, ts, attrs) "
                "VALUES (?, ?, ?, ?, ?)",
                n_rows,
            )
        if e_rows:
            self._c().executemany(
                "INSERT INTO edges (dataset_id, type, src_id, dst_id, ts, attrs) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                e_rows,
            )
        return len(n_rows) + len(e_rows)

    def ingest_numfocus_contracts(
        self, dataset_id: str, path: str | Path, *, limit: int | None = None
    ) -> tuple[int, int, int]:
        """Run the example fast DuckDB adapter for NumFocus Actions JSONL.

        This is source-specific adapter logic, not core HIN logic. The store
        owns the contract tables and HIN views; the adapter maps one raw source
        format into those tables.
        """
        from hinge.stages.store import _numfocus_contract_adapter

        self._require_dataset_id(dataset_id)
        return _numfocus_contract_adapter.ingest(self._c(), dataset_id, path, limit=limit)

    def discard_dataset(self, dataset_id: str) -> None:
        """Remove every trace of a dataset. Called by the runner on ingest failure."""
        self._require_dataset_id(dataset_id)
        c = self._c()
        c.execute("DELETE FROM nodes WHERE dataset_id = ?", [dataset_id])
        c.execute("DELETE FROM edges WHERE dataset_id = ?", [dataset_id])
        c.execute("DELETE FROM contract_relations WHERE dataset_id = ?", [dataset_id])
        c.execute("DELETE FROM contract_artifacts WHERE dataset_id = ?", [dataset_id])
        c.execute("DELETE FROM contract_repositories WHERE dataset_id = ?", [dataset_id])
        c.execute("DELETE FROM contract_accounts WHERE dataset_id = ?", [dataset_id])
        c.execute("DELETE FROM contract_adapter_manifest WHERE adapter_run_id = ?", [dataset_id])
        c.execute("DELETE FROM datasets WHERE dataset_id = ?", [dataset_id])
        logger.warning("dataset discarded — dataset_id=%s", dataset_id)

    # ---- read / project ----

    def scope_to_dataset(self, dataset_id: str) -> DuckDbDatasetView:
        """Create the dataset-scoped views the projection will read."""
        self._require_dataset_id(dataset_id)
        # dataset_id is validated UUID-hex so direct interpolation is safe;
        # DuckDB doesn't accept ``?`` placeholders inside view definitions.
        c = self._c()
        # Prefer the canonical HIN views. Legacy row-by-row ingests still
        # populate nodes/edges directly; fast HIN ingests backfill them from
        # contract tables. Either way projections see the same active_* shape.
        c.execute(
            f"CREATE OR REPLACE VIEW active_nodes AS "
            f"SELECT type, id, ts, attrs FROM nodes WHERE dataset_id = '{dataset_id}'"
        )
        c.execute(
            f"CREATE OR REPLACE VIEW active_edges AS "
            f"SELECT type, src_id, dst_id, ts, attrs FROM edges WHERE dataset_id = '{dataset_id}'"
        )
        c.execute(
            f"CREATE OR REPLACE VIEW active_hin_nodes AS "
            f"SELECT * FROM hin_nodes WHERE dataset_id = '{dataset_id}'"
        )
        c.execute(
            f"CREATE OR REPLACE VIEW active_hin_edges AS "
            f"SELECT * FROM hin_edges WHERE dataset_id = '{dataset_id}'"
        )
        logger.debug("views scoped — dataset_id=%s", dataset_id)
        return DuckDbDatasetView(dataset_id=dataset_id, db_path=self._path)

    def query(self, dataset_id: str, node_types: list[str]) -> Iterator[TypedNode]:
        self._require_dataset_id(dataset_id)
        if node_types:
            placeholders = ",".join("?" for _ in node_types)
            cur = self._c().execute(
                f"SELECT type, id, ts, attrs FROM nodes "
                f"WHERE dataset_id = ? AND type IN ({placeholders})",
                [dataset_id, *node_types],
            )
        else:
            cur = self._c().execute(
                "SELECT type, id, ts, attrs FROM nodes WHERE dataset_id = ?",
                [dataset_id],
            )
        for type_, id_, ts, attrs in cur.fetchall():
            yield TypedNode(
                type=type_,
                id=id_,
                timestamp=ts,
                attrs=json.loads(attrs) if attrs else {},
            )

    def census(self, dataset_id: str) -> StoreCensus:
        self._require_dataset_id(dataset_id)
        c = self._c()
        node_rows = c.execute(
            "SELECT type, COUNT(*) FROM nodes WHERE dataset_id = ? GROUP BY type",
            [dataset_id],
        ).fetchall()
        edge_rows = c.execute(
            "SELECT type, COUNT(*) FROM edges WHERE dataset_id = ? GROUP BY type",
            [dataset_id],
        ).fetchall()
        return StoreCensus(
            nodes_by_type={t: c for t, c in node_rows},
            edges_by_type={t: c for t, c in edge_rows},
        )

    def fingerprint(self, dataset_id: str) -> StoreFingerprint:
        """Content hash of exactly one dataset — not the whole file."""
        self._require_dataset_id(dataset_id)
        c = self._c()
        n_count = _scalar(
            c.execute("SELECT COUNT(*) FROM nodes WHERE dataset_id = ?", [dataset_id]).fetchone()
        )
        e_count = _scalar(
            c.execute("SELECT COUNT(*) FROM edges WHERE dataset_id = ?", [dataset_id]).fetchone()
        )
        digest = _scalar(
            c.execute(
                "SELECT md5(string_agg(t, '|' ORDER BY t)) FROM ("
                "  SELECT type || ':' || id AS t FROM nodes WHERE dataset_id = ?"
                "  UNION ALL"
                "  SELECT type || ':' || src_id || '->' || dst_id AS t "
                "  FROM edges WHERE dataset_id = ?"
                ")",
                [dataset_id, dataset_id],
            ).fetchone()
        )
        return StoreFingerprint(
            dataset_id=dataset_id,
            schema_version=_STORAGE_VERSION,
            node_count=n_count,
            edge_count=e_count,
            content_hash=hashlib.sha256((digest or "").encode("utf-8")).hexdigest(),
        )

    def list_datasets(self) -> list[DatasetMeta]:
        rows = (
            self._c()
            .execute(
                "SELECT dataset_id, reader, path, ingested_at, node_count, edge_count "
                "FROM datasets ORDER BY ingested_at DESC"
            )
            .fetchall()
        )
        return [
            DatasetMeta(
                dataset_id=r[0],
                reader=r[1],
                path=r[2],
                ingested_at=r[3],
                node_count=r[4],
                edge_count=r[5],
            )
            for r in rows
        ]

    @property
    def db_path(self) -> Path:
        return self._path

    # ---- private ----

    def _c(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            raise RuntimeError(
                "DuckDBStore is not open. Use it as a context manager: `with store:`."
            )
        return self._conn

    @staticmethod
    def _require_dataset_id(dataset_id: str) -> None:
        if not _UUID_HEX.match(dataset_id):
            raise ValueError(f"dataset_id {dataset_id!r} is not a 32-character lowercase UUID hex")

    def _init_schema(self) -> None:
        c = self._c()
        c.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        c.execute(
            "CREATE TABLE IF NOT EXISTS datasets ("
            "  dataset_id  TEXT PRIMARY KEY,"
            "  reader      TEXT NOT NULL,"
            "  path        TEXT NOT NULL,"
            "  ingested_at TIMESTAMP NOT NULL,"
            "  node_count  INTEGER,"
            "  edge_count  INTEGER"
            ")"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS nodes ("
            "  dataset_id TEXT NOT NULL,"
            "  type       TEXT NOT NULL,"
            "  id         TEXT NOT NULL,"
            "  ts         TIMESTAMP,"
            "  attrs      JSON,"
            "  PRIMARY KEY (dataset_id, type, id)"
            ")"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS edges ("
            "  dataset_id TEXT NOT NULL,"
            "  type       TEXT NOT NULL,"
            "  src_id     TEXT NOT NULL,"
            "  dst_id     TEXT NOT NULL,"
            "  ts         TIMESTAMP,"
            "  attrs      JSON"
            ")"
        )
        self._init_contract_schema()
        self._create_hin_views()
        existing = c.execute("SELECT value FROM meta WHERE key = 'storage_version'").fetchone()
        current = str(_STORAGE_VERSION)
        if existing is None:
            c.execute("INSERT INTO meta (key, value) VALUES ('storage_version', ?)", [current])
        elif existing[0] != current:
            raise SchemaMismatchError(
                f"store at {self._path} was written with storage_version={existing[0]}, "
                f"but current is {current}. Delete the file and re-ingest."
            )

    def _init_contract_schema(self) -> None:
        c = self._c()
        c.execute(
            "CREATE TABLE IF NOT EXISTS contract_accounts ("
            "  dataset_id TEXT NOT NULL, account_key TEXT NOT NULL, platform TEXT,"
            "  github_id BIGINT, login TEXT, account_type TEXT, is_bot BOOLEAN,"
            "  bot_confidence DOUBLE, bot_source TEXT, created_at TIMESTAMP, updated_at TIMESTAMP,"
            "  profile_json JSON, observed_at TIMESTAMP, adapter_run_id TEXT,"
            "  PRIMARY KEY (dataset_id, account_key)"
            ")"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS contract_repositories ("
            "  dataset_id TEXT NOT NULL, repo_key TEXT NOT NULL, platform TEXT, github_id BIGINT,"
            "  full_name TEXT, owner_account_key TEXT, name TEXT, description TEXT,"
            "  primary_language TEXT, is_fork BOOLEAN, forked_from_repo_key TEXT,"
            "  default_branch TEXT, created_at TIMESTAMP, pushed_at TIMESTAMP, updated_at TIMESTAMP,"
            "  archived_at TIMESTAMP, deleted_at TIMESTAMP, repo_json JSON, observed_at TIMESTAMP,"
            "  adapter_run_id TEXT, PRIMARY KEY (dataset_id, repo_key)"
            ")"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS contract_artifacts ("
            "  dataset_id TEXT NOT NULL, artifact_key TEXT NOT NULL, platform TEXT, artifact_type TEXT,"
            "  repo_key TEXT, parent_artifact_key TEXT, github_id BIGINT, node_id TEXT, number INTEGER,"
            "  sha TEXT, url TEXT, title TEXT, state TEXT, body_text TEXT, body_text_hash TEXT,"
            "  file_path TEXT, old_file_path TEXT, start_line INTEGER, end_line INTEGER,"
            "  created_at TIMESTAMP, updated_at TIMESTAMP, closed_at TIMESTAMP, merged_at TIMESTAMP,"
            "  artifact_json JSON, observed_at TIMESTAMP, adapter_run_id TEXT,"
            "  PRIMARY KEY (dataset_id, artifact_key)"
            ")"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS contract_relations ("
            "  dataset_id TEXT NOT NULL, relation_key TEXT NOT NULL,"
            "  source_node_key TEXT NOT NULL, source_node_type TEXT NOT NULL,"
            "  target_node_key TEXT NOT NULL, target_node_type TEXT NOT NULL,"
            "  relation_type TEXT NOT NULL, relation_subtype TEXT, directed BOOLEAN DEFAULT TRUE,"
            "  occurred_at TIMESTAMP, observed_at TIMESTAMP, valid_from TIMESTAMP, valid_to TIMESTAMP,"
            "  event_count INTEGER DEFAULT 1, weight DOUBLE DEFAULT 1.0, source_record_id TEXT,"
            "  source_table TEXT, adapter_run_id TEXT, properties JSON,"
            "  PRIMARY KEY (dataset_id, relation_key)"
            ")"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS contract_adapter_manifest ("
            "  adapter_run_id TEXT PRIMARY KEY, adapter_name TEXT, adapter_version TEXT, source_name TEXT,"
            "  extracted_at TIMESTAMP, has_accounts BOOLEAN, has_repositories BOOLEAN, has_commits BOOLEAN,"
            "  has_file_touches BOOLEAN, has_line_touches BOOLEAN, has_pull_requests BOOLEAN,"
            "  has_pr_reviews BOOLEAN, has_issues BOOLEAN, has_comments BOOLEAN, has_stars BOOLEAN,"
            "  has_watches BOOLEAN, has_forks BOOLEAN, has_follows BOOLEAN, has_mentions BOOLEAN,"
            "  has_artifact_refs BOOLEAN, coverage_start TIMESTAMP, coverage_end TIMESTAMP,"
            "  focal_repo_keys TEXT[], notes TEXT"
            ")"
        )

    def _create_hin_views(self) -> None:
        c = self._c()
        c.execute(
            "CREATE OR REPLACE VIEW hin_nodes AS "
            "SELECT dataset_id, account_key AS node_id, 'user' AS node_type, account_type AS node_subtype, "
            "       account_key AS natural_key, login AS display_name, created_at, updated_at, observed_at, "
            "       FALSE AS is_stub, profile_json AS properties "
            "FROM contract_accounts "
            "UNION ALL "
            "SELECT dataset_id, repo_key, 'repo', CASE WHEN is_fork THEN 'fork' ELSE 'repository' END, "
            "       full_name, full_name, created_at, updated_at, observed_at, FALSE, repo_json "
            "FROM contract_repositories "
            "UNION ALL "
            "SELECT dataset_id, artifact_key, 'artifact', artifact_type, artifact_key, "
            "       coalesce(title, artifact_key), created_at, updated_at, observed_at, FALSE, artifact_json "
            "FROM contract_artifacts"
        )
        c.execute(
            "CREATE OR REPLACE VIEW hin_edges AS "
            "SELECT r.dataset_id, r.relation_key AS edge_id, "
            "       r.source_node_key AS source_node_id, "
            "       CASE WHEN r.source_node_type = 'account' THEN 'user' ELSE r.source_node_type END AS source_node_type, "
            "       sn.node_subtype AS source_node_subtype, "
            "       r.target_node_key AS target_node_id, "
            "       CASE WHEN r.target_node_type = 'account' THEN 'user' ELSE r.target_node_type END AS target_node_type, "
            "       tn.node_subtype AS target_node_subtype, "
            "       r.relation_type AS edge_type, r.relation_subtype, r.directed, "
            "       r.occurred_at, r.observed_at, r.valid_from, r.valid_to, "
            "       r.event_count, r.weight, r.adapter_run_id, r.source_record_id, r.properties "
            "FROM contract_relations r "
            "LEFT JOIN hin_nodes sn ON sn.dataset_id = r.dataset_id AND sn.node_id = r.source_node_key "
            "LEFT JOIN hin_nodes tn ON tn.dataset_id = r.dataset_id AND tn.node_id = r.target_node_key"
        )
