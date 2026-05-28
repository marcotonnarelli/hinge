"""Fast reader for the NumFocus flat GitHub activity event format.

Supports JSONL files that follow the schema:

    {
      "action":     "OpenPullRequest",
      "event_id":   "...",
      "date":       "2022-01-01T00:14:19Z",
      "actor":      { "id": ..., "login": "..." },
      "repository": { "id": ..., "name": "org/repo", "organisation": "..." },
      "details":    { ... }
    }

The reader implements the ``BulkIngestReader`` protocol: instead of yielding
``TypedNode`` / ``TypedEdge`` objects one row at a time, it asks the DuckDB
store to ingest the source file in a single set-based SQL pass. The actual
JSON-to-contract-table mapping lives in ``_numfocus_contract_adapter``.

For very different flat schemas, write a sibling reader rather than
subclassing — the adapter SQL is the meaningful surface to override, and
subclassing through a thin reader buys little.
"""

from __future__ import annotations

from pathlib import Path

from hinge.kernel.protocols.reader_stage import ReaderDescriptor
from hinge.kernel.protocols.store_stage import StoreStage
from hinge.stages.readers import _numfocus_contract_adapter

_SUPPORTED_FORMATS = frozenset({"jsonl"})


class NumFocusReader:
    """Bulk-ingest reader for NumFocus GitHub activity JSONL files."""

    def __init__(self, path: str | Path, format: str | None = None) -> None:
        self._path = Path(path)
        self._format = format or self._infer_format(self._path)
        if self._format not in _SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported format {self._format!r}. Supported: {sorted(_SUPPORTED_FORMATS)}"
            )

    def describe(self) -> ReaderDescriptor:
        return ReaderDescriptor(
            dataset="numfocus-hin",
            format=self._format,
            path=self._path,
            byte_size=self._path.stat().st_size,
        )

    def bulk_ingest(self, store: StoreStage, dataset_id: str) -> tuple[int, int, int]:
        # The adapter speaks DuckDB SQL directly; reach into the underlying
        # connection rather than indirecting through a generic store API that
        # would only ever have one implementation.
        conn = store._c()  # type: ignore[attr-defined]
        return _numfocus_contract_adapter.ingest(conn, dataset_id, self._path)

    @staticmethod
    def _infer_format(path: Path) -> str:
        ext = path.suffix.lower().lstrip(".")
        if ext in _SUPPORTED_FORMATS:
            return ext
        raise ValueError(
            f"Cannot infer format from extension {path.suffix!r}. "
            f"Pass format= explicitly. Supported: {sorted(_SUPPORTED_FORMATS)}"
        )
