from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from hinge.kernel.schema.typed_edge import TypedEdge
from hinge.kernel.schema.typed_node import TypedNode


class ProjectedGraphHandle(Protocol):
    """Lazy cursor over a materialised projection.

    Implementations stream rows from the result table — exporters must not
    assume the full graph fits in memory.
    """

    def iter_nodes(self) -> Iterator[TypedNode]: ...
    def iter_edges(self) -> Iterator[TypedEdge]: ...


class ProjectedGraph:
    """Concrete, in-memory ProjectedGraphHandle. Useful for tests."""

    def __init__(self, nodes: list[TypedNode], edges: list[TypedEdge]) -> None:
        self._nodes = nodes
        self._edges = edges

    def iter_nodes(self) -> Iterator[TypedNode]:
        return iter(self._nodes)

    def iter_edges(self) -> Iterator[TypedEdge]:
        return iter(self._edges)
