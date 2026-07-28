"""Real PostgreSQL + pgvector integration tests.

These tests use Docker/Testcontainers and are intentionally separate from the
mocked repository tests. They verify the release-critical path with a real
database engine, real migrations, pgvector extension, RLS policies and the
public MemoryClient.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

pytest.importorskip("testcontainers")
pytest.importorskip("psycopg")
pytest.importorskip("pgvector")
pytest.importorskip("alembic")

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from agent_memory.client import MemoryClient
from agent_memory.config import DatabaseConfig, MemoryConfig
from agent_memory.context import MemoryContext, TenantContext
from agent_memory.domain.consent import ConsentGrant
from agent_memory.domain.memory import MemoryRecord, MemoryVersion
from agent_memory.postgres.backend import PostgresBackend
from agent_memory.providers.deterministic_embeddings import DeterministicEmbeddingProvider
from agent_memory.providers.rule_based_extractor import RuleBasedExtractor


@pytest.fixture(scope="session")
def postgres_uri() -> str:
    """Start a real pgvector-enabled PostgreSQL container."""

    container = DockerContainer("pgvector/pgvector:pg16")
    container.with_env("POSTGRES_DB", "agent_memory_test")
    container.with_env("POSTGRES_USER", "agent_memory")
    container.with_env("POSTGRES_PASSWORD", "agent_memory")
    container.with_exposed_ports(5432)
    container.waiting_for(
        LogMessageWaitStrategy("database system is ready to accept connections").with_startup_timeout(45)
    )
    container.start()
    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5432)
        yield f"postgresql+psycopg://agent_memory:agent_memory@{host}:{port}/agent_memory_test"
    finally:
        container.stop()


@pytest.fixture()
def migrated_postgres(postgres_uri: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Run Alembic migrations against the real container."""

    monkeypatch.setenv("AGENT_MEMORY_DATABASE__URI", postgres_uri)
    alembic_cfg = Config(str(Path("alembic.ini").resolve()))
    command.upgrade(alembic_cfg, "head")
    return postgres_uri


@pytest.mark.asyncio
async def test_real_postgres_pgvector_rls_and_memory_client(migrated_postgres: str) -> None:
    """End-to-end write/retrieve with pgvector and RLS enabled."""

    config = MemoryConfig(environment="testing", database=DatabaseConfig(uri=migrated_postgres))
    backend = PostgresBackend(config=config)
    embedder = DeterministicEmbeddingProvider(dimensions=128)
    ctx = MemoryContext(
        tenant_id="tenant-real-a",
        subject_id="subject-1",
        actor_id="actor-1",
        purpose="testing",
    )

    async with MemoryClient(
        backend=backend,
        extractor=RuleBasedExtractor(),
        embedder=embedder,
        consent=backend,
    ) as client:
        await client.grant_consent(
            context=ctx,
            grant=ConsentGrant(
                purpose="testing",
                allow_write=True,
                allow_read=True,
                allowed_memory_types={"preference", "semantic"},
                allowed_sensitivity={"public", "internal"},
            ),
        )
        remembered = await client.remember(
            context=ctx,
            messages=[{"id": "msg-1", "role": "user", "content": "I prefer Python"}],
        )
        assert remembered.count == 1

        retrieved = await client.retrieve(context=ctx, query="Python", limit=5)
        assert retrieved.total_count >= 1
        assert retrieved.results[0].score_breakdown["vector"] >= 0.0

    engine = create_async_engine(migrated_postgres)
    async with engine.begin() as conn:
        vector_installed = await conn.scalar(text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'"))
        assert vector_installed == 1

        rls_rows = (
            await conn.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE relname IN ('memories', 'memory_versions', 'consent', 'audit_log')"
                )
            )
        ).all()
        assert len(rls_rows) == 4
        assert all(row.relrowsecurity and row.relforcerowsecurity for row in rls_rows)
    await engine.dispose()


@pytest.mark.asyncio
async def test_real_postgres_cross_tenant_get_denied(migrated_postgres: str) -> None:
    """A tenant cannot fetch another tenant's memory by ID through the backend."""

    config = MemoryConfig(environment="testing", database=DatabaseConfig(uri=migrated_postgres))
    backend = PostgresBackend(config=config)
    await backend.initialize()
    try:
        record = MemoryRecord(
            tenant_id="tenant-real-owner",
            subject_id="subject-1",
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
            searchable_summary="code_language Python",
            confidence=0.95,
            sensitivity="public",
            embedding=[0.0] * 128,
        )
        await backend.save_memory(record, version, context=TenantContext(tenant_id="tenant-real-owner"))

        leaked = await backend.get_memory(record.id, context=TenantContext(tenant_id="tenant-real-other"))
        assert leaked is None
    finally:
        await backend.close()
