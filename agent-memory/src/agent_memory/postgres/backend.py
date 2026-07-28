"""PostgreSQL backend — complete MemoryBackend implementation.

Wires repositories (MemoryRepository, ConsentRepository, AuditRepository)
with the async session factory.

Provides all methods required by the MemoryBackend port protocol.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from agent_memory.config import MemoryConfig, load_config
from agent_memory.context import TenantContext
from agent_memory.domain.audit import AuditEvent, AuditQuery
from agent_memory.domain.consent import ConsentRecord
from agent_memory.domain.memory import MemoryRecord, MemoryVersion
from agent_memory.domain.retrieval import RetrievedMemory
from agent_memory.exceptions import (
    ConfigurationError,
    ConsentNotFoundError,
    MemoryNotFoundError,
    TenantIsolationError,
)
from agent_memory.postgres.repositories import (
    AuditRepository,
    ConsentRepository,
    MemoryRepository,
)
from agent_memory.postgres.session import create_engine, get_session, close_engine


class PostgresBackend:
    """PostgreSQL backend implementing the MemoryBackend port protocol.

    Uses async SQLAlchemy with asyncpg driver.
    RLS is configured via SET LOCAL transaction parameters.
    """

    def __init__(
        self,
        config: MemoryConfig | None = None,
    ) -> None:
        self._config = config or load_config()
        if self._config.embeddings.dimensions != 128:
            raise ConfigurationError(
                "PostgreSQL pgvector schema for v0.0.1 requires embeddings.dimensions=128"
            )
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the backend (create engine and sessionmaker)."""
        if self._initialized:
            return
        create_engine(self._config)
        self._initialized = True

    async def close(self) -> None:
        """Close the backend and dispose of the engine."""
        await close_engine()
        self._initialized = False

    # ── Session helper ───────────────────────────────────────────────────────────

    async def _with_session(self, tenant_id: str, actor_id: str | None = None):
        """Context manager for a scoped session with RLS context."""
        return get_session(tenant_id=tenant_id, actor_id=actor_id)

    # ── Memories ─────────────────────────────────────────────────────────────────

    async def save_memory(
        self,
        record: MemoryRecord,
        version: MemoryVersion,
        *,
        context: TenantContext,
    ) -> MemoryRecord:
        """Save a new memory record with its first version."""
        async with get_session(
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
        ) as session:
            repo = MemoryRepository(session)
            result = await repo.save(record, version)
            await session.commit()
            return result

    async def get_memory(
        self,
        memory_id: UUID,
        *,
        context: TenantContext,
    ) -> MemoryRecord | None:
        """Get a memory record by ID."""
        async with get_session(
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
        ) as session:
            repo = MemoryRepository(session)
            result = await repo.get(memory_id, tenant_id=context.tenant_id)
            return result

    async def add_version(
        self,
        memory_id: UUID,
        version: MemoryVersion,
        *,
        context: TenantContext,
    ) -> MemoryVersion:
        """Add a new version to an existing memory record."""
        async with get_session(
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
        ) as session:
            repo = MemoryRepository(session)
            result = await repo.add_version(
                memory_id, version, tenant_id=context.tenant_id,
            )
            await session.commit()
            return result

    async def update_memory_status(
        self,
        memory_id: UUID,
        status: str,
        *,
        context: TenantContext,
    ) -> None:
        """Update the status of a memory record."""
        async with get_session(
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
        ) as session:
            repo = MemoryRepository(session)
            await repo.update_status(memory_id, status, tenant_id=context.tenant_id)
            await session.commit()

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
        async with get_session(tenant_id=tenant_id) as session:
            repo = MemoryRepository(session)
            return await repo.list(
                tenant_id=tenant_id,
                subject_id=subject_id,
                purpose=purpose,
                memory_type=memory_type,
                status=status,
                limit=limit,
                offset=offset,
            )

    # ── Retrieval ───────────────────────────────────────────────────────────────

    async def retrieve(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        purpose: str | None = None,
        query: str,
        memory_types: list[str] | None = None,
        statuses: list[str] | None = None,
        query_vector: list[float] | None = None,
        limit: int = 8,
        token_budget: int = 1200,
    ) -> list[RetrievedMemory]:
        """Retrieve active memories using structured filters and lexical scoring.

        This backend returns the persisted current version value. Vector ranking
        is intentionally left at 0.0 unless a vector index is added by a later
        migration; the application-level retriever still exposes the score
        breakdown without fabricating vector similarity.
        """
        async with get_session(tenant_id=tenant_id) as session:
            repo = MemoryRepository(session)
            vector_rows = []
            if query_vector is not None:
                vector_rows = await repo.search_current_versions(
                    tenant_id=tenant_id,
                    subject_id=subject_id,
                    purpose=purpose,
                    memory_types=memory_types,
                    statuses=statuses,
                    query_vector=query_vector,
                    limit=limit,
                )

            if vector_rows:
                record_version_rows = vector_rows
            else:
                records = await repo.list(
                    tenant_id=tenant_id,
                    subject_id=subject_id,
                    purpose=purpose,
                    limit=50,
                )
                record_version_rows = []
                for record in records:
                    version = await repo.get_current_version(
                        record.id,
                        version=record.current_version,
                    )
                    if version is not None:
                        record_version_rows.append((record, version, 0.0))

            results: list[RetrievedMemory] = []
            for record, version, vector_score in record_version_rows:
                if record.status != "active":
                    continue
                if record.is_expired():
                    continue
                if memory_types and record.memory_type not in memory_types:
                    continue
                if statuses and record.status not in statuses:
                    continue

                search_text = f"{record.predicate} {record.subject_key} {version.searchable_summary}".lower()
                lexical_score = 0.5
                if query and query.lower() in search_text:
                    lexical_score = 0.9
                score = max(vector_score, lexical_score)

                results.append(
                    RetrievedMemory(
                        id=record.id,
                        version=record.current_version,
                        memory_type=record.memory_type,
                        predicate=record.predicate,
                        value=version.value,
                        score=score,
                        score_breakdown={
                            "lexical": lexical_score,
                            "vector": vector_score,
                            "recency": 1.0,
                            "confidence": 0.0,
                        },
                        confidence=version.confidence,
                        source_type=version.source_type,
                        sensitivity=version.sensitivity,
                        created_at=version.created_at,
                        searchable_summary=version.searchable_summary,
                        evidence_text=version.evidence_text,
                    )
                )

            results.sort(key=lambda r: r.score, reverse=True)
            return results[:limit]

    # ── Consent ─────────────────────────────────────────────────────────────────

    async def save_consent(
        self,
        record: ConsentRecord,
        *,
        context: TenantContext,
    ) -> ConsentRecord:
        """Save a new consent record."""
        async with get_session(
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
        ) as session:
            repo = ConsentRepository(session)
            result = await repo.save(record)
            await session.commit()
            return result

    async def get_active_consent(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        purpose: str,
    ) -> ConsentRecord | None:
        """Get the active consent for a subject and purpose."""
        async with get_session(tenant_id=tenant_id) as session:
            repo = ConsentRepository(session)
            return await repo.get_active(
                tenant_id=tenant_id,
                subject_id=subject_id,
                purpose=purpose,
            )

    async def revoke_consent(
        self,
        consent_id: UUID,
        *,
        context: TenantContext,
    ) -> ConsentRecord:
        """Revoke a consent record."""
        async with get_session(
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
        ) as session:
            repo = ConsentRepository(session)
            result = await repo.revoke(
                consent_id, tenant_id=context.tenant_id,
            )
            await session.commit()
            return result

    async def list_consent(
        self,
        *,
        tenant_id: str,
        subject_id: str | None = None,
        limit: int = 100,
    ) -> list[ConsentRecord]:
        """List consent records."""
        async with get_session(tenant_id=tenant_id) as session:
            repo = ConsentRepository(session)
            return await repo.list(
                tenant_id=tenant_id,
                subject_id=subject_id,
                limit=limit,
            )

    # ── Audit ───────────────────────────────────────────────────────────────────

    async def audit(
        self,
        event: AuditEvent,
    ) -> None:
        """Record an audit event."""
        async with get_session(tenant_id=event.tenant_id) as session:
            repo = AuditRepository(session)
            await repo.append(event)
            await session.commit()

    async def query_audit(
        self,
        query: AuditQuery,
    ) -> list[AuditEvent]:
        """Query the audit log."""
        async with get_session(tenant_id=query.tenant_id) as session:
            repo = AuditRepository(session)
            return await repo.query(query)

    # ── Health ──────────────────────────────────────────────────────────────────

    async def health_check(self) -> dict[str, bool]:
        """Check backend health."""
        try:
            async with get_session() as session:
                from sqlalchemy import text
                await session.execute(text("SELECT 1"))
            return {"healthy": True, "type": "postgres"}
        except Exception:
            return {"healthy": False, "type": "postgres"}


class PostgresBackendFactory:
    """Factory for creating PostgresBackend instances."""

    async def create(self, config: MemoryConfig | None = None) -> PostgresBackend:
        """Create a PostgresBackend instance.

        Args:
            config: Optional MemoryConfig. If None, uses default config.
        """
        backend = PostgresBackend(config=config)
        await backend.initialize()
        return backend
