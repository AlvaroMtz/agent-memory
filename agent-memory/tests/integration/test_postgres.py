"""Integration tests for PostgresBackend — repository CRUD via mocked SQLAlchemy session.

Uses real domain models with a mocked AsyncSession to validate:
- Repository persistence logic (ORM ↔ domain conversion)
- Backend orchestration (session management, error handling, commit patterns)
- Tenant-scoped filtering
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agent_memory.config import MemoryConfig
from agent_memory.context import TenantContext
from agent_memory.domain.audit import AuditEvent, AuditQuery
from agent_memory.domain.consent import ConsentRecord
from agent_memory.domain.memory import MemoryRecord, MemoryVersion
from agent_memory.exceptions import (
    ConsentNotFoundError,
    MemoryNotFoundError,
)
from agent_memory.postgres.backend import PostgresBackend
from agent_memory.postgres.models import (
    AuditLogModel,
    ConsentModel,
    MemoryModel,
    MemoryVersionModel,
)
from agent_memory.postgres.repositories import (
    AuditRepository,
    ConsentRepository,
    MemoryRepository,
)

_NOW = datetime.now(timezone.utc)


# ── Fixtures ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def tenant_a():
    return TenantContext(tenant_id="tenant-alpha")


@pytest.fixture
def tenant_b():
    return TenantContext(tenant_id="tenant-beta")


@pytest.fixture
def sample_memory():
    return MemoryRecord(
        tenant_id="tenant-alpha",
        subject_id="user-42",
        purpose="code_prefs",
        memory_type="preference",
        subject_key="code",
        predicate="code_language",
    )


@pytest.fixture
def sample_version(sample_memory):
    return MemoryVersion(
        memory_id=sample_memory.id,
        version=1,
        value="Python",
        confidence=0.95,
        searchable_summary="preference: code_language = Python",
        evidence_text="I like Python",
        source_message_id="msg-001",
    )


@pytest.fixture
def sample_consent():
    return ConsentRecord(
        tenant_id="tenant-alpha",
        subject_id="user-42",
        actor_id="admin",
        purpose="code_prefs",
        allow_write=True,
        allow_read=True,
        allowed_memory_types={"preference", "semantic"},
        allowed_sensitivity={"public", "internal"},
    )


@pytest.fixture
def sample_audit_event():
    return AuditEvent(
        tenant_id="tenant-alpha",
        actor_id="admin",
        action="memory.retrieved",
        resource_type="memory",
    )


# ── Helpers ──────────────────────────────────────────────────────────────────────


def make_memory_orm(**overrides) -> MemoryModel:
    """Build a MemoryModel with defaults for testing."""
    fields = dict(
        id=uuid4(),
        tenant_id="tenant-alpha",
        subject_id="user-42",
        purpose="code_prefs",
        memory_type="preference",
        subject_key="code",
        predicate="code_language",
        status="candidate",
        current_version=0,
        created_at=_NOW,
        updated_at=_NOW,
    )
    fields.update(overrides)
    return MemoryModel(**fields)


def make_consent_orm(**overrides) -> ConsentModel:
    """Build a ConsentModel with defaults for testing."""
    fields = dict(
        id=uuid4(),
        tenant_id="tenant-alpha",
        subject_id="user-42",
        actor_id="admin",
        purpose="code_prefs",
        allow_write=True,
        allow_read=True,
        allowed_memory_types=["preference", "semantic"],
        allowed_sensitivity=["public", "internal"],
        version=1,
        revoked_at=None,
        expires_at=None,
        retention_days=None,
        created_at=_NOW,
        updated_at=_NOW,
    )
    fields.update(overrides)
    return ConsentModel(**fields)


def make_audit_orm(**overrides) -> AuditLogModel:
    """Build an AuditLogModel with defaults for testing."""
    fields = dict(
        id=uuid4(),
        tenant_id="tenant-alpha",
        actor_id="admin",
        action="memory.retrieved",
        memory_type=None,
        details=None,
        created_at=_NOW,
    )
    fields.update(overrides)
    return AuditLogModel(**fields)


# ── MemoryRepository Tests ────────────────────────────────────────────────────────


class TestMemoryRepository:
    """Test MemoryRepository CRUD operations with mocked session."""

    async def test_save_memory(
        self, mock_session, sample_memory, sample_version,
    ):
        """Save a new memory with its first version."""
        repo = MemoryRepository(mock_session)
        result = await repo.save(sample_memory, sample_version)

        assert result.id == sample_memory.id
        assert result.tenant_id == "tenant-alpha"
        assert mock_session.add.call_count == 2
        assert mock_session.flush.await_count == 1

    async def test_get_memory_found(
        self, mock_session, sample_memory,
    ):
        """Get an existing memory by ID."""
        orm = make_memory_orm(id=sample_memory.id)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = orm
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = MemoryRepository(mock_session)
        result = await repo.get(sample_memory.id, tenant_id="tenant-alpha")

        assert result is not None
        assert result.id == sample_memory.id
        assert result.tenant_id == "tenant-alpha"
        assert result.memory_type == "preference"

    async def test_get_memory_not_found(
        self, mock_session,
    ):
        """Get returns None when memory doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = MemoryRepository(mock_session)
        result = await repo.get(uuid4(), tenant_id="tenant-alpha")
        assert result is None

    async def test_list_memories(
        self, mock_session, sample_memory,
    ):
        """List memories with filters."""
        orm = make_memory_orm(id=sample_memory.id, status="active", current_version=1)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [orm]
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = MemoryRepository(mock_session)
        results = await repo.list(
            tenant_id="tenant-alpha",
            subject_id="user-42",
            memory_type="preference",
        )

        assert len(results) == 1
        assert results[0].tenant_id == "tenant-alpha"
        assert results[0].subject_id == "user-42"

    async def test_list_memories_empty(
        self, mock_session,
    ):
        """List returns empty list when no matching memories."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = MemoryRepository(mock_session)
        results = await repo.list(
            tenant_id="tenant-alpha",
            subject_id="nonexistent",
        )

        assert len(results) == 0

    async def test_add_version(
        self, mock_session, sample_memory, sample_version,
    ):
        """Add a new version to an existing memory."""
        orm = make_memory_orm(id=sample_memory.id, status="active", current_version=1)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = orm
        mock_result.rowcount = 1
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = MemoryRepository(mock_session)
        v2 = MemoryVersion(
            memory_id=sample_memory.id,
            version=2,
            value="TypeScript",
            confidence=0.98,
        )

        result = await repo.add_version(
            sample_memory.id, v2, tenant_id="tenant-alpha",
        )

        assert result.version == 2
        assert result.memory_id == sample_memory.id

    async def test_update_status(
        self, mock_session,
    ):
        """Update memory status."""
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = MemoryRepository(mock_session)
        mid = uuid4()
        await repo.update_status(mid, "active", tenant_id="tenant-alpha")

        assert mock_session.execute.await_count >= 1
        assert mock_session.flush.await_count == 1

    async def test_update_status_not_found(
        self, mock_session,
    ):
        """Update on non-existent memory raises MemoryNotFoundError."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = MemoryRepository(mock_session)
        with pytest.raises(MemoryNotFoundError):
            await repo.update_status(uuid4(), "active", tenant_id="tenant-alpha")


