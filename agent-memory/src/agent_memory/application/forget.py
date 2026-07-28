"""Forget application service.

GDPR-compliant forget operations: soft-delete all memories for a subject
or an entire tenant, with mandatory audit trail.
"""

from __future__ import annotations

from agent_memory.context import TenantContext
from agent_memory.domain.audit import AuditEvent
from agent_memory.domain.memory import MemoryRecord
from agent_memory.ports.backend import MemoryBackend


class ForgetService:
    """Application service for GDPR forget operations.

    Implements:
    - forget_subject: soft-deletes all memories for a subject within a tenant.
    - forget_tenant: soft-deletes all memories for an entire tenant.
    - list_subject_memories: lists all memories for audit/review before deletion.
    """

    def __init__(self, backend: MemoryBackend) -> None:
        self._backend = backend

    async def forget_subject(
        self,
        tenant_id: str,
        subject_id: str,
        *,
        actor_id: str = "system",
    ) -> None:
        """Soft-delete all memories for a subject within a tenant.

        GDPR Article 17 compliance: the data is not destroyed but marked as
        'deleted' so it can be recovered if needed within retention windows.
        """
        context = TenantContext(tenant_id=tenant_id, actor_id=actor_id)
        memories = await self._backend.list_memories(
            tenant_id=tenant_id,
            subject_id=subject_id,
            limit=10_000,
        )

        for memory in memories:
            await self._backend.update_memory_status(
                memory.id,
                "deleted",
                context=context,
            )

        await self._backend.audit(
            AuditEvent(
                tenant_id=tenant_id,
                actor_id=actor_id,
                action="memory.deleted",
                resource_type="memory",
                subject_id_hash=subject_id,
                outcome="allowed",
                reason=f"forget_subject: {len(memories)} memories soft-deleted",
                metadata={"subject_id": subject_id, "count": len(memories)},
            )
        )

    async def forget_tenant(
        self,
        tenant_id: str,
        *,
        actor_id: str = "system",
    ) -> None:
        """Soft-delete all memories for an entire tenant.

        This is a drastic operation. All subjects within the tenant lose
        their memories. Used for tenant deprovisioning.
        """
        context = TenantContext(tenant_id=tenant_id, actor_id=actor_id)
        total_count = 0

        # The backend may not support listing all subjects directly.
        # We iterate through consent records to discover subjects.
        consent_records = await self._backend.list_consent(
            tenant_id=tenant_id,
            limit=10_000,
        )
        seen_subjects: set[str] = set()
        for record in consent_records:
            if record.subject_id not in seen_subjects:
                seen_subjects.add(record.subject_id)
                memories = await self._backend.list_memories(
                    tenant_id=tenant_id,
                    subject_id=record.subject_id,
                    limit=10_000,
                )
                for memory in memories:
                    await self._backend.update_memory_status(
                        memory.id,
                        "deleted",
                        context=context,
                    )
                    total_count += 1

        await self._backend.audit(
            AuditEvent(
                tenant_id=tenant_id,
                actor_id=actor_id,
                action="memory.deleted",
                resource_type="tenant",
                outcome="allowed",
                reason=f"forget_tenant: {total_count} memories soft-deleted across {len(seen_subjects)} subjects",
                metadata={"count": total_count, "subjects_count": len(seen_subjects)},
            )
        )

    async def list_subject_memories(
        self,
        tenant_id: str,
        subject_id: str,
    ) -> list[MemoryRecord]:
        """List all memories for a subject within a tenant.

        Used for audit/review before initiating a forget operation.
        Returns records in any status, so the caller can assess what would be deleted.
        """
        return await self._backend.list_memories(
            tenant_id=tenant_id,
            subject_id=subject_id,
            limit=10_000,
        )