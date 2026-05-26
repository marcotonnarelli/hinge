"""dbt-backed implementation of ProjectionStage.

# ─────────────────────────────────────────────────────────────────────────
# HOW PROJECTIONS GET WIRED IN  (orientation for the projection contributor)
# ─────────────────────────────────────────────────────────────────────────
#
# 1. The store owns the file. Before a projection runs, the caller asks the
#    store for a ``DatasetView`` (``store.scope_to_dataset(dataset_id)``).
#    The store creates the ``active_hin_nodes`` and ``active_hin_edges`` views and
#    returns the path + view names. This stage never opens DuckDB directly
#    for setup — it only opens a read-only connection later to stream rows.
#
# 2. ``DbtProjection.run(spec, params, view)`` invokes dbt as a subprocess,
#    pointed at ``view.db_path``, to materialise the model named by the spec.
#
# 3. The materialised result table MUST follow the standard network contract:
#        recipe_name, recipe_version, source_node_id, source_node_type,
#        target_node_id, target_node_type, directed, edge_type, weight,
#        weight_kind, n_contexts, n_events, first_seen_at, last_seen_at,
#        time_bin, bot_policy, properties
#    The cursor handle converts that richer dbt table into TypedEdge objects
#    for existing exporters. Legacy src_id/dst_id/attrs tables are still read.
#
# 4. ``run`` returns a ``ProjectedGraphHandle`` that streams rows back from
#    the materialised table. The exporter consumes the handle.
#
# To add a new cookbook projection: drop a .sql file in
# ``hinge/dbt/models/networks/``, ship a module under
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

_DBT_PROJECT_DIR = Path(__file__).parents[2] / "dbt"
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
        seed_cmd = [
            "dbt",
            "seed",
            "--project-dir",
            str(_DBT_PROJECT_DIR),
            "--profiles-dir",
            str(_DBT_PROJECT_DIR),
            "--select",
            "ref_recipe_requirements",
        ]
        self._run_dbt(seed_cmd, env, "seed ref_recipe_requirements")

        run_cmd = [
            "dbt",
            "run",
            "--project-dir",
            str(_DBT_PROJECT_DIR),
            "--profiles-dir",
            str(_DBT_PROJECT_DIR),
            "--select",
            f"+{model}",
        ]
        if params:
            run_cmd += ["--vars", json.dumps(params)]

        self._run_dbt(run_cmd, env, f"model {model!r}")
        logger.info("dbt model %r materialised successfully", model)

    def _run_dbt(self, cmd: list[str], env: dict[str, str], label: str) -> None:
        logger.debug("dbt invocation: %s", " ".join(cmd))
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)

        for line in result.stdout.splitlines():
            logger.debug("[dbt] %s", line)
        if result.returncode != 0:
            for line in result.stderr.splitlines():
                logger.error("[dbt stderr] %s", line)
            logger.error("dbt failed (exit %d) for %s", result.returncode, label)
            raise subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )


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
            if self._uses_standard_network_schema(conn):
                query = (
                    f"SELECT DISTINCT id, type FROM ("
                    f"  SELECT source_node_id AS id, source_node_type AS type FROM {self._table_name}"
                    f"  UNION"
                    f"  SELECT target_node_id AS id, target_node_type AS type FROM {self._table_name}"
                    f")"
                )
            else:
                query = (
                    f"SELECT DISTINCT id, type FROM ("
                    f"  SELECT src_id AS id, src_type AS type FROM {self._table_name}"
                    f"  UNION"
                    f"  SELECT dst_id AS id, dst_type AS type FROM {self._table_name}"
                    f")"
                )
            cur = conn.execute(query)
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
            if self._uses_standard_network_schema(conn):
                yield from self._iter_standard_edges(conn)
            else:
                yield from self._iter_legacy_edges(conn)
        finally:
            conn.close()

    def _uses_standard_network_schema(self, conn: duckdb.DuckDBPyConnection) -> bool:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info('{self._table_name}')").fetchall()}
        return {
            "source_node_id",
            "source_node_type",
            "target_node_id",
            "target_node_type",
            "recipe_name",
            "properties",
        }.issubset(columns)

    def _iter_standard_edges(self, conn: duckdb.DuckDBPyConnection) -> Iterator[TypedEdge]:
        cur = conn.execute(
            f"""
            SELECT
                source_node_id,
                target_node_id,
                edge_type,
                to_json({{
                    'recipe_name': recipe_name,
                    'recipe_version': recipe_version,
                    'directed': directed,
                    'weight': weight,
                    'weight_kind': weight_kind,
                    'n_contexts': n_contexts,
                    'n_events': n_events,
                    'first_seen_at': first_seen_at,
                    'last_seen_at': last_seen_at,
                    'time_bin': time_bin,
                    'bot_policy': bot_policy
                }}) AS standard_attrs,
                properties
            FROM {self._table_name}
            """
        )
        while True:
            rows = cur.fetchmany(_FETCH_BATCH)
            if not rows:
                break
            for src_id, dst_id, edge_type, standard_attrs, properties in rows:
                attrs = json.loads(standard_attrs) if standard_attrs else {}
                attrs.update(json.loads(properties) if properties else {})
                yield TypedEdge(type=edge_type, src_id=src_id, dst_id=dst_id, attrs=attrs)

    def _iter_legacy_edges(self, conn: duckdb.DuckDBPyConnection) -> Iterator[TypedEdge]:
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
