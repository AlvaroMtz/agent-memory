"""Tests for Memory Lab services and API."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from starlette.requests import Request

from agent_memory.context import TenantContext
from agent_memory.domain.audit import AuditEvent
from agent_memory.lab import app as lab_app
from agent_memory.lab.schemas import (
    ConsentGrantRequest,
    ConsentRevokeRequest,
    ConversationSimulationRequest,
    RetrieveRequest,
)
from agent_memory.lab.services import LabServices
from agent_memory.providers.in_memory_backend import InMemoryBackend
from agent_memory.providers.rule_based_extractor import RuleBasedExtractor


@pytest.fixture()
async def lab_services() -> LabServices:
    backend = InMemoryBackend()
    await backend.initialize()
    return LabServices(backend=backend, extractor=RuleBasedExtractor())


@pytest.mark.asyncio
async def test_lab_services_simulate_conversation(lab_services: LabServices) -> None:
    result = await lab_services.simulate_conversation(
        messages=[{"id": "m1", "role": "user", "content": "I prefer Python"}],
        agent_id="subject-1",
    )

    assert result["errors"] == []
    assert result["extracted"][0]["predicate"] == "code_language"


@pytest.mark.asyncio
async def test_lab_services_consent_add_retrieve_and_revoke(lab_services: LabServices) -> None:
    granted = await lab_services.grant_consent("default", ["preference"], sensitivity="public")
    saved = await lab_services.add_memory(
        "preference", "code_language", "Python", subject_id="default"
    )
    retrieved = await lab_services.run_retrieval(query="", subject_id="default")
    revoked = await lab_services.revoke_consent("default")

    assert granted is True
    assert saved is not None
    assert retrieved["total_count"] >= 1
    assert revoked is True


@pytest.mark.asyncio
async def test_lab_services_stats_and_audit_log(lab_services: LabServices) -> None:
    await lab_services.add_memory("preference", "code_language", "Python", subject_id="default")
    await lab_services.backend.audit(
        AuditEvent(tenant_id="default", actor_id="lab", action="memory.test", outcome="ok")
    )

    stats = await lab_services.get_stats()
    audit_log = await lab_services.get_audit_log(limit=10)

    assert stats["total_memories"] == 1
    assert stats["by_type"] == {"preference": 1}
    assert audit_log[0]["action"] == "memory.test"


@pytest.mark.asyncio
async def test_lab_services_error_paths() -> None:
    class FailingExtractor:
        async def extract(self, **kwargs):
            raise RuntimeError("boom")

    class FailingBackend(InMemoryBackend):
        async def list_memories(self, **kwargs):
            raise RuntimeError("list failed")

        async def query_audit(self, query):
            raise RuntimeError("audit failed")

        async def save_consent(self, record, *, context: TenantContext):
            raise RuntimeError("consent failed")

        async def save_memory(self, record, version, *, context: TenantContext):
            raise RuntimeError("memory failed")

    backend = FailingBackend()
    await backend.initialize()
    services = LabServices(backend=backend, extractor=FailingExtractor())

    simulated = await services.simulate_conversation(
        [{"role": "user", "content": "I prefer Python"}]
    )
    stats = await services.get_stats()
    audit = await services.get_audit_log()
    granted = await services.grant_consent("subject", ["preference"])
    saved = await services.add_memory("preference", "code_language", "Python")
    retrieved = await services.run_retrieval("Python")

    assert simulated["errors"]
    assert stats["total_memories"] == 0
    assert audit[0]["action"] == "error"
    assert granted is False
    assert saved is None
    assert retrieved["total_count"] == 0


@pytest.mark.asyncio
async def test_lab_api_health_and_json_endpoints(lab_services: LabServices) -> None:
    assert await lab_app.health_check() == {"status": "ok", "version": "0.0.1"}

    simulation = await lab_app.simulate_conversation(
        ConversationSimulationRequest(
            agent_id="subject-1",
            messages=[{"id": "m1", "role": "user", "content": "I prefer Python"}],
        ),
        services=lab_services,
    )
    assert simulation.extracted[0]["predicate"] == "code_language"

    granted = await lab_app.grant_consent(
        ConsentGrantRequest(
            subject_id="default", memory_types=["preference"], sensitivity="public"
        ),
        services=lab_services,
    )
    retrieved = await lab_app.search_memory(
        RetrieveRequest(query="", subject_id="default"), services=lab_services
    )
    revoked = await lab_app.revoke_consent(
        ConsentRevokeRequest(subject_id="default"), services=lab_services
    )

    assert granted.status_code == 200
    assert retrieved.total_count >= 0
    assert revoked.status_code == 200


@pytest.mark.asyncio
async def test_lab_api_pages_render(lab_services: LabServices) -> None:
    request = Request(
        {"type": "http", "method": "GET", "path": "/", "headers": [], "app": lab_app.app}
    )

    responses = [
        await lab_app.dashboard(request, services=lab_services),
        await lab_app.conversation_page(request),
        await lab_app.extract_page(request),
        await lab_app.retrieve_page(request),
        await lab_app.consent_page(request),
        await lab_app.audit_page(request),
    ]

    assert all(response.status_code == 200 for response in responses)
