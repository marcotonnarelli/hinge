"""Linear pipeline runner.

Pipeline shapes supported:

    Reader → Store                          (ingest)
    Store  → Projection                     (project)
    Store  → Projection → Exporter          (export)

The runner owns three responsibilities:

  * batching and schema validation during ingest;
  * transactional bookkeeping — a failed ingest leaves no half-written dataset;
  * snapshot_id assembly during export, computed from store + projection
    fingerprints + the HIN schema version + the tool version.

Stage implementations are passed in; the runner never constructs them or
imports concrete classes.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any, BinaryIO

from pydantic import BaseModel

from hinge.kernel.projection.projected_graph import ProjectedGraphHandle
from hinge.kernel.projection.projection_spec import ProjectionSpec
from hinge.kernel.protocols.dataset_view import DatasetView
from hinge.kernel.protocols.exporter_stage import ExporterStage, ExportReceipt
from hinge.kernel.protocols.projection_stage import ProjectionStage
from hinge.kernel.protocols.reader_stage import BulkIngestReader, ReaderStage
from hinge.kernel.protocols.store_stage import StoreStage
from hinge.kernel.schema.hin_schema import HINSchema
from hinge.kernel.schema.schema_violation import SchemaViolation
from hinge.kernel.schema.typed_edge import TypedEdge
from hinge.kernel.schema.typed_node import TypedNode

logger = logging.getLogger(__name__)

_TOOL_VERSION = "0.1.0"
_BATCH_SIZE = 100_000


class IngestReport(BaseModel):
    dataset_id: str
    elements_read: int
    nodes_upserted: int
    edges_upserted: int
    violation_count: int


def run_ingest(
    reader: ReaderStage | BulkIngestReader, store: StoreStage, schema: HINSchema
) -> IngestReport:
    """Read a dataset and persist it. Transactional: on any exception the
    half-written dataset is discarded so the store stays consistent.

    Readers that implement ``bulk_ingest`` are dispatched through the bulk
    path — schema validation is delegated to the reader because the records
    never cross the Python boundary.
    """
    dataset_id = uuid.uuid4().hex
    desc = reader.describe()
    logger.info(
        "ingest started — dataset_id=%s reader=%s format=%s path=%s size=%.1fMB",
        dataset_id,
        desc.dataset,
        desc.format,
        desc.path,
        desc.byte_size / 1_048_576,
    )

    store.begin_dataset(dataset_id, desc.dataset, str(desc.path))
    if isinstance(reader, BulkIngestReader):
        try:
            records, nodes_total, edges_total = reader.bulk_ingest(store, dataset_id)
            store.finalise_dataset(dataset_id, nodes_total, edges_total)
        except BaseException:
            logger.exception("ingest failed — discarding dataset_id=%s", dataset_id)
            store.discard_dataset(dataset_id)
            raise
        logger.info(
            "ingest complete (bulk) — dataset_id=%s nodes=%d edges=%d",
            dataset_id,
            nodes_total,
            edges_total,
        )
        return IngestReport(
            dataset_id=dataset_id,
            elements_read=records,
            nodes_upserted=nodes_total,
            edges_upserted=edges_total,
            violation_count=0,
        )

    nodes_total = 0
    edges_total = 0
    violation_count = 0
    elements_read = 0
    node_buf: list[TypedNode] = []
    edge_buf: list[TypedEdge] = []

    try:
        for element in reader.iter_elements():
            elements_read += 1
            if isinstance(element, SchemaViolation):
                violation_count += 1
                logger.warning(
                    "violation [%s] %s:%d — %s",
                    element.code,
                    element.source,
                    element.line,
                    element.message,
                )
                continue
            if isinstance(element, TypedNode):
                if not schema.allows_node(element.type):
                    violation_count += 1
                    logger.warning(
                        "violation [invalid_node_type] node id=%s — type %r not in schema",
                        element.id,
                        element.type,
                    )
                    continue
                node_buf.append(element)
            elif isinstance(element, TypedEdge):
                if not schema.allows_edge(element.type):
                    violation_count += 1
                    logger.warning(
                        "violation [invalid_edge_type] %s→%s — type %r not in schema",
                        element.src_id,
                        element.dst_id,
                        element.type,
                    )
                    continue
                edge_buf.append(element)

            if len(node_buf) + len(edge_buf) >= _BATCH_SIZE:
                store.upsert(dataset_id, node_buf, edge_buf)
                nodes_total += len(node_buf)
                edges_total += len(edge_buf)
                logger.debug(
                    "batch upserted — nodes=%d edges=%d (running total nodes=%d edges=%d)",
                    len(node_buf),
                    len(edge_buf),
                    nodes_total,
                    edges_total,
                )
                node_buf.clear()
                edge_buf.clear()

        if node_buf or edge_buf:
            store.upsert(dataset_id, node_buf, edge_buf)
            nodes_total += len(node_buf)
            edges_total += len(edge_buf)

        store.finalise_dataset(dataset_id, nodes_total, edges_total)
    except BaseException:
        logger.exception("ingest failed — discarding dataset_id=%s", dataset_id)
        store.discard_dataset(dataset_id)
        raise

    logger.info(
        "ingest complete — dataset_id=%s nodes=%d edges=%d violations=%d",
        dataset_id,
        nodes_total,
        edges_total,
        violation_count,
    )
    return IngestReport(
        dataset_id=dataset_id,
        elements_read=elements_read,
        nodes_upserted=nodes_total,
        edges_upserted=edges_total,
        violation_count=violation_count,
    )


def run_projection(
    projection: ProjectionStage,
    spec: ProjectionSpec,
    view: DatasetView,
    params: dict[str, Any] | None = None,
) -> ProjectedGraphHandle:
    logger.info(
        "projection started — spec=%s dataset_id=%s params=%s",
        spec.name,
        view.dataset_id,
        params or {},
    )
    handle = projection.run(spec, params or {}, view)
    logger.info("projection complete — spec=%s dataset_id=%s", spec.name, view.dataset_id)
    return handle


def run_export(
    handle: ProjectedGraphHandle,
    exporter: ExporterStage,
    sink: BinaryIO,
    *,
    store: StoreStage | None = None,
    projection: ProjectionStage | None = None,
    schema: HINSchema | None = None,
    dataset_id: str | None = None,
) -> ExportReceipt:
    """Write a projected graph. When store, projection, schema, and dataset_id
    are all provided the receipt carries a snapshot_id; otherwise it doesn't.
    """
    logger.info("export started")
    receipt = exporter.write(handle, sink)
    if schema is not None:
        receipt = receipt.model_copy(update={"schema_version": schema.schema_version})
    if store and projection and schema and dataset_id:
        receipt = receipt.model_copy(
            update={"snapshot_id": _snapshot_id(store, projection, schema, dataset_id)}
        )
    logger.info(
        "export complete — format=%s nodes=%d edges=%d snapshot=%s",
        receipt.format,
        receipt.node_count,
        receipt.edge_count,
        (receipt.snapshot_id or "")[:12] or "—",
    )
    return receipt


def _snapshot_id(
    store: StoreStage, projection: ProjectionStage, schema: HINSchema, dataset_id: str
) -> str:
    sf = store.fingerprint(dataset_id)
    ef = projection.fingerprint()
    parts = f"{sf.content_hash}|{ef.project_hash}|{schema.schema_version}|{_TOOL_VERSION}"
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()
