"""PostgreSQL backend adapter.

Keep imports lazy so pure RLS SQL helpers remain importable in minimal
environments that do not have pgvector installed.
"""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    if name in {"PostgresBackend", "PostgresBackendFactory"}:
        from agent_memory.postgres.backend import PostgresBackend, PostgresBackendFactory

        return {
            "PostgresBackend": PostgresBackend,
            "PostgresBackendFactory": PostgresBackendFactory,
        }[name]
    raise AttributeError(name)


__all__ = ["PostgresBackend", "PostgresBackendFactory"]
