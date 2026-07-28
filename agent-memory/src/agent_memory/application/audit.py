"""Audit logging service.

Provides high-level audit logging and query operations.
Every operation in agent-memory is auditable and append-only.
Secrets and decrypted content are never logged.
"""

from __future__ import annotations

from agent_memory.domain.audit import AuditEvent, AuditQuery
from agent_memory.ports.backend import MemoryBackend


class AuditService:
    """Application service for audit logging.

    Provides log_action to record events and query_events to retrieve them.
    """

    def __init__(self, backend: MemoryBackend) -> None:
        self._backend = backend

    async def log_action(
        self,
        tenant_id: str,
        actor_id: str,
        action: str,
        *,
        memory_type: str | None = None,
        details: dict | None = None,
        outcome: str = "allowed",
        resource_type: str | None = None,
        resource_id: str | None = None,
        subject_id_hash: str | None = None,
        reason: str | None = None,
    ) -> AuditEvent:
        """Log an auditable action.

        Records the event in the backend's audit log.
        Returns the created AuditEvent for reference.
        """
        metadata: dict = {}
        if memory_type:
            metadata["memory_type"] = memory_type
        if details:
            metadata.update(details)

        event = AuditEvent(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            subject_id_hash=subject_id_hash,
            outcome=outcome,
            reason=reason,
            metadata=metadata,
        )

        await self._backend.audit(event)
        return event

    async def query_events(
        self,
        tenant_id: str,
        *,
        actor_id: str | None = None,
        action: str | None = None,
        outcome: str | None = None,
        limit: int = 50,
    ) -> list[AuditEvent]:
        """Query audit events for a tenant with optional filters."""
        query = AuditQuery(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action=action,
            outcome=outcome,
            limit=limit,
        )
        return await self._backend.query_audit(query)