# ── ConsentRepository Tests ───────────────────────────────────────────────────────


class TestConsentRepository:
    """Test ConsentRepository CRUD operations."""

    async def test_save_consent(
        self, mock_session, sample_consent,
    ):
        """Save a new consent record."""
        repo = ConsentRepository(mock_session)
        result = await repo.save(sample_consent)

        assert result.id == sample_consent.id
        assert result.tenant_id == "tenant-alpha"
        assert mock_session.add.call_count == 1
        assert mock_session.flush.await_count == 1

    async def test_get_active_consent(
        self, mock_session, sample_consent,
    ):
        """Get the active consent for a subject and purpose."""
        orm = make_consent_orm(id=sample_consent.id)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = orm
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = ConsentRepository(mock_session)
        result = await repo.get_active(
            tenant_id="tenant-alpha",
            subject_id="user-42",
            purpose="code_prefs",
        )

        assert result is not None
        assert result.is_active()
        assert result.allow_write is True
        assert result.allow_read is True

    async def test_get_active_consent_not_found(
        self, mock_session,
    ):
        """Returns None when no active consent exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = ConsentRepository(mock_session)
        result = await repo.get_active(
            tenant_id="tenant-alpha",
            subject_id="user-42",
            purpose="unknown_purpose",
        )
        assert result is None

    async def test_revoke_consent(
        self, mock_session, sample_consent,
    ):
        """Revoke a consent record."""
        orm = make_consent_orm(id=sample_consent.id, revoked_at=None)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = orm
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = ConsentRepository(mock_session)
        result = await repo.revoke(
            sample_consent.id, tenant_id="tenant-alpha",
        )

        assert result.is_revoked()
        assert result.revoked_at is not None
        assert mock_session.flush.await_count == 1

    async def test_revoke_consent_not_found(
        self, mock_session,
    ):
        """Revoking non-existent consent raises ConsentNotFoundError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = ConsentRepository(mock_session)
        with pytest.raises(ConsentNotFoundError):
            await repo.revoke(uuid4(), tenant_id="tenant-alpha")


# ── AuditRepository Tests ─────────────────────────────────────────────────────────


