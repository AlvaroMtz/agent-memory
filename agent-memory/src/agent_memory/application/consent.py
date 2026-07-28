"""Consent application service.

Provides high-level consent operations: grant, revoke, and policy checks
that enforce consent before memory reads and writes.
"""

from __future__ import annotations

from uuid import UUID

from agent_memory.context import MemoryContext, TenantContext
from agent_memory.domain.audit import AuditEvent
from agent_memory.domain.consent import ConsentGrant, ConsentRecord
from agent_memory.exceptions import (
    ConsentDeniedError,
    ConsentExpiredError,
    ConsentNotFoundError,
    ConsentRevokedError,
    MissingTenantError,
)
from agent_memory.ports.backend import MemoryBackend
from agent_memory.ports.telemetry import TelemetryProvider


class ConsentService:
    """Application service for consent management.

    Provides grant, revoke, and check operations.
    Uses MemoryBackend for persistence and TelemetryProvider for audit.
    """

    def __init__(
        self,
        backend: MemoryBackend,
        telemetry: TelemetryProvider | None = None,
    ) -> None:
        self._backend = backend
        self._telemetry = telemetry

    async def grant_consent(
        self,
        tenant_id: str,
        subject_id: str,
        actor_id: str,
        grant: ConsentGrant,
        *,
        request_id: str = "",
    ) -> ConsentRecord:
        """Grant consent for a subject under a tenant.

        Creates a new ConsentRecord from the grant parameters and persists it.
        Audits the grant on success.
        """
        context = TenantContext(tenant_id=tenant_id, actor_id=actor_id)

        record = ConsentRecord(
            tenant_id=tenant_id,
            subject_id=subject_id,
            actor_id=actor_id,
            purpose=grant.purpose,
            allow_write=grant.allow_write,
            allow_read=grant.allow_read,
            allowed_memory_types=grant.allowed_memory_types,
            allowed_sensitivity=grant.allowed_sensitivity,
            retention_days=grant.retention_days,
            expires_at=grant.expires_at,
        )

        saved = await self._backend.save_consent(record, context=context)

        await self._audit(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="consent.granted",
            resource_id=str(saved.id),
            outcome="allowed",
        )

        return saved

    async def revoke_consent(
        self,
        consent_id: UUID,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> ConsentRecord:
        """Revoke a previously granted consent by its ID.

        Audits the revocation on success.
        """
        context = TenantContext(tenant_id=tenant_id, actor_id=actor_id)
        revoked = await self._backend.revoke_consent(consent_id, context=context)

        await self._audit(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="consent.revoked",
            resource_id=str(consent_id),
            outcome="allowed",
        )

        return revoked

    async def check_consent_for_write(
        self,
        subject_id: str,
        memory_type: str,
        sensitivity: str,
        *,
        tenant_id: str,
        purpose: str,
    ) -> bool:
        """Check whether a write operation is allowed for the given parameters.

        Returns True if active consent exists and permits the write.
        Returns False if no consent exists or consent explicitly forbids the write.
        Never raises — callers receive a boolean for policy enforcement.
        """
        if not tenant_id:
            return False

        try:
            consent = await self._backend.get_active_consent(
                tenant_id=tenant_id,
                subject_id=subject_id,
                purpose=purpose,
            )
        except Exception:
            return False

        if consent is None:
            return False

        return consent.allows_write(memory_type, sensitivity)

    async def check_consent_for_read(
        self,
        subject_id: str,
        memory_type: str,
        sensitivity: str,
        *,
        tenant_id: str,
        purpose: str,
    ) -> bool:
        """Check whether a read operation is allowed for the given parameters.

        Returns True if active consent exists and permits the read.
        Returns False if no consent exists or consent explicitly forbids the read.
        Never raises — callers receive a boolean for policy enforcement.
        """
        if not tenant_id:
            return False

        try:
            consent = await self._backend.get_active_consent(
                tenant_id=tenant_id,
                subject_id=subject_id,
                purpose=purpose,
            )
        except Exception:
            return False

        if consent is None:
            return False

        return consent.allows_read(memory_type, sensitivity)

    async def get_consent(
        self,
        consent_id: UUID,
        *,
        tenant_id: str,
    ) -> ConsentRecord | None:
        """Retrieve a specific consent record."""
        context = TenantContext(tenant_id=tenant_id)
        try:
            return await self._backend.get_memory(consent_id, context=context)  # type: ignore[arg-type]
        except Exception:
            return None

    async def list_consent(
        self,
        *,
        tenant_id: str,
        subject_id: str | None = None,
        limit: int = 100,
    ) -> list[ConsentRecord]:
        """List consent records for a tenant, optionally filtered by subject."""
        return await self._backend.list_consent(
            tenant_id=tenant_id,
            subject_id=subject_id,
            limit=limit,
        )

    # ── Internal helpers ─────────────────────────────────────────────────────

    async def _audit(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        action: str,
        resource_id: str | None = None,
        outcome: str = "allowed",
        reason: str | None = None,
    ) -> None:
        """Audit a consent operation to the backend audit log."""
        event = AuditEvent(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action=action,
            resource_type="consent",
            resource_id=resource_id,
            outcome=outcome,
            reason=reason,
        )
        await self._backend.audit(event)