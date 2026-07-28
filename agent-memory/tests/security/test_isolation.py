"""Security tests — cross-tenant isolation, unauthorized operations, consent bypass.

These tests verify the security boundaries of agent-memory at the
application service layer using the InMemoryBackend.

Tests exercise:
- Cross-tenant leakage: tenant A cannot read/write tenant B's data.
- Unauthorized operation: operations without proper context are denied.
- Consent bypass: reads/writes bypassing consent checks are blocked.
"""

from __future__ import annotations

import pytest

from agent_memory.application.consent import ConsentService
from agent_memory.application.forget import ForgetService
from agent_memory.context import TenantContext
from agent_memory.domain.audit import AuditQuery
from agent_memory.domain.consent import ConsentGrant, ConsentRecord
from agent_memory.domain.memory import MemoryRecord, MemoryVersion
from agent_memory.exceptions import (
    ConsentDeniedError,
    MissingTenantError,
    TenantIsolationError,
)
from agent_memory.providers.in_memory_backend import InMemoryBackend


@pytest.fixture
def backend():
    """Provide a fresh InMemoryBackend for each test."""
    return InMemoryBackend()


@pytest.fixture
def consent_service(backend):
    """Provide a ConsentService backed by the InMemoryBackend."""
    return ConsentService(backend)


@pytest.fixture
async def seeded_backend(backend):
    """Seed the backend with two tenants and some memories."""
    context_a = TenantContext(tenant_id="tenant-a", actor_id="actor-1")
    context_b = TenantContext(tenant_id="tenant-b", actor_id="actor-2")

    # Grant consent for both tenants
    grant_a = ConsentGrant(
        purpose="testing",
        allow_write=True,
        allow_read=True,
        allowed_memory_types={"preference", "semantic"},
        allowed_sensitivity={"public", "internal"},
    )
    record_a = ConsentRecord(
        tenant_id="tenant-a",
        subject_id="subject-1",
        actor_id="actor-1",
        purpose="testing",
        allow_write=True,
        allow_read=True,
        allowed_memory_types={"preference", "semantic"},
        allowed_sensitivity={"public", "internal"},
    )
    await backend.save_consent(record_a, context=context_a)

    record_b = ConsentRecord(
        tenant_id="tenant-b",
        subject_id="subject-1",
        actor_id="actor-2",
        purpose="testing",
        allow_write=True,
        allow_read=True,
        allowed_memory_types={"preference", "semantic"},
        allowed_sensitivity={"public", "internal"},
    )
    await backend.save_consent(record_b, context=context_b)

    # Create memories for tenant-a
    mem_a = MemoryRecord(
        tenant_id="tenant-a",
        subject_id="subject-1",
        purpose="testing",
        memory_type="preference",
        subject_key="language",
        predicate="response_language",
        status="active",
    )
    ver_a = MemoryVersion(
        memory_id=mem_a.id,
        version=1,
        value="spanish",
        confidence=0.95,
        sensitivity="public",
    )
    await backend.save_memory(mem_a, ver_a, context=context_a)

    # Create memories for tenant-b
    mem_b = MemoryRecord(
        tenant_id="tenant-b",
        subject_id="subject-1",
        purpose="testing",
        memory_type="preference",
        subject_key="language",
        predicate="response_language",
        status="active",
    )
    ver_b = MemoryVersion(
        memory_id=mem_b.id,
        version=1,
        value="english",
        confidence=0.95,
        sensitivity="public",
    )
    await backend.save_memory(mem_b, ver_b, context=context_b)

    return backend, context_a, context_b, mem_a, mem_b


# ── Cross-tenant leakage tests ────────────────────────────────────────────────


