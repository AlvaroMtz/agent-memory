"""PostgreSQL Row-Level Security (RLS) support for agent-memory.

Provides:
- enable_rqls(): SQL function to enable RLS on all agent-memory tables
- apply_rls_policies(): SQL to create per-table RLS policies
- set_session_tenant(): set tenant context using SET LOCAL
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from agent_memory.constants import TENANT_CONTEXT_PARAM

RLS_TABLES = ["memories", "memory_versions", "consent", "audit_log"]


def enable_rqls_sql() -> str:
    """Return SQL that enables RLS on each agent-memory table.

    Returns:
        A SQL string to execute in a migration or setup step.
    """
    statements = []
    for table in RLS_TABLES:
        statements.append(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        statements.append(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
    return "\n".join(statements)


def apply_rls_policies_sql() -> str:
    """Return SQL that creates per-table RLS policies.

    Each policy uses the current_setting('agent_memory.tenant_id') function
    to compare against the tenant_id column.

    Returns:
        A SQL string to execute in a migration or setup step.
    """
    statements = []

    # ── memories ──────────────────────────────────────────────────────────────
    statements.append(
        f"""
        CREATE POLICY tenant_isolation ON memories
        FOR ALL
        USING (tenant_id = current_setting('{TENANT_CONTEXT_PARAM}', true)::text)
        WITH CHECK (tenant_id = current_setting('{TENANT_CONTEXT_PARAM}', true)::text);
        """
    )

    # ── memory_versions (uses tenant_id via join to memories, but we add direct check) ──
    statements.append(
        f"""
        CREATE POLICY tenant_isolation ON memory_versions
        FOR ALL
        USING (
            memory_id IN (
                SELECT id FROM memories
                WHERE tenant_id = current_setting('{TENANT_CONTEXT_PARAM}', true)::text
            )
        )
        WITH CHECK (
            memory_id IN (
                SELECT id FROM memories
                WHERE tenant_id = current_setting('{TENANT_CONTEXT_PARAM}', true)::text
            )
        );
        """
    )

    # ── consent ───────────────────────────────────────────────────────────────
    statements.append(
        f"""
        CREATE POLICY tenant_isolation ON consent
        FOR ALL
        USING (tenant_id = current_setting('{TENANT_CONTEXT_PARAM}', true)::text)
        WITH CHECK (tenant_id = current_setting('{TENANT_CONTEXT_PARAM}', true)::text);
        """
    )

    # ── audit_log ─────────────────────────────────────────────────────────────
    statements.append(
        f"""
        CREATE POLICY tenant_isolation ON audit_log
        FOR ALL
        USING (tenant_id = current_setting('{TENANT_CONTEXT_PARAM}', true)::text)
        WITH CHECK (tenant_id = current_setting('{TENANT_CONTEXT_PARAM}', true)::text);
        """
    )

    return "\n".join(statements)


def drop_rls_policies_sql() -> str:
    """Return SQL that drops all RLS policies.

    Returns:
        A SQL string to execute for cleanup (e.g., in a downgrade).
    """
    statements = []
    for table in RLS_TABLES:
        statements.append(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
    return "\n".join(statements)


def disable_rqls_sql() -> str:
    """Return SQL that disables RLS on each table.

    Returns:
        A SQL string to execute for cleanup.
    """
    statements = []
    for table in RLS_TABLES:
        statements.append(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        statements.append(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
    return "\n".join(statements)


def set_session_tenant_sql(tenant_id: str) -> str:
    """Return SQL to set the tenant context parameter via SET LOCAL.

    Args:
        tenant_id: The tenant identifier to set.

    Returns:
        A SQL string to execute at the start of a session or transaction.
    """
    return f"SELECT set_config('{TENANT_CONTEXT_PARAM}', :tenant_id, true)"


def set_session_actor_sql(actor_id: str) -> str:
    """Return SQL to set the actor context parameter via SET LOCAL.

    Args:
        actor_id: The actor identifier to set.

    Returns:
        A SQL string to execute.
    """
    return "SELECT set_config('agent_memory.actor_id', :actor_id, true)"


# ── Async convenience functions ────────────────────────────────────────────────────


async def enable_rqls_on_connection(connection: AsyncConnection) -> None:
    """Enable RLS on all tables via the given connection.

    Args:
        connection: An active async database connection.
    """
    await connection.execute(text(enable_rqls_sql()))


async def apply_rls_policies(connection: AsyncConnection) -> None:
    """Create RLS policies on all tables via the given connection.

    Args:
        connection: An active async database connection.
    """
    await connection.execute(text(apply_rls_policies_sql()))


async def set_session_tenant(
    session: AsyncSession,
    tenant_id: str,
    actor_id: str | None = None,
) -> None:
    """Set the tenant (and optionally actor) context for the current session.

    Uses SET LOCAL so the context is scoped to the current transaction.

    Args:
        session: An active async database session.
        tenant_id: The tenant identifier.
        actor_id: Optional actor identifier.
    """
    await session.execute(
        text(set_session_tenant_sql(tenant_id)),
        {"tenant_id": tenant_id},
    )
    if actor_id:
        await session.execute(
            text(set_session_actor_sql(actor_id)),
            {"actor_id": actor_id},
        )


async def setup_rqls(connection: AsyncConnection) -> None:
    """Full RLS setup: enable RLS and create policies.

    Args:
        connection: An active async database connection.
    """
    await enable_rqls_on_connection(connection)
    await apply_rls_policies(connection)


async def teardown_rqls(connection: AsyncConnection) -> None:
    """Full RLS teardown: drop policies and disable RLS.

    Args:
        connection: An active async database connection.
    """
    await connection.execute(text(drop_rls_policies_sql()))
    await connection.execute(text(disable_rqls_sql()))