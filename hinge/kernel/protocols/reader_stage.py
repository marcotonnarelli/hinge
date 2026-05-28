from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from hinge.kernel.protocols.store_stage import StoreStage
from hinge.kernel.schema.schema_violation import SchemaViolation
from hinge.kernel.schema.typed_edge import TypedEdge
from hinge.kernel.schema.typed_node import TypedNode


class ReaderDescriptor(BaseModel):
    dataset: str
    format: str
    path: Path
    byte_size: int


class ReaderStage(Protocol):
    """Reads a dataset file and yields typed graph elements directly.

    A reader owns both the file-format parsing logic and the domain knowledge
    needed to map raw records to ``TypedNode`` / ``TypedEdge`` objects. It may
    also yield ``SchemaViolation`` instances for records it cannot map — the
    runner counts and logs them rather than aborting the ingest.
    """

    def iter_elements(self) -> Iterator[TypedNode | TypedEdge | SchemaViolation]: ...
    def describe(self) -> ReaderDescriptor: ...


@runtime_checkable
class BulkIngestReader(Protocol):
    """Reader that loads a whole dataset in one bulk operation against the store.

    Implementations push records directly into the store's native engine
    (e.g. DuckDB SQL) and return summary counts. The runner detects this
    shape and uses it in place of the element-by-element ``ReaderStage``
    path — useful when the file format and the store backend let us avoid
    a per-row Python round-trip.
    """

    def describe(self) -> ReaderDescriptor: ...
    def bulk_ingest(self, store: StoreStage, dataset_id: str) -> tuple[int, int, int]:
        """Load the dataset into ``store`` under ``dataset_id``.

        Returns ``(records_read, nodes_written, edges_written)``.
        """
        ...
