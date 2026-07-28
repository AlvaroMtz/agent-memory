"""Async SQLAlchemy session factory for agent-memory PostgreSQL backend.

Provides:
- create_async_engine from config
- async_sessionmaker bound to that engine
- get_session() async context manager
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from agent_memory.config import MemoryConfig, load_config
from agent_memory.constants import TENANT_CONTEXT_PARAM


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def create_engine(
    config: MemoryConfig | None = None,
    **kwargs: Any,
) -> AsyncEngine:
    """Create the async SQLAlchemy engine from configuration.

    Args:
        config: MemoryConfig instance. If None, loads from defaults.
        **kwargs: Additional keyword arguments passed to create_async_engine.

    Returns:
        AsyncEngine instance.
    """
    global _engine

    if config is None:
        config = load_config()

    engine = create_async_engine(
        config.database.uri,
        pool_size=config.database.pool_size,
        max_overflow=config.database.max_overflow,
        pool_pre_ping=True,
        echo=config.environment == "development",
        **kwargs,
    )

    _engine = engine
    return engine


def create_sessionmaker(
    engine: AsyncEngine | None = None,
) -> async_sessionmaker[AsyncSession]:
    """Create the async sessionmaker.

    Args:
        engine: AsyncEngine instance. If None, uses or creates the global engine.

    Returns:
        async_sessionmaker bound to the engine.
    """
    global _sessionmaker

    if engine is None:
        if _engine is None:
            engine = create_engine()
        else:
            engine = _engine

    sessionmaker = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    _sessionmaker = sessionmaker
    return sessionmaker


@contextlib.asynccontextmanager
async def get_session(
    tenant_id: str | None = None,
    actor_id: str | None = None,
) -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session.

    Optionally sets RLS context parameters via SET LOCAL.
    The session is automatically closed and any transaction is rolled back
    on exit if not explicitly committed.

    Args:
        tenant_id: If provided, set the tenant RLS context parameter.
        actor_id: If provided, set the actor RLS context parameter.

    Yields:
        AsyncSession instance.
    """
    global _sessionmaker

    if _sessionmaker is None:
        create_sessionmaker()

    assert _sessionmaker is not None

    async with _sessionmaker() as session:
        # Set RLS context parameters before any operation
        if tenant_id:
            await session.execute(
                text("SELECT set_config(:param, :val, true)"),
                {"param": TENANT_CONTEXT_PARAM, "val": tenant_id},
            )
        if actor_id:
            await session.execute(
                text("SELECT set_config(:param, :val, true)"),
                {"param": "agent_memory.actor_id", "val": actor_id},
            )

        try:
            yield session
        finally:
            await session.close()


async def close_engine() -> None:
    """Dispose of the global async engine."""
    global _engine, _sessionmaker

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
