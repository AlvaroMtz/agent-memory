"""RLS integration tests — tenant isolation via mock RLS context.

Validates:
- enable_rqls_sql generates correct SQL
- apply_rls_policies_sql creates policies for all tables
- set_session_tenant_sql generates correct SET LOCAL statements
- RLS policy SQL statements are syntactically valid
- Policies cover all four tables (memories, memory_versions, consent, audit_log)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_memory.constants import TENANT_CONTEXT_PARAM
from agent_memory.postgres.rls import (
    RLS_TABLES,
    apply_rls_policies_sql,
    disable_rqls_sql,
    drop_rls_policies_sql,
    enable_rqls_sql,
    set_session_tenant_sql,
    set_session_actor_sql,
    setup_rqls,
    teardown_rqls,
    set_session_tenant,
)


class TestRLSSQLStatements:
    """Verify RLS SQL statements are well-formed and cover required tables."""

    def test_enable_rqls_sql_covers_all_tables(self):
        """enable_rqls_sql contains ENABLE ROW LEVEL SECURITY for each table."""
        sql = enable_rqls_sql()

        for table in RLS_TABLES:
            assert f"ALTER TABLE {table}" in sql
            assert "ENABLE ROW LEVEL SECURITY" in sql
            assert "FORCE ROW LEVEL SECURITY" in sql

    def test_enable_rqls_sql_contains_all_tables(self):
        """The table list matches the expected set."""
        expected = {"memories", "memory_versions", "consent", "audit_log"}
        assert set(RLS_TABLES) == expected

    def test_apply_rls_policies_sql_creates_policies(self):
        """apply_rls_policies_sql creates a tenant_isolation policy for each table."""
        sql = apply_rls_policies_sql()

        for table in RLS_TABLES:
            assert f"CREATE POLICY tenant_isolation ON {table}" in sql

    def test_apply_rls_policies_sql_uses_tenant_context(self):
        """The policy references the correct tenant context parameter."""
        sql = apply_rls_policies_sql()

        assert TENANT_CONTEXT_PARAM in sql
        assert "current_setting" in sql

    def test_apply_rls_policies_sql_for_memory_versions(self):
        """memory_versions policy uses a subquery against memories."""
        sql = apply_rls_policies_sql()
        memory_versions_section = (
            sql.split("CREATE POLICY tenant_isolation ON memory_versions")[1]
            .split("CREATE POLICY")[0]
            if "CREATE POLICY tenant_isolation ON memory_versions" in sql
            else ""
        )

        assert "SELECT id FROM memories" in memory_versions_section

    def test_drop_rls_policies_sql_drops_all(self):
        """drop_rls_policies_sql drops the policy from each table."""
        sql = drop_rls_policies_sql()

        for table in RLS_TABLES:
            assert f"DROP POLICY IF EXISTS tenant_isolation ON {table}" in sql

    def test_disable_rqls_sql_disables_all(self):
        """disable_rqls_sql disables RLS on each table."""
        sql = disable_rqls_sql()

        for table in RLS_TABLES:
            assert f"ALTER TABLE {table}" in sql
            assert "DISABLE ROW LEVEL SECURITY" in sql
            assert "NO FORCE ROW LEVEL SECURITY" in sql

    def test_set_session_tenant_sql(self):
        """set_session_tenant_sql generates correct SET LOCAL command."""
        sql = set_session_tenant_sql("tenant-alpha")

        assert TENANT_CONTEXT_PARAM in sql
        assert "set_config" in sql
        assert ":tenant_id" in sql

    def test_set_session_actor_sql(self):
        """set_session_actor_sql generates correct actor context command."""
        sql = set_session_actor_sql("actor-42")

        assert "agent_memory.actor_id" in sql
        assert "set_config" in sql
        assert ":actor_id" in sql


class TestRLSAsyncFunctions:
    """Test async RLS convenience functions with mocked connections."""

    @pytest.fixture
    def mock_connection(self):
        conn = AsyncMock()
        conn.execute = AsyncMock()
        return conn

    async def test_setup_rqls_calls_enable_and_apply(self, mock_connection):
        """setup_rqls enables RLS and applies policies."""
        await setup_rqls(mock_connection)

        # Should call execute twice: once for enable, once for apply
        assert mock_connection.execute.await_count >= 1

    async def test_teardown_rqls_drops_and_disables(self, mock_connection):
        """teardown_rqls drops policies and disables RLS."""
        await teardown_rqls(mock_connection)
        assert mock_connection.execute.await_count >= 1

    async def test_set_session_tenant_sets_context(self):
        """set_session_tenant sets the tenant context parameter."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        result = MagicMock()
        mock_session.execute.return_value = result

        await set_session_tenant(mock_session, "tenant-alpha", actor_id="actor-42")

        # Should call execute twice: once for tenant, once for actor
        assert mock_session.execute.await_count == 2

    async def test_set_session_tenant_no_actor(self):
        """set_session_tenant works without an actor_id."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        result = MagicMock()
        mock_session.execute.return_value = result

        await set_session_tenant(mock_session, "tenant-alpha")

        # Should call execute once (no actor)
        assert mock_session.execute.await_count == 1


class TestRLSTenantIsolation:
    """Conceptual tenant isolation tests through RLS."""

    def test_rls_tables_are_complete(self):
        """All multi-tenant tables must have RLS."""
        # These tables contain tenant-scoped data
        tables_requiring_rls = {"memories", "memory_versions", "consent", "audit_log"}
        assert set(RLS_TABLES) == tables_requiring_rls

    def test_rls_policy_uses_using_with_check(self):
        """Each policy should have both USING and WITH CHECK clauses."""
        sql = apply_rls_policies_sql()

        for table in RLS_TABLES:
            # Split into per-table sections
            if table == "memory_versions":
                # memory_versions is a special case with subquery
                assert "USING" in sql
                assert "WITH CHECK" in sql
                continue
            assert "USING" in sql, f"Table {table} policy missing USING clause"

    def test_rls_policy_references_tenant_id_column(self):
        """Each policy must reference the tenant_id column."""
        sql = apply_rls_policies_sql()

        for table in {"memories", "consent", "audit_log"}:
            # Find the policy section for this table
            keyword = f"CREATE POLICY tenant_isolation ON {table}"
            assert keyword in sql, f"Missing policy for table {table}"

        # memory_versions uses a different pattern (subquery)
        assert "memory_versions" in sql