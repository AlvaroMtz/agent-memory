"""Consent domain models.

Consent is not a boolean — it is a versioned, granular permission grant.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from agent_memory.constants import Sensitivity


class ConsentGrant(BaseModel):
    """A consent grant request — specifies what and for how long."""

    purpose: str
    allow_write: bool = False
    allow_read: bool = False
    allowed_memory_types: set[str] = Field(default_factory=lambda: {"preference"})  # type: ignore[valid-type]
    allowed_sensitivity: set[str] = Field(default_factory=lambda: {"public", "internal"})  # type: ignore[valid-type]
    retention_days: int | None = None
    expires_at: datetime | None = None


class ConsentRecord(BaseModel):
    """A stored consent record — versioned and immutable in its core attributes.

    When consent is modified, a new version is created.
    The record can be revoked, which blocks reads and writes immediately.
    """

    id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    subject_id: str
    actor_id: str

    purpose: str
    allow_write: bool
    allow_read: bool
    allowed_memory_types: set[str]
    allowed_sensitivity: set[str]
    retention_days: int | None = None

    version: int = 1
    revoked_at: datetime | None = None
    expires_at: datetime | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_active(self) -> bool:
        """Check if this consent is currently active."""
        if self.revoked_at is not None:
            return False
        if self.expires_at and self.expires_at < datetime.now(timezone.utc):
            return False
        return True

    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def allows_write(self, memory_type: str, sensitivity: str) -> bool:
        """Check if write is allowed for the given memory type and sensitivity."""
        if not self.is_active():
            return False
        if not self.allow_write:
            return False
        if memory_type not in self.allowed_memory_types:
            return False
        if sensitivity not in self.allowed_sensitivity:
            return False
        return True

    def allows_read(self, memory_type: str, sensitivity: str) -> bool:
        """Check if read is allowed for the given memory type and sensitivity."""
        if not self.is_active():
            return False
        if not self.allow_read:
            return False
        if memory_type not in self.allowed_memory_types:
            return False
        if sensitivity not in self.allowed_sensitivity:
            return False
        return True

    def revoke(self) -> None:
        """Revoke this consent record."""
        self.revoked_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)