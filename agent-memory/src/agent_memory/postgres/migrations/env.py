"""asynchronous Alembic environment configuration.

Uses async SQLAlchemy engine with Alembic's run_async() support.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from agent_memory.config import load_config
from agent_memory.postgres.models import Base

# Alembic Config object
config = context.config

# Set up Python logging from the alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData for autogenerate support
target_metadata = Base.metadata


# Exclude internal Alembic tables from autogenerate
def include_object(obj, name, type_, reflected, compare_to):
    """Exclude Alembic's own version table from autogenerate."""
    if type_ == "table" and name == "alembic_version":
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine.
    Calls to context.execute() here emit the given string to the
    script output.
    """
    cfg = load_config()
    url = cfg.database.uri

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        version_table="alembic_version",
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Run migrations with a synchronous connection wrapper."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        version_table="alembic_version",
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using an async engine created from configuration."""
    cfg = load_config()
    url = cfg.database.uri

    connectable = create_async_engine(url, pool_pre_ping=True)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using async engine."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
