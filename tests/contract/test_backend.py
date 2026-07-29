"""Contract tests for MemoryBackend.

Reusable test suite that any backend implementation must pass.
"""

from __future__ import annotations

import pytest

from agent_memory.context import TenantContext
from agent_memory.domain.audit import AuditEvent, AuditQuery
from agent_memory.domain.consent import ConsentRecord
from agent_memory.domain.memory import MemoryRecord, MemoryVersion
from agent_memory.ports.backend import MemoryBackend


class MemoryBackendContractSuite:
    """Contract test suite for MemoryBackend implementations.

    Usage:
        class TestMyBackend:
            @pytest.fixture
            async def backend(self):
                return await MyBackendFactory().create()

            def test_contract(self, backend):
                MemoryBackendContractSuite().run_all(backend)
    """

    async def run_all(self, backend: MemoryBackend) -> None:
        """Run all contract tests."""
        await self._test_save_and_get_memory(backend)
        await self._test_tenant_isolation(backend)
        await self._test_add_version(backend)
        await self._test_consent_lifecycle(backend)
        await self._test_audit_logging(backend)

    async def _test_save_and_get_memory(self, backend: MemoryBackend) -> None:
        ctx = TenantContext(tenant_id="contract-test")
        record = MemoryRecord(
            tenant_id="contract-test",
            subject_id="user-1",
            purpose="test",
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
        )
        version = MemoryVersion(
            memory_id=record.id,
            version=1,
            value="Python",
            confidence=0.95,
        )
        saved = await backend.save_memory(record, version, context=ctx)
        assert saved.id == record.id

        retrieved = await backend.get_memory(record.id, context=ctx)
        assert retrieved is not None
        assert retrieved.tenant_id == "contract-test"

    async def _test_tenant_isolation(self, backend: MemoryBackend) -> None:
        ctx_a = TenantContext(tenant_id="tenant-a")
        ctx_b = TenantContext(tenant_id="tenant-b")

        record = MemoryRecord(
            tenant_id="tenant-a",
            subject_id="user-1",
            purpose="test",
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
        )
        version = MemoryVersion(
            memory_id=record.id,
            version=1,
            value="Python",
            confidence=0.95,
        )
        await backend.save_memory(record, version, context=ctx_a)

        # List from tenant-b should not include tenant-a's memory
        results = await backend.list_memories(
            tenant_id="tenant-b",
            subject_id="user-1",
            limit=100,
        )
        assert len(results) == 0

    async def _test_add_version(self, backend: MemoryBackend) -> None:
        ctx = TenantContext(tenant_id="contract-test")
        record = MemoryRecord(
            tenant_id="contract-test",
            subject_id="user-1",
            purpose="test",
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            status="active",
        )
        v1 = MemoryVersion(
            memory_id=record.id,
            version=1,
            value="Python",
            confidence=0.95,
        )
        await backend.save_memory(record, v1, context=ctx)

        v2 = MemoryVersion(
            memory_id=record.id,
            version=2,
            value="TypeScript",
            confidence=0.95,
        )
        added = await backend.add_version(record.id, v2, context=ctx)
        assert added.version == 2

    async def _test_consent_lifecycle(self, backend: MemoryBackend) -> None:
        ctx = TenantContext(tenant_id="contract-test")
        record = ConsentRecord(
            tenant_id="contract-test",
            subject_id="user-1",
            actor_id="admin",
            purpose="test",
            allow_write=True,
            allow_read=True,
            allowed_memory_types={"preference", "semantic"},
            allowed_sensitivity={"public", "internal"},
        )
        saved = await backend.save_consent(record, context=ctx)
        assert saved.id == record.id

        active = await backend.get_active_consent(
            tenant_id="contract-test",
            subject_id="user-1",
            purpose="test",
        )
        assert active is not None
        assert active.is_active()

        revoked = await backend.revoke_consent(record.id, context=ctx)
        assert revoked.is_revoked()

    async def _test_audit_logging(self, backend: MemoryBackend) -> None:
        event = AuditEvent(
            tenant_id="contract-test",
            actor_id="admin",
            action="memory.retrieved",
        )
        await backend.audit(event)

        events = await backend.query_audit(AuditQuery(tenant_id="contract-test", limit=10))
        assert len(events) >= 1


class InMemoryBackendContractTest:
    """Run the contract suite against InMemoryBackend."""

    @pytest.fixture
    def backend(self):
        from agent_memory.providers.in_memory_backend import InMemoryBackend

        return InMemoryBackend()

    @pytest.mark.asyncio
    async def test_contract_suite(self, backend):
        await MemoryBackendContractSuite().run_all(backend)
