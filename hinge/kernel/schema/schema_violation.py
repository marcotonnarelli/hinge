from __future__ import annotations

from pydantic import BaseModel


class SchemaViolation(BaseModel):
    code: str
    message: str
    source: str
    line: int

    def as_exception(self) -> SchemaViolationError:
        return SchemaViolationError(self)


class SchemaViolationError(Exception):
    def __init__(self, violation: SchemaViolation) -> None:
        super().__init__(
            f"[{violation.code}] {violation.source}:{violation.line} — {violation.message}"
        )
        self.violation = violation
