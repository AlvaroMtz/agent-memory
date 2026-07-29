"""Remember result — outcome of a memory extraction and persistence operation."""

from __future__ import annotations

from pydantic import BaseModel

from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.domain.memory import MemoryRecord, MemoryVersion


class RememberResult(BaseModel):
    """Complete result of a memory remember operation.

    Includes both the extracted candidates and the persisted records,
    along with audit and encryption metadata.
    """

    candidates: list[MemoryCandidate]
    memories: list[MemoryRecord]
    versions: list[MemoryVersion]
    count: int

    audit_id: str | None = None
    encrypted: bool = False

    purpose: str = ""
    tenant_id: str = ""
    subject_id: str = ""

    @property
    def empty(self) -> bool:
        return self.count == 0
