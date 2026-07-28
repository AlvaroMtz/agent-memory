"""Tests for GDPR forget application service."""

from __future__ import annotations

import pytest

from agent_memory.application.forget import ForgetService
from agent_memory.context import TenantContext
from agent_memory.domain.audit import AuditQuery
from agent_memory.domain.consent import ConsentRecord
from agent_memory.domain.memory import MemoryRecord, MemoryVersion
from agent_memory.providers.in_memory_backend import InMemoryBackend


async def _save_memory(backend: InMemoryBackend, tenant_id: str, subject_id: str) -> MemoryRecord:
    record = MemoryRecord(
        tenant_id=tenant_id,
        subject_id=subject_id,
        purpose="testing",
        memory_type="preference",
        subject_key="code",
        predicate="code_language",
        status="active",
        current_version=1,
    )
    version = MemoryVersion(
        memory_id=record.id,
        version=1,
        value="Python",
        confidence=1.0,
        sensitivity="public",
    )
    return await backend.save_memory(record, version, context=TenantContext(tenant_id=tenant_id))


@pytest.fixture()
async def backend() -> InMemoryBackend:
    backend = InMemoryBackend()
    await backend.initialize()
    return backend


@pytest.mark.asyncio
async def test_forget_subject_soft_deletes_memories_and_audits(backend: InMemoryBackend) -> None:
    memory = await _save_memory(backend, "tenant-a", "subject-1")
    service = ForgetService(backend)

    await service.forget_subject("tenant-a", "subject-1", actor_id="admin")

    deleted = await backend.get_memory(memory.id, context=TenantContext(tenant_id="tenant-a"))
    audit = await backend.query_audit(AuditQuery(tenant_id="tenant-a"))

    assert deleted is not None
    assert deleted.status == "deleted"
    assert audit[-1].action == "memory.deleted"
    assert audit[-1].metadata["count"] == 1


@pytest.mark.asyncio
async def test_forget_tenant_deletes_each_subject_once(backend: InMemoryBackend) -> None:
    await _save_memory(backend, "tenant-a", "subject-1")
    await _save_memory(backend, "tenant-a", "subject-2")
    await backend.save_consent(
        ConsentRecord(
            tenant_id="tenant-a",
            subject_id="subject-1",
            actor_id="actor",
            purpose="testing",
            allow_write=True,
            allow_read=True,
            allowed_memory_types={"preference"},
            allowed_sensitivity={"public"},
        ),
        context=TenantContext(tenant_id="tenant-a"),
    )
    await backend.save_consent(
        ConsentRecord(
            tenant_id="tenant-a",
            subject_id="subject-2",
            actor_id="actor",
            purpose="testing",
            allow_write=True,
            allow_read=True,
            allowed_memory_types={"preference"},
            allowed_sensitivity={"public"},
        ),
        context=TenantContext(tenant_id="tenant-a"),
    )

    await ForgetService(backend).forget_tenant("tenant-a", actor_id="admin")

    memories_1 = await backend.list_memories(tenant_id="tenant-a", subject_id="subject-1", status="deleted")
    memories_2 = await backend.list_memories(tenant_id="tenant-a", subject_id="subject-2", status="deleted")
    audit = await backend.query_audit(AuditQuery(tenant_id="tenant-a"))

    assert len(memories_1) == 1
    assert len(memories_2) == 1
    assert audit[-1].resource_type == "tenant"
    assert audit[-1].metadata == {"count": 2, "subjects_count": 2}


@pytest.mark.asyncio
async def test_list_subject_memories(backend: InMemoryBackend) -> None:
    await _save_memory(backend, "tenant-a", "subject-1")

    memories = await ForgetService(backend).list_subject_memories("tenant-a", "subject-1")

    assert len(memories) == 1
    assert memories[0].predicate == "code_language"
