"""In-memory backend for testing.

Provides a MemoryBackend implementation using Python dicts.
NOT suitable for production — for tests and development only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from agent_memory.context import TenantContext
from agent_memory.domain.audit import AuditEvent, AuditQuery
from agent_memory.domain.consent import ConsentGrant, ConsentRecord
from agent_memory.domain.memory import MemoryRecord, MemoryVersion
from agent_memory.domain.retrieval import RetrievedMemory
from agent_memory.exceptions import (
    ConsentNotFoundError,
    MemoryNotFoundError,
    TenantIsolationError,
)


class InMemoryBackend:
    """In-memory backend for testing.

    Stores all data in Python dicts.
    Implements basic tenant isolation via filtering.
    Does NOT implement RLS, encryption, or vector search.
    """

    def __init__(self) -> None:
        self._memories: dict[UUID, MemoryRecord] = {}
        self._versions: dict[tuple[UUID, int], MemoryVersion] = {}
        self._consent: dict[UUID, ConsentRecord] = {}
        self._audit: list[AuditEvent] = []

    async def initialize(self) -> None:
        pass  # No-op for in-memory

    async def close(self) -> None:
        self._memories.clear()
        self._versions.clear()
        self._consent.clear()
        self._audit.clear()

    # ── Memories ────────────────────────────────────────────────────────────

    async def save_memory(
        self,
        record: MemoryRecord,
        version: MemoryVersion,
        *,
        context: TenantContext,
    ) -> MemoryRecord:
        if record.tenant_id != context.tenant_id:
            raise TenantIsolationError("Tenant mismatch")
        self._memories[record.id] = record
        self._versions[(record.id, version.version)] = version
        return record

    async def get_memory(
        self,
        memory_id: UUID,
        *,
        context: TenantContext,
    ) -> MemoryRecord | None:
        record = self._memories.get(memory_id)
        if record and record.tenant_id != context.tenant_id:
            raise TenantIsolationError("Tenant mismatch")
        return record

    async def add_version(
        self,
        memory_id: UUID,
        version: MemoryVersion,
        *,
        context: TenantContext,
    ) -> MemoryVersion:
        record = self._memories.get(memory_id)
        if not record:
            raise MemoryNotFoundError(f"Memory {memory_id} not found")
        if record.tenant_id != context.tenant_id:
            raise TenantIsolationError("Tenant mismatch")
        self._versions[(memory_id, version.version)] = version
        record.current_version = version.version
        record.updated_at = datetime.now(timezone.utc)
        return version

    async def update_memory_status(
        self,
        memory_id: UUID,
        status: str,
        *,
        context: TenantContext,
    ) -> None:
        record = self._memories.get(memory_id)
        if not record:
            raise MemoryNotFoundError(f"Memory {memory_id} not found")
        if record.tenant_id != context.tenant_id:
            raise TenantIsolationError("Tenant mismatch")
        record.status = status  # type: ignore
        record.updated_at = datetime.now(timezone.utc)

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
        results: list[MemoryRecord] = []
        for record in self._memories.values():
            if record.tenant_id != tenant_id:
                continue
            if record.subject_id != subject_id:
                continue
            if purpose and record.purpose != purpose:
                continue
            if memory_type and record.memory_type != memory_type:
                continue
            if status and record.status != status:
                continue
            results.append(record)
        return results[offset:offset + limit]

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
        results: list[RetrievedMemory] = []
        for record in self._memories.values():
            if record.tenant_id != tenant_id:
                continue
            if record.subject_id != subject_id:
                continue
            if purpose and record.purpose != purpose:
                continue
            if memory_types and record.memory_type not in memory_types:
                continue
            if statuses and record.status not in statuses:
                continue
            if record.status != "active":
                continue
            if record.is_expired():
                continue

            version = self._versions.get((record.id, record.current_version))
            if not version:
                continue

            # Simple lexical match
            score = 0.5
            if query.lower() in version.searchable_summary.lower() or query.lower() in str(version.value).lower():
                score = 0.9

            results.append(
                RetrievedMemory(
                    id=record.id,
                    version=version.version,
                    memory_type=record.memory_type,
                    predicate=record.predicate,
                    value=version.value,
                    score=score,
                    score_breakdown={"lexical": score, "vector": 0.0, "recency": 1.0, "confidence": version.confidence},
                    confidence=version.confidence,
                    source_type=version.source_type,
                    sensitivity=version.sensitivity,
                    created_at=version.created_at,
                    searchable_summary=version.searchable_summary,
                    evidence_text=version.evidence_text,
                )
            )

        # Sort by score descending, limit
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    # ── Consent ─────────────────────────────────────────────────────────────

    async def save_consent(
        self,
        record: ConsentRecord,
        *,
        context: TenantContext,
    ) -> ConsentRecord:
        if record.tenant_id != context.tenant_id:
            raise TenantIsolationError("Tenant mismatch")
        self._consent[record.id] = record
        return record

    async def get_active_consent(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        purpose: str,
    ) -> ConsentRecord | None:
        for record in self._consent.values():
            if record.tenant_id != tenant_id:
                continue
            if record.subject_id != subject_id:
                continue
            if record.purpose != purpose:
                continue
            if record.is_active():
                return record
        return None

    async def revoke_consent(
        self,
        consent_id: UUID,
        *,
        context: TenantContext,
    ) -> ConsentRecord:
        record = self._consent.get(consent_id)
        if not record:
            raise ConsentNotFoundError(f"Consent {consent_id} not found")
        if record.tenant_id != context.tenant_id:
            raise TenantIsolationError("Tenant mismatch")
        record.revoke()
        return record

    async def list_consent(
        self,
        *,
        tenant_id: str,
        subject_id: str | None = None,
        limit: int = 100,
    ) -> list[ConsentRecord]:
        results: list[ConsentRecord] = []
        for record in self._consent.values():
            if record.tenant_id != tenant_id:
                continue
            if subject_id and record.subject_id != subject_id:
                continue
            results.append(record)
        return results[:limit]

    # ── Audit ───────────────────────────────────────────────────────────────

    async def audit(
        self,
        event: AuditEvent,
    ) -> None:
        self._audit.append(event)

    async def query_audit(
        self,
        query: AuditQuery,
    ) -> list[AuditEvent]:
        results: list[AuditEvent] = []
        for event in self._audit:
            if event.tenant_id != query.tenant_id:
                continue
            if query.actor_id and event.actor_id != query.actor_id:
                continue
            if query.action and event.action != query.action:
                continue
            if query.outcome and event.outcome != query.outcome:
                continue
            results.append(event)
        return results[-query.limit:] if results else []

    # ── Health ──────────────────────────────────────────────────────────────

    async def health_check(self) -> dict[str, bool]:
        return {"healthy": True, "type": "in_memory"}


class InMemoryBackendFactory:
    """Factory for InMemoryBackend."""

    async def create(self) -> InMemoryBackend:
        return InMemoryBackend()