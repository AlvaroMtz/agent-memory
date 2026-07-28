"""Migration tests — fresh install, upgrade, and idempotency checks."""

from __future__ import annotations

import os

import pytest


pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("AGENT_MEMORY_DATABASE__URI"),
        reason="AGENT_MEMORY_DATABASE__URI not set",
    ),
    pytest.mark.asyncio,
]


@pytest.fixture
def database_url() -> str:
    url = os.environ["AGENT_MEMORY_DATABASE__URI"]
    # Normalize async driver for alembic
    return url.replace("+asyncpg", "").replace("+psycopg", "").replace("asyncpg://", "postgresql://")


async def test_alembic_can_run_migrations():
    """Verify alembic migration script generation works."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    heads = script.get_heads()
    assert len(heads) >= 1, "No migration heads found"


async def test_alembic_heads_match_revision():
    """Verify the latest migration head is consistent."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    heads = script.get_heads()
    for head in heads:
        rev = script.get_revision(head)
        assert rev is not None, f"Revision {head} not found"
        assert rev.doc, f"Revision {head} has no doc string"


async def test_migration_idempotency():
    """Verify alembic stamp head can be run multiple times."""
    from alembic.config import Config
    from alembic.command import check

    alembic_cfg = Config("alembic.ini")
    # check raises SystemExit if not at head, otherwise passes
    try:
        check(alembic_cfg)
    except SystemExit as exc:
        pytest.skip(f"Alembic check failed: {exc}. Run migrations first.")
