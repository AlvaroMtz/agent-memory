"""Audit models — every operation in agent-memory is auditable."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from agent_memory.constants import AuditAction


class AuditEvent(BaseModel):
    """An auditable event in the agent-memory system.

    Append-only. Never modified after creation.
    Decrypted content, secrets, and keys are never logged.
    """

    id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    actor_id: str
    action: AuditAction | str

    resource_type: str | None = None  # e.g., "memory", "consent", "candidate"
    resource_id: str | None = None
    subject_id_hash: str | None = None  # hashed subject_id, never raw value

    outcome: str = "allowed"  # "allowed" or "denied"
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditQuery(BaseModel):
    """Parameters for querying the audit log."""

    tenant_id: str
    actor_id: str | None = None
    action: AuditAction | str | None = None
    outcome: str | None = None
    limit: int = 100
    offset: int = 0
    from_date: datetime | None = None
    to_date: datetime | None = None
