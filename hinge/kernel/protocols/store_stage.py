from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import datetime
from types import TracebackType
from typing import Protocol

from pydantic import BaseModel

from hinge.kernel.protocols.dataset_view import DatasetView
from hinge.kernel.schema.typed_edge import TypedEdge
from hinge.kernel.schema.typed_node import TypedNode


class StoreFingerprint(BaseModel):
    """Content hash of one dataset inside a store. Used to compute snapshot_id."""

    dataset_id: str
    schema_version: int
    node_count: int
    edge_count: int
    content_hash: str


class StoreCensus(BaseModel):
    """Per-type counts for one dataset."""

    nodes_by_type: dict[str, int]
    edges_by_type: dict[str, int]


class DatasetMeta(BaseModel):
    dataset_id: str
    reader: str
    path: str
    ingested_at: datetime
    node_count: int | None = None
    edge_count: int | None = None


class StoreStage(Protocol):
    """Persists typed graph elements and surfaces them to projections.

    The store is a context manager: it acquires whatever resources it needs
    (file lock, connection, transaction) on ``__enter__`` and releases them on
    ``__exit__``. This makes the DuckDB single-writer lock explicit at the
    call site rather than buried inside method calls.
    """

    def __enter__(self) -> StoreStage: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    # ---- ingest ----
    def begin_dataset(self, dataset_id: str, reader: str, path: str) -> None: ...
    def finalise_dataset(self, dataset_id: str, node_count: int, edge_count: int) -> None: ...
    def upsert(
        self, dataset_id: str, nodes: Iterable[TypedNode], edges: Iterable[TypedEdge]
    ) -> int: ...
    def discard_dataset(self, dataset_id: str) -> None: ...

    # ---- read / project ----
    def scope_to_dataset(self, dataset_id: str) -> DatasetView: ...
    def query(self, dataset_id: str, node_types: list[str]) -> Iterator[TypedNode]: ...
    def census(self, dataset_id: str) -> StoreCensus: ...
    def fingerprint(self, dataset_id: str) -> StoreFingerprint: ...
    def list_datasets(self) -> list[DatasetMeta]: ...
