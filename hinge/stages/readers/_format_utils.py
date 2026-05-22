"""Shared file-format parsing utilities for readers.

These are internal helpers — import them only from within hinge.stages.readers.
They are not part of the public protocol and are not exported from hinge.kernel.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any


def iter_jsonl(path: Path) -> Iterator[tuple[dict[str, Any], int]]:
    """Yield (parsed_dict, line_number) for every non-empty line in a JSONL file."""
    import orjson

    with path.open("rb") as fh:
        for lineno, line in enumerate(fh, start=1):
            if line.strip():
                yield orjson.loads(line), lineno


def iter_csv(path: Path) -> Iterator[tuple[dict[str, Any], int]]:
    """Yield (row_dict, row_number) for every row in a CSV file."""
    import csv

    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for lineno, row in enumerate(reader, start=2):  # 2: header is row 1
            yield dict(row), lineno


def iter_parquet(path: Path) -> Iterator[tuple[dict[str, Any], int]]:
    """Yield (row_dict, row_index) for every row in a Parquet file."""
    import pyarrow.parquet as pq

    table = pq.read_table(path)  # type: ignore[no-untyped-call]  # pyarrow stubs incomplete
    for i, batch in enumerate(table.to_batches()):
        for row in batch.to_pylist():
            yield row, i
