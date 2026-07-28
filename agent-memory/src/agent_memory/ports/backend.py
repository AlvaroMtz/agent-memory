"""MemoryBackend port — abstract interface for memory storage.

All backend implementations must implement this protocol.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from agent_memory.context import MemoryContext, TenantContext
from agent_memory.domain.audit import AuditEvent, AuditQuery
from agent_memory.domain.consent import ConsentGrant, ConsentRecord
from agent_memory.domain.memory import MemoryRecord, MemoryVersion
from agent_memory.domain.retrieval import RetrievedMemory


@runtime_checkable
class MemoryBackend(Protocol):
    """Port for memory storage backends.

    The canonical implementation is PostgreSQL + pgvector.
    In-memory backend is provided for tests.
    """

    async def initialize(self) -> None:
        """Initialize the backend (migrations, schema setup, etc.)."""
        ...

    async def close(self) -> None:
        """Close the backend connection."""
        ...

    # ── Memories ────────────────────────────────────────────────────────────

    async def save_memory(
        self,
        record: MemoryRecord,
        version: MemoryVersion,
        *,
        context: TenantContext,
    ) -> MemoryRecord:
        """Save a new memory record with its first version."""
        ...

    async def get_memory(
        self,
        memory_id: UUID,
        *,
        context: TenantContext,
    ) -> MemoryRecord | None:
        """Get a memory record by ID."""
        ...

    async def add_version(
        self,
        memory_id: UUID,
        version: MemoryVersion,
        *,
        context: TenantContext,
    ) -> MemoryVersion:
        """Add a new version to an existing memory record."""
        ...

    async def update_memory_status(
        self,
        memory_id: UUID,
        status: str,
        *,
        context: TenantContext,
    ) -> None:
        """Update the status of a memory record."""
        ...

    async def list_memories(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        purpose: str | None = None,
        memory_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        """List memory records matching the given filters."""
        ...

    # ── Retrieval ───────────────────────────────────────────────────────────

    async def retrieve(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        purpose: str | None = None,
        query: str,
        memory_types: list[str] | None = None,
        statuses: list[str] | None = None,
        limit: int = 8,
        token_budget: int = 1200,
    ) -> list[RetrievedMemory]:
        """Hybrid retrieval: vector + lexical + structured filters."""
        ...

    # ── Consent ─────────────────────────────────────────────────────────────

    async def save_consent(
        self,
        record: ConsentRecord,
        *,
        context: TenantContext,
    ) -> ConsentRecord:
        """Save a new consent record."""
        ...

    async def get_active_consent(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        purpose: str,
    ) -> ConsentRecord | None:
        """Get the active consent record for a given subject and purpose."""
        ...

    async def revoke_consent(
        self,
        consent_id: UUID,
        *,
        context: TenantContext,
    ) -> ConsentRecord:
        """Revoke a consent record."""
        ...

    async def list_consent(
        self,
        *,
        tenant_id: str,
        subject_id: str | None = None,
        limit: int = 100,
    ) -> list[ConsentRecord]:
        """List consent records."""
        ...

    # ── Audit ───────────────────────────────────────────────────────────────

    async def audit(
        self,
        event: AuditEvent,
    ) -> None:
        """Record an audit event."""
        ...

    async def query_audit(
        self,
        query: AuditQuery,
    ) -> list[AuditEvent]:
        """Query the audit log."""
        ...

    # ── Health / Doctor ─────────────────────────────────────────────────────

    async def health_check(self) -> dict[str, bool]:
        """Check backend health."""
        ...


class MemoryBackendFactory(Protocol):
    """Factory for creating MemoryBackend instances."""

    async def create(self, **kwargs) -> MemoryBackend:
        """Create a MemoryBackend instance."""
        ...