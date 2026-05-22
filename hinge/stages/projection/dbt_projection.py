"""dbt-backed implementation of ProjectionStage.

# ─────────────────────────────────────────────────────────────────────────
# HOW PROJECTIONS GET WIRED IN  (orientation for the projection contributor)
# ─────────────────────────────────────────────────────────────────────────
#
# 1. The store owns the file. Before a projection runs, the caller asks the
#    store for a ``DatasetView`` (``store.scope_to_dataset(dataset_id)``).
#    The store creates the ``active_nodes`` and ``active_edges`` views and
#    returns the path + view names. This stage never opens DuckDB directly
#    for setup — it only opens a read-only connection later to stream rows.
#
# 2. ``DbtProjection.run(spec, params, view)`` invokes dbt as a subprocess,
#    pointed at ``view.db_path``, to materialise the model named by the spec.
#
# 3. The materialised result table MUST follow the output contract:
#    rows are typed edges with columns
#        (src_id TEXT, src_type TEXT, dst_id TEXT, dst_type TEXT,
#         edge_type TEXT, attrs JSON)
#    Read ``models/dev_interaction.sql`` for the worked example.
#
# 4. ``run`` returns a ``ProjectedGraphHandle`` that streams rows back from
#    the materialised table. The exporter consumes the handle.
#
# To add a new projection: drop a .sql file in models/, ship a module under
# ``hinge/stages/projection/specs/`` exposing a ``SPEC`` constant, register
# the entry-point in pyproject.toml under ``hinge.projection_specs``. No
# edits to this file are needed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb

from hinge.kernel.projection.projected_graph import ProjectedGraphHandle
from hinge.kernel.projection.projection_spec import ProjectionSpec
from hinge.kernel.protocols.dataset_view import DatasetView
from hinge.kernel.protocols.projection_stage import EngineFingerprint
from hinge.kernel.schema.typed_edge import TypedEdge
from hinge.kernel.schema.typed_node import TypedNode

logger = logging.getLogger(__name__)

_DBT_PROJECT_DIR = Path(__file__).parent
_FETCH_BATCH = 1_000


class DbtProjection:
    def run(
        self, spec: ProjectionSpec, params: dict[str, Any], view: DatasetView
    ) -> ProjectedGraphHandle:
        self._invoke_dbt(spec.model_name, params, view.db_path)
        return _CursorHandle(view.db_path, spec.model_name)

    def fingerprint(self) -> EngineFingerprint:
        h = hashlib.sha256()
        for p in sorted(_DBT_PROJECT_DIR.rglob("*")):
            if p.is_file() and p.suffix in {".sql", ".yml", ".yaml"}:
                h.update(p.read_bytes())
        return EngineFingerprint(engine="dbt-duckdb", project_hash=h.hexdigest())

    # ---- internals ----

    def _invoke_dbt(self, model: str, params: dict[str, Any], db_path: Path) -> None:
        env = os.environ.copy()
        env["HINGE_STORE_PATH"] = str(db_path)
        env["DBT_PROFILES_DIR"] = str(_DBT_PROJECT_DIR)
        cmd = [
            "dbt",
            "run",
            "--project-dir",
            str(_DBT_PROJECT_DIR),
            "--profiles-dir",
            str(_DBT_PROJECT_DIR),
            "--select",
            model,
        ]
        if params:
            cmd += ["--vars", json.dumps(params)]

        logger.debug("dbt invocation: %s", " ".join(cmd))
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)

        for line in result.stdout.splitlines():
            logger.debug("[dbt] %s", line)
        if result.returncode != 0:
            for line in result.stderr.splitlines():
                logger.error("[dbt stderr] %s", line)
            logger.error("dbt failed (exit %d) for model %r", result.returncode, model)
            raise subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )
        logger.info("dbt model %r materialised successfully", model)


class _CursorHandle:
    """Streams a materialised projection table as TypedNodes / TypedEdges.

    Real streaming — uses ``fetchmany`` so the exporter doesn't have to hold
    the whole graph in memory.
    """

    def __init__(self, db_path: Path, table_name: str) -> None:
        self._db_path = db_path
        self._table_name = table_name

    def iter_nodes(self) -> Iterator[TypedNode]:
        conn = duckdb.connect(str(self._db_path), read_only=True)
        try:
            cur = conn.execute(
                f"SELECT DISTINCT id, type FROM ("
                f"  SELECT src_id AS id, src_type AS type FROM {self._table_name}"
                f"  UNION"
                f"  SELECT dst_id AS id, dst_type AS type FROM {self._table_name}"
                f")"
            )
            while True:
                rows = cur.fetchmany(_FETCH_BATCH)
                if not rows:
                    break
                for id_, type_ in rows:
                    yield TypedNode(type=type_, id=id_)
        finally:
            conn.close()

    def iter_edges(self) -> Iterator[TypedEdge]:
        conn = duckdb.connect(str(self._db_path), read_only=True)
        try:
            cur = conn.execute(f"SELECT src_id, dst_id, edge_type, attrs FROM {self._table_name}")
            while True:
                rows = cur.fetchmany(_FETCH_BATCH)
                if not rows:
                    break
                for src_id, dst_id, edge_type, attrs in rows:
                    yield TypedEdge(
                        type=edge_type,
                        src_id=src_id,
                        dst_id=dst_id,
                        attrs=json.loads(attrs) if attrs else {},
                    )
        finally:
            conn.close()
