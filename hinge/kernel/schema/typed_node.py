from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TypedNode(BaseModel):
    """A typed graph node. ``type`` is an open string label — validated against
    a :class:`HINSchema` at ingest time, not constrained by a Python enum.
    """

    type: str
    id: str
    timestamp: datetime | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)
