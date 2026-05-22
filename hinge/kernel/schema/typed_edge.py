from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TypedEdge(BaseModel):
    """A typed graph edge. ``type`` is an open string label — projections may
    introduce new labels (e.g. ``"interacted_with"``) without touching any enum.
    Validated against :class:`HINSchema` only at the ingest boundary; downstream
    stages treat labels as opaque strings.
    """

    type: str
    src_id: str
    dst_id: str
    timestamp: datetime | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)