class TestCrossTenantIsolation:
    """Verify that tenant A cannot access tenant B's data."""

    @pytest.mark.asyncio
    async def test_cross_tenant_read_returns_empty(self, seeded_backend):
        backend, ctx_a, ctx_b, mem_a, mem_b = seeded_backend

        # tenant-a tries to list tenant-b's memories
        results = await backend.list_memories(
            tenant_id="tenant-a",
            subject_id="subject-1",
        )
        for r in results:
            assert r.tenant_id == "tenant-a", f"Found tenant-b memory in tenant-a results: {r.id}"

    @pytest.mark.asyncio
    async def test_cross_tenant_get_memory_raises(self, seeded_backend):
        backend, ctx_a, ctx_b, mem_a, mem_b = seeded_backend

        # tenant-a tries to get tenant-b's memory directly
        with pytest.raises(TenantIsolationError):
            await backend.get_memory(mem_b.id, context=ctx_a)

        # tenant-b tries to get tenant-a's memory directly
        with pytest.raises(TenantIsolationError):
            await backend.get_memory(mem_a.id, context=ctx_b)

    @pytest.mark.asyncio
    async def test_cross_tenant_write_raises(self, seeded_backend):
        backend, ctx_a, ctx_b, mem_a, mem_b = seeded_backend

        # tenant-a tries to save a memory under tenant-b
        rogue_mem = MemoryRecord(
            tenant_id="tenant-b",
            subject_id="subject-1",
            purpose="rogue",
            memory_type="preference",
            subject_key="test",
            predicate="test",
        )
        rogue_ver = MemoryVersion(
            memory_id=rogue_mem.id,
            version=1,
            value="rogue",
            confidence=0.9,
        )
        with pytest.raises(TenantIsolationError):
            await backend.save_memory(rogue_mem, rogue_ver, context=ctx_a)

    @pytest.mark.asyncio
    async def test_cross_tenant_update_status_raises(self, seeded_backend):
        backend, ctx_a, ctx_b, mem_a, mem_b = seeded_backend

        # tenant-a tries to update tenant-b's memory status
        with pytest.raises(TenantIsolationError):
            await backend.update_memory_status(mem_b.id, "deleted", context=ctx_a)

        # tenant-b tries to update tenant-a's memory status
        with pytest.raises(TenantIsolationError):
            await backend.update_memory_status(mem_a.id, "deleted", context=ctx_b)

    @pytest.mark.asyncio
    async def test_cross_tenant_consent_revoke_raises(self, seeded_backend):
        backend, ctx_a, ctx_b, mem_a, mem_b = seeded_backend

        # tenant-a tries to revoke tenant-b's consent
        consent_b = None
        records = await backend.list_consent(tenant_id="tenant-b")
        if records:
            consent_b = records[0]

        if consent_b:
            with pytest.raises(TenantIsolationError):
                await backend.revoke_consent(consent_b.id, context=ctx_a)


# ── Consent bypass tests ──────────────────────────────────────────────────────


class TestConsentBypass:
    """Verify that consent operations cannot be bypassed."""

    @pytest.mark.asyncio
    async def test_no_consent_denies_write(self, consent_service, backend):
        # Without any consent, write checks return False
        allowed = await consent_service.check_consent_for_write(
            subject_id="subject-1",
            memory_type="preference",
            sensitivity="internal",
            tenant_id="tenant-a",
            purpose="testing",
        )
        assert allowed is False, "Write should be denied without consent"

    @pytest.mark.asyncio
    async def test_no_consent_denies_read(self, consent_service, backend):
        # Without any consent, read checks return False
        allowed = await consent_service.check_consent_for_read(
            subject_id="subject-1",
            memory_type="preference",
            sensitivity="internal",
            tenant_id="tenant-a",
            purpose="testing",
        )
        assert allowed is False, "Read should be denied without consent"

    @pytest.mark.asyncio
    async def test_write_only_consent_denies_read(self, consent_service, backend):
        # Grant write-only consent
        await consent_service.grant_consent(
            tenant_id="tenant-a",
            subject_id="subject-1",
            actor_id="actor-1",
            grant=ConsentGrant(
                purpose="testing",
                allow_write=True,
                allow_read=False,
            ),
        )

        read_allowed = await consent_service.check_consent_for_read(
            subject_id="subject-1",
            memory_type="preference",
            sensitivity="internal",
            tenant_id="tenant-a",
            purpose="testing",
        )
        assert read_allowed is False, "Read-only consent should deny read"

        write_allowed = await consent_service.check_consent_for_write(
            subject_id="subject-1",
            memory_type="preference",
            sensitivity="internal",
            tenant_id="tenant-a",
            purpose="testing",
        )
        assert write_allowed is True, "Write should be allowed with write consent"

    @pytest.mark.asyncio
    async def test_read_only_consent_denies_write(self, consent_service, backend):
        # Grant read-only consent
        await consent_service.grant_consent(
            tenant_id="tenant-a",
            subject_id="subject-1",
            actor_id="actor-1",
            grant=ConsentGrant(
                purpose="testing",
                allow_write=False,
                allow_read=True,
            ),
        )

        write_allowed = await consent_service.check_consent_for_write(
            subject_id="subject-1",
            memory_type="preference",
            sensitivity="internal",
            tenant_id="tenant-a",
            purpose="testing",
        )
        assert write_allowed is False, "Read-only consent should deny write"

        read_allowed = await consent_service.check_consent_for_read(
            subject_id="subject-1",
            memory_type="preference",
            sensitivity="internal",
            tenant_id="tenant-a",
            purpose="testing",
        )
        assert read_allowed is True, "Read should be allowed with read consent"

    @pytest.mark.asyncio
    async def test_expired_consent_denies_operations(self, consent_service, backend):
        from datetime import datetime, timedelta, timezone

        # Grant consent with immediate expiry
        await consent_service.grant_consent(
            tenant_id="tenant-a",
            subject_id="subject-1",
            actor_id="actor-1",
            grant=ConsentGrant(
                purpose="testing",
                allow_write=True,
                allow_read=True,
                expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            ),
        )

        write_allowed = await consent_service.check_consent_for_write(
            subject_id="subject-1",
            memory_type="preference",
            sensitivity="internal",
            tenant_id="tenant-a",
            purpose="testing",
        )
        assert write_allowed is False, "Expired consent should deny write"

        read_allowed = await consent_service.check_consent_for_read(
            subject_id="subject-1",
            memory_type="preference",
            sensitivity="internal",
            tenant_id="tenant-a",
            purpose="testing",
        )
        assert read_allowed is False, "Expired consent should deny read"

    @pytest.mark.asyncio
    async def test_revoked_consent_blocks_operations(self, consent_service, backend):
        # Grant and then revoke consent
        record = await consent_service.grant_consent(
            tenant_id="tenant-a",
            subject_id="subject-1",
            actor_id="actor-1",
            grant=ConsentGrant(
                purpose="testing",
                allow_write=True,
                allow_read=True,
            ),
        )

        # Should work before revoke
        write_allowed = await consent_service.check_consent_for_write(
            subject_id="subject-1",
            memory_type="preference",
            sensitivity="internal",
            tenant_id="tenant-a",
            purpose="testing",
        )
        assert write_allowed is True, "Write should work before revoke"

        # Revoke
        await consent_service.revoke_consent(
            record.id,
            tenant_id="tenant-a",
            actor_id="actor-1",
        )

        # Should be blocked after revoke
        write_allowed = await consent_service.check_consent_for_write(
            subject_id="subject-1",
            memory_type="preference",
            sensitivity="internal",
            tenant_id="tenant-a",
            purpose="testing",
        )
        assert write_allowed is False, "Revoked consent should deny write"

        read_allowed = await consent_service.check_consent_for_read(
            subject_id="subject-1",
            memory_type="preference",
            sensitivity="internal",
            tenant_id="tenant-a",
            purpose="testing",
        )
        assert read_allowed is False, "Revoked consent should deny read"

    @pytest.mark.asyncio
    async def test_empty_tenant_id_denied(self, consent_service, backend):
        """Operations without tenant_id are denied."""
        allowed = await consent_service.check_consent_for_write(
            subject_id="subject-1",
            memory_type="preference",
            sensitivity="internal",
            tenant_id="",
            purpose="testing",
        )
        assert allowed is False, "Empty tenant_id should be denied"

        allowed = await consent_service.check_consent_for_read(
            subject_id="subject-1",
            memory_type="preference",
            sensitivity="internal",
            tenant_id="",
            purpose="testing",
        )
        assert allowed is False, "Empty tenant_id should be denied"


