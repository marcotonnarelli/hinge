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

_STORAGE_VERSION = 1  # storage layout version (table shapes). Independent of HIN schema_version.
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

    def discard_dataset(self, dataset_id: str) -> None:
        """Remove every trace of a dataset. Called by the runner on ingest failure."""
        self._require_dataset_id(dataset_id)
        c = self._c()
        c.execute("DELETE FROM nodes WHERE dataset_id = ?", [dataset_id])
        c.execute("DELETE FROM edges WHERE dataset_id = ?", [dataset_id])
        c.execute("DELETE FROM datasets WHERE dataset_id = ?", [dataset_id])
        logger.warning("dataset discarded — dataset_id=%s", dataset_id)

    # ---- read / project ----

    def scope_to_dataset(self, dataset_id: str) -> DuckDbDatasetView:
        """Create the dataset-scoped views the projection will read."""
        self._require_dataset_id(dataset_id)
        # dataset_id is validated UUID-hex so direct interpolation is safe;
        # DuckDB doesn't accept ``?`` placeholders inside view definitions.
        c = self._c()
        c.execute(
            f"CREATE OR REPLACE VIEW active_nodes AS "
            f"SELECT type, id, ts, attrs FROM nodes WHERE dataset_id = '{dataset_id}'"
        )
        c.execute(
            f"CREATE OR REPLACE VIEW active_edges AS "
            f"SELECT type, src_id, dst_id, ts, attrs FROM edges WHERE dataset_id = '{dataset_id}'"
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
        existing = c.execute("SELECT value FROM meta WHERE key = 'storage_version'").fetchone()
        current = str(_STORAGE_VERSION)
        if existing is None:
            c.execute("INSERT INTO meta (key, value) VALUES ('storage_version', ?)", [current])
        elif existing[0] != current:
            raise SchemaMismatchError(
                f"store at {self._path} was written with storage_version={existing[0]}, "
                f"but current is {current}. Delete the file and re-ingest."
            )
