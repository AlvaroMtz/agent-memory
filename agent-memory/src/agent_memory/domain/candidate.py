"""MemoryCandidate model — represents a candidate extracted from a message.

Candidates are validated before being persisted as MemoryRecord + MemoryVersion.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agent_memory.constants import MemoryType


class MemoryCandidate(BaseModel):
    """A candidate memory extracted from a message.

    Must pass all validations before being persisted:
    - evidence_text must be a literal substring of the source
    - source_message_id must exist
    - source role must be eligible (user or trusted_tool)
    - confidence must meet threshold
    - explicitly_stated must be True
    """

    memory_type: MemoryType
    subject_key: str
    predicate: str
    value: Any  # JSON-serializable value

    source_message_id: str
    evidence_text: str
    source_role: str = "user"

    explicitly_stated: bool = True
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    sensitivity: str = "public"

    def is_valid(self) -> bool:
        """Basic validity check — detailed checks are done by policies."""
        return bool(self.source_message_id and self.evidence_text and self.predicate)

    @property
    def identity_key(self) -> tuple[str, str, str]:
        """Logical identity for contradiction detection.

        Returns (memory_type, subject_key, predicate)
        """
        return (self.memory_type, self.subject_key, self.predicate)