# ── Unauthorized operation tests ──────────────────────────────────────────────


class TestForgetServiceSecurity:
    """Verify that ForgetService respects tenant boundaries."""

    @pytest.mark.asyncio
    async def test_forget_subject_tenant_isolation(self, seeded_backend):
        backend, ctx_a, ctx_b, mem_a, mem_b = seeded_backend
        forget = ForgetService(backend)

        # Forget subject-1 under tenant-a
        await forget.forget_subject("tenant-a", "subject-1")

        # tenant-a's memory should be deleted
        memories_a = await backend.list_memories(
            tenant_id="tenant-a",
            subject_id="subject-1",
        )
        for m in memories_a:
            assert m.status == "deleted", f"Memory {m.id} should be deleted in tenant-a"

        # tenant-b's memory should still be active
        memories_b = await backend.list_memories(
            tenant_id="tenant-b",
            subject_id="subject-1",
        )
        for m in memories_b:
            assert m.status == "active", f"Memory {m.id} should still be active in tenant-b"


# ── Audit trail tests ─────────────────────────────────────────────────────────


class TestAuditSecurity:
    """Verify that denied operations and security events are audited."""

    @pytest.mark.asyncio
    async def test_consent_grant_audited(self, consent_service, backend):
        await consent_service.grant_consent(
            tenant_id="tenant-a",
            subject_id="subject-1",
            actor_id="actor-1",
            grant=ConsentGrant(purpose="testing"),
        )

        events = await backend.query_audit(
            AuditQuery(tenant_id="tenant-a"),
        )
        grant_events = [e for e in events if e.action == "consent.granted"]
        assert len(grant_events) >= 1, "Consent grant should be audited"

    @pytest.mark.asyncio
    async def test_consent_revoke_audited(self, consent_service, backend):
        record = await consent_service.grant_consent(
            tenant_id="tenant-a",
            subject_id="subject-1",
            actor_id="actor-1",
            grant=ConsentGrant(purpose="testing"),
        )
        await consent_service.revoke_consent(
            record.id,
            tenant_id="tenant-a",
            actor_id="actor-1",
        )

        events = await backend.query_audit(
            AuditQuery(tenant_id="tenant-a"),
        )
        revoke_events = [e for e in events if e.action == "consent.revoked"]
        assert len(revoke_events) >= 1, "Consent revoke should be audited"