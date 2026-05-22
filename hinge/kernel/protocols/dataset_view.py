from __future__ import annotations

from pathlib import Path
from typing import Protocol


class DatasetView(Protocol):
    """Read-only handle to one dataset inside a store.

    Stores produce this via :meth:`StoreStage.scope_to_dataset`; projections
    consume it. Today every store backend ships a SQL view of the dataset so
    the projection can read it with whatever query engine fits — the fields
    are intentionally concrete (path + view names) rather than an abstract
    "query handle", because every real projection backend needs either SQL
    or row iteration anyway.

    A future non-SQL store can implement this by writing its dataset out to
    a temporary DuckDB file before returning — the contract stays one shape.
    """

    @property
    def dataset_id(self) -> str: ...
    @property
    def db_path(self) -> Path: ...
    @property
    def nodes_view(self) -> str: ...
    @property
    def edges_view(self) -> str: ...

    def close(self) -> None: ...
