from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

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