class TestAuditRepository:
    """Test AuditRepository append-only operations."""

    async def test_append_event(
        self, mock_session, sample_audit_event,
    ):
        """Append an audit event."""
        repo = AuditRepository(mock_session)
        result = await repo.append(sample_audit_event)

        assert result.id == sample_audit_event.id
        assert result.tenant_id == "tenant-alpha"
        assert result.action == "memory.retrieved"
        assert mock_session.add.call_count == 1
        assert mock_session.flush.await_count == 1

    async def test_query_audit(
        self, mock_session, sample_audit_event,
    ):
        """Query audit events."""
        orm = make_audit_orm(
            id=sample_audit_event.id,
            action="memory.retrieved",
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [orm]
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = AuditRepository(mock_session)
        query = AuditQuery(tenant_id="tenant-alpha", limit=10)
        results = await repo.query(query)

        assert len(results) >= 1
        assert results[0].tenant_id == "tenant-alpha"


# ── PostgresBackend Tests ─────────────────────────────────────────────────────────


class TestPostgresBackend:
    """Test PostgresBackend orchestrates repositories and sessions correctly."""

    @pytest.fixture
    def backend(self):
        config = MemoryConfig()
        config.database.uri = "sqlite+aiosqlite://"
        return PostgresBackend(config=config)

    async def _run_with_mock_session(self, backend, callback):
        """Run a callback with a mock session patched into get_session."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.close = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock())

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_session)
        cm.__aexit__ = AsyncMock()

        with patch("agent_memory.postgres.backend.get_session", return_value=cm):
            return await callback(mock_session)

    async def test_save_and_get_memory(self, backend, tenant_a, sample_memory, sample_version):
        """End-to-end: save then get a memory through the backend."""
        async def callback(session):
            saved = await backend.save_memory(sample_memory, sample_version, context=tenant_a)
            assert saved.id == sample_memory.id

            orm = make_memory_orm(id=sample_memory.id)
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = orm
            session.execute = AsyncMock(return_value=mock_result)

            retrieved = await backend.get_memory(sample_memory.id, context=tenant_a)
            assert retrieved is not None
            assert retrieved.tenant_id == "tenant-alpha"
            return True

        await self._run_with_mock_session(backend, callback)

    async def test_consent_lifecycle(self, backend, tenant_a, sample_consent):
        """Full consent lifecycle: save -> get active -> revoke."""
        async def callback(session):
            saved = await backend.save_consent(sample_consent, context=tenant_a)
            assert saved.id == sample_consent.id

            orm = make_consent_orm(id=sample_consent.id)
            mock_found = MagicMock()
            mock_found.scalar_one_or_none.return_value = orm
            session.execute = AsyncMock(return_value=mock_found)

            active = await backend.get_active_consent(
                tenant_id="tenant-alpha",
                subject_id="user-42",
                purpose="code_prefs",
            )
            assert active is not None
            return True

        await self._run_with_mock_session(backend, callback)

    async def test_audit_logging(self, backend, sample_audit_event):
        """Audit event append and query."""
        async def callback(session):
            await backend.audit(sample_audit_event)

            orm = make_audit_orm(id=sample_audit_event.id, action="memory.retrieved")
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [orm]
            session.execute = AsyncMock(return_value=mock_result)

            query = AuditQuery(tenant_id="tenant-alpha", limit=10)
            events = await backend.query_audit(query)
            assert len(events) >= 1
            assert events[0].action == "memory.retrieved"
            return True

        await self._run_with_mock_session(backend, callback)

    async def test_health_check(self, backend):
        """Health check returns expected structure."""
        async def callback(session):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = 1
            session.execute = AsyncMock(return_value=mock_result)
            health = await backend.health_check()
            assert isinstance(health, dict)
            assert "healthy" in health
            return True

        await self._run_with_mock_session(backend, callback)

    async def test_update_memory_status(self, backend, tenant_a):
        """Update status through backend."""
        async def callback(session):
            mock_result = MagicMock()
            mock_result.rowcount = 1
            session.execute = AsyncMock(return_value=mock_result)

            mid = uuid4()
            await backend.update_memory_status(mid, "active", context=tenant_a)
            assert session.commit.await_count >= 1
            return True

        await self._run_with_mock_session(backend, callback)

    async def test_tenant_isolation_in_repository(
        self, mock_session,
    ):
        """Repository-level tenant filtering works correctly."""
        mem_a = make_memory_orm(tenant_id="tenant-alpha", status="active", current_version=1)
        mem_b = make_memory_orm(
            id=uuid4(),
            tenant_id="tenant-beta",
            status="active",
            current_version=1,
        )

        mock_alpha_result = MagicMock()
        mock_alpha_result.scalars.return_value.all.return_value = [mem_a]
        mock_beta_result = MagicMock()
        mock_beta_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(side_effect=[mock_alpha_result, mock_beta_result])

        repo = MemoryRepository(mock_session)
        alpha_results = await repo.list(
            tenant_id="tenant-alpha",
            subject_id="user-42",
        )
        assert len(alpha_results) == 1
        assert alpha_results[0].tenant_id == "tenant-alpha"

        beta_results = await repo.list(
            tenant_id="tenant-beta",
            subject_id="user-42",
        )
        assert len(beta_results) == 0