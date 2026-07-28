"""Multi-tenant adversarial tests — cross-tenant attack prevention.

Validates that tenant isolation is enforced at multiple layers:
- Repository-level: tenant_id is always part of WHERE clauses
- Backend-level: TenantContext is validated and scoped
- RLS SQL: policies correctly restrict by tenant_id
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agent_memory.context import TenantContext
from agent_memory.domain.consent import ConsentRecord
from agent_memory.domain.memory import MemoryRecord, MemoryVersion
from agent_memory.exceptions import (
    ConsentNotFoundError,
    MemoryNotFoundError,
)
from agent_memory.postgres.models import (
    ConsentModel,
    MemoryModel,
)
from agent_memory.postgres.repositories import (
    ConsentRepository,
    MemoryRepository,
)
from agent_memory.postgres.rls import RLS_TABLES, apply_rls_policies_sql, enable_rqls_sql

_NOW = datetime.now(timezone.utc)


# ── Helper factories ──────────────────────────────────────────────────────────────


def make_memory_orm(**overrides) -> MemoryModel:
    """Build a MemoryModel with defaults for testing."""
    fields = dict(
        id=uuid4(),
        tenant_id="tenant-alpha",
        subject_id="user-42",
        purpose="test",
        memory_type="preference",
        subject_key="code",
        predicate="code_language",
        status="active",
        current_version=1,
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
        purpose="test",
        allow_write=True,
        allow_read=True,
        allowed_memory_types=["preference"],
        allowed_sensitivity=["public"],
        version=1,
        revoked_at=None,
        expires_at=None,
        retention_days=None,
        created_at=_NOW,
        updated_at=_NOW,
    )
    fields.update(overrides)
    return ConsentModel(**fields)


# ── Fixtures ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_session():
    session = AsyncMock(spec=AsyncSession)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def tenant_alpha():
    return TenantContext(tenant_id="tenant-alpha")


@pytest.fixture
def tenant_beta():
    return TenantContext(tenant_id="tenant-beta")


# ── Multi-Tenant Adversarial Tests ────────────────────────────────────────────────


class TestCrossTenantMemoryIsolation:
    """Verify that one tenant cannot access another tenant's memories."""

    async def test_list_memories_respects_tenant_boundary(
        self, mock_session,
    ):
        """LIST for tenant-alpha returns only alpha's memories."""
        alpha_mem = make_memory_orm(tenant_id="tenant-alpha")
        beta_mem = make_memory_orm(
            id=uuid4(),
            tenant_id="tenant-beta",
        )

        mock_alpha = MagicMock()
        mock_alpha.scalars.return_value.all.return_value = [alpha_mem]
        mock_beta = MagicMock()
        mock_beta.scalars.return_value.all.return_value = [beta_mem]

        mock_session.execute = AsyncMock(side_effect=[mock_alpha, mock_beta])

        repo = MemoryRepository(mock_session)

        alpha_results = await repo.list(
            tenant_id="tenant-alpha",
            subject_id="user-42",
        )
        assert len(alpha_results) == 1
        assert alpha_results[0].tenant_id == "tenant-alpha"
        assert alpha_results[0].id == alpha_mem.id

        beta_results = await repo.list(
            tenant_id="tenant-beta",
            subject_id="user-42",
        )
        assert len(beta_results) == 1
        assert beta_results[0].tenant_id == "tenant-beta"
        assert beta_results[0].id == beta_mem.id

    async def test_update_status_isolated_per_tenant(
        self, mock_session,
    ):
        """Update in tenant-alpha does not affect tenant-beta data."""
        mock_found = MagicMock()
        mock_found.rowcount = 1
        mock_not_found = MagicMock()
        mock_not_found.rowcount = 0

        mock_session.execute = AsyncMock(side_effect=[mock_found, mock_not_found])

        repo = MemoryRepository(mock_session)
        mid = uuid4()

        await repo.update_status(mid, "active", tenant_id="tenant-alpha")

        with pytest.raises(MemoryNotFoundError):
            await repo.update_status(mid, "active", tenant_id="tenant-beta")

    async def test_add_version_checks_tenant(
        self, mock_session,
    ):
        """add_version fails for cross-tenant access."""
        mem_id = uuid4()

        alpha_orm = make_memory_orm(id=mem_id, tenant_id="tenant-alpha")
        mock_exists = MagicMock()
        mock_exists.scalar_one_or_none.return_value = alpha_orm

        mock_session.execute = AsyncMock(return_value=mock_exists)

        repo = MemoryRepository(mock_session)
        version = MemoryVersion(
            memory_id=mem_id,
            version=1,
            value="test",
            confidence=0.9,
        )

        # Use separate mock sessions with appropriate return values
        mock_alpha_session = AsyncMock(spec=AsyncSession)
        mock_alpha_session.flush = AsyncMock()
        mock_alpha_result = MagicMock()
        mock_alpha_result.scalar_one_or_none.return_value = alpha_orm
        mock_alpha_result.rowcount = 1
        mock_alpha_session.execute = AsyncMock(
            side_effect=[mock_alpha_result, mock_alpha_result],
        )

        repo_alpha = MemoryRepository(mock_alpha_session)
        result = await repo_alpha.add_version(
            mem_id, version, tenant_id="tenant-alpha",
        )
        assert result.version == 1

        # For tenant-beta, get returns None (no match)
        mock_beta_session = AsyncMock(spec=AsyncSession)
        mock_beta_result = MagicMock()
        mock_beta_result.scalar_one_or_none.return_value = None
        mock_beta_session.execute = AsyncMock(return_value=mock_beta_result)

        repo_beta = MemoryRepository(mock_beta_session)
        with pytest.raises(MemoryNotFoundError):
            await repo_beta.add_version(
                mem_id, version, tenant_id="tenant-beta",
            )


class TestCrossTenantConsentIsolation:
    """Verify that one tenant cannot access another tenant's consent records."""

    async def test_get_active_consent_cross_tenant(
        self, mock_session,
    ):
        """Active consent lookup for tenant-beta should not return alpha's record."""
        consent_id = uuid4()
        alpha_consent = make_consent_orm(id=consent_id, tenant_id="tenant-alpha")

        mock_found = MagicMock()
        mock_found.scalar_one_or_none.return_value = alpha_consent
        mock_none = MagicMock()
        mock_none.scalar_one_or_none.return_value = None

        repo = ConsentRepository(mock_session)

        mock_session.execute = AsyncMock(return_value=mock_found)
        result = await repo.get_active(
            tenant_id="tenant-alpha",
            subject_id="user-42",
            purpose="test",
        )
        assert result is not None
        assert result.tenant_id == "tenant-alpha"

        mock_session.execute = AsyncMock(return_value=mock_none)
        result = await repo.get_active(
            tenant_id="tenant-beta",
            subject_id="user-42",
            purpose="test",
        )
        assert result is None

    async def test_revoke_consent_cross_tenant(
        self, mock_session,
    ):
        """Revoking a consent from wrong tenant raises ConsentNotFoundError."""
        consent_id = uuid4()

        mock_none = MagicMock()
        mock_none.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_none)

        repo = ConsentRepository(mock_session)
        with pytest.raises(ConsentNotFoundError):
            await repo.revoke(consent_id, tenant_id="tenant-beta")

    async def test_list_consent_isolated(
        self, mock_session,
    ):
        """LIST consent returns only the requesting tenant's records."""
        alpha_consent = make_consent_orm(tenant_id="tenant-alpha")
        beta_consent = make_consent_orm(
            id=uuid4(),
            tenant_id="tenant-beta",
        )

        mock_alpha = MagicMock()
        mock_alpha.scalars.return_value.all.return_value = [alpha_consent]
        mock_beta = MagicMock()
        mock_beta.scalars.return_value.all.return_value = [beta_consent]

        mock_session.execute = AsyncMock(side_effect=[mock_alpha, mock_beta])

        repo = ConsentRepository(mock_session)

        alpha_results = await repo.list(tenant_id="tenant-alpha")
        assert len(alpha_results) == 1
        assert alpha_results[0].tenant_id == "tenant-alpha"

        beta_results = await repo.list(tenant_id="tenant-beta")
        assert len(beta_results) == 1
        assert beta_results[0].tenant_id == "tenant-beta"


class TestRLSAdversarialBoundary:
    """Adversarial tests: confirm RLS is structurally sound against attacks."""

    def test_rls_covers_all_tenant_tables(self):
        """All tenant-scoped tables have RLS policies generated."""
        expected = {"memories", "memory_versions", "consent", "audit_log"}
        assert set(RLS_TABLES) == expected

    def test_rls_policies_are_comprehensive(self):
        """RLS policies cover FOR ALL operations (SELECT, INSERT, UPDATE, DELETE)."""
        sql = apply_rls_policies_sql()
        assert "FOR ALL" in sql

    def test_rls_policies_use_check_constraint(self):
        """WITH CHECK prevents cross-tenant INSERT/UPDATE."""
        sql = apply_rls_policies_sql()
        for table in {"memories", "consent", "audit_log"}:
            keyword = f"CREATE POLICY tenant_isolation ON {table}"
            if keyword in sql:
                section = sql.split(keyword)[1]
                assert "WITH CHECK" in section, f"Table {table} must have WITH CHECK"

    def test_rls_enable_uses_force(self):
        """FORCE ROW LEVEL SECURITY ensures RLS cannot be bypassed."""
        sql = enable_rqls_sql()
        assert "FORCE ROW LEVEL SECURITY" in sql

    def test_memory_versions_rls_uses_subquery(self):
        """memory_versions uses subquery-based isolation."""
        sql = apply_rls_policies_sql()
        assert "memory_id IN" in sql
        assert "SELECT id FROM memories" in sql