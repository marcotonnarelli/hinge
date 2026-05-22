from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class HINSchema(BaseModel):
    """The vocabulary of node and edge labels permitted at ingest.

    Loaded from ``hinge/config/types.yaml`` — the single source of truth.
    Labels are open strings; the schema simply enumerates which ones are
    accepted. Projections may introduce labels not listed here; they only
    bind ingest-time validation.
    """

    schema_version: int
    node_types: set[str] = Field(default_factory=set)
    edge_types: set[str] = Field(default_factory=set)
    artifact_subtypes: set[str] = Field(default_factory=set)

    @classmethod
    def from_yaml(cls, path: Path) -> HINSchema:
        raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            schema_version=int(raw["schema_version"]),
            node_types=set(raw.get("node_types", [])),
            edge_types=set(raw.get("edge_types", [])),
            artifact_subtypes=set(raw.get("artifact_subtypes", [])),
        )

    def allows_node(self, label: str) -> bool:
        return label in self.node_types

    def allows_edge(self, label: str) -> bool:
        return label in self.edge_types
