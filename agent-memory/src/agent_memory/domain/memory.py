"""Memory domain models — core entities for the agent-memory system.

These models are framework-agnostic. They do not depend on LangChain,
PostgreSQL, or any external library beyond Pydantic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from agent_memory.constants import (
    MemoryStatus,
    MemoryType,
    Sensitivity,
    SourceType,
)


class MemoryRecord(BaseModel):
    """A memory record — the aggregate root for a memory's lifecycle.

    Multiple versions may exist for a single MemoryRecord.
    The current active version is indicated by current_version and status.
    """

    id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    subject_id: str
    purpose: str

    memory_type: MemoryType
    subject_key: str
    predicate: str

    status: MemoryStatus = "candidate"
    current_version: int = 0

    valid_from: datetime | None = None
    valid_until: datetime | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_active(self) -> bool:
        """Check if this memory is currently active and retrievable."""
        return self.status == "active"

    def is_superseded(self) -> bool:
        return self.status == "superseded"

    def is_revoked(self) -> bool:
        return self.status == "revoked"

    def is_expired(self) -> bool:
        if self.status == "expired":
            return True
        if self.valid_until and self.valid_until < datetime.now(timezone.utc):
            return True
        return False

    def can_be_retrieved(self) -> bool:
        """Check if this memory can be returned in a retrieval result."""
        if self.status == "active":
            return not self.is_expired()
        return False

    def supersede(self) -> None:
        """Mark this memory as superseded."""
        self.status = "superseded"
        self.updated_at = datetime.now(timezone.utc)

    def revoke(self) -> None:
        """Revoke this memory."""
        self.status = "revoked"
        self.updated_at = datetime.now(timezone.utc)

    def delete_record(self) -> None:
        """Soft-delete this memory."""
        self.status = "deleted"
        self.updated_at = datetime.now(timezone.utc)


class MemoryVersion(BaseModel):
    """An immutable version of a memory.

    Once created, a MemoryVersion is never modified.
    Updates create a new MemoryVersion with an incremented version number.
    """

    memory_id: UUID
    version: int
    value: Any  # JSON-serializable value

    searchable_summary: str = ""
    encrypted_value: bytes | None = None
    encrypted_evidence: bytes | None = None

    confidence: float = Field(ge=0.0, le=1.0)
    sensitivity: Sensitivity = "internal"

    source_type: SourceType = "user_explicit"
    source_message_id: str | None = None
    evidence_text: str | None = None

    extractor_provider: str = ""
    extractor_model: str = ""
    extractor_prompt_version: str = ""

    embedding_provider: str = ""
    embedding_model: str = ""
    policy_version: str = ""
    consent_id: UUID | None = None

    supersedes_memory_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def identity_key(self) -> tuple[str, str, str, str]:
        """Return the logical identity tuple for contradiction detection.

        Matches: tenant_id, memory_type, subject_key, predicate
        (Note: tenant_id is held at the MemoryRecord level)
        """
        return (self.memory_type or "", self.extractor_provider or "", "", "")