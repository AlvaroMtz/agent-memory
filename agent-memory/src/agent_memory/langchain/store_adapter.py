"""Store adapter — adapts MemoryBackend to LangChain's BaseStore interface.

Provides AgentMemoryStoreAdapter that implements LangChain's BaseStore
protocol, mapping string keys to MemoryRecord/RetrievedMemory objects
with tenant isolation via key prefixes.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterable
from typing import Any

from agent_memory.constants import DEFAULT_TOP_K
from agent_memory.domain.memory import MemoryRecord
from agent_memory.ports.backend import MemoryBackend

logger = logging.getLogger(__name__)


class AgentMemoryStoreAdapter:
    """Adapts agent-memory's MemoryBackend to LangChain's BaseStore.

    Key format: ``{tenant_id}:{subject_id}:{namespace}:{key}``

    This ensures tenant isolation and allows sharing the same backend
    with multiple agents in the same tenant.

    Example::

        adapter = AgentMemoryStoreAdapter(backend=backend, namespace="agent-1")

        # Write a memory
        await adapter.mset([(("preference", "language"), "en")])

        # Read memories back
        items = await adapter.mget([("preference", "language")])
    """

    def __init__(
        self,
        backend: MemoryBackend,
        *,
        namespace: str = "",
        tenant_id: str = "default",
        subject_id: str = "default",
    ) -> None:
        """Initialize the store adapter.

        Args:
            backend: The MemoryBackend instance to use.
            namespace: A namespace prefix for keys (e.g. "agent-1").
            tenant_id: The tenant ID to use for all operations.
            subject_id: The subject ID to use for all operations.
        """
        self.backend = backend
        self.namespace = namespace
        self.tenant_id = tenant_id
        self.subject_id = subject_id

    # ── Required BaseStore methods ──────────────────────────────────────────

    async def mget(self, keys: Iterable[str]) -> list[Any | None]:
        """Get multiple values by key.

        Args:
            keys: Iterable of string keys (without tenant prefix).

        Returns:
            List of values (or None if key not found).
        """
        result: list[Any | None] = []
        for key in keys:
            value = await self._get(key)
            result.append(value)
        return result

    async def mset(self, pairs: Iterable[tuple[str, Any]]) -> None:
        """Set multiple key-value pairs.

        Values are JSON-serialized before storage.

        Args:
            pairs: Iterable of (key, value) tuples.
        """
        for key, value in pairs:
            await self._set(key, value)

    async def mdelete(self, keys: Iterable[str]) -> None:
        """Delete multiple keys.

        Args:
            keys: Iterable of string keys to delete.
        """
        for key in keys:
            await self._delete(key)

    async def yield_keys(
        self,
        *,
        next_key: str | None = None,
        prefix: str | None = None,
    ) -> AsyncIterator[str]:
        """Yield keys matching an optional prefix.

        Args:
            next_key: Cursor for pagination (key after which to continue).
            prefix: Optional prefix filter (full prefixed key).

        Yields:
            Keys matching the criteria.
        """
        # Build the full prefix from the tenant and subject
        base_prefix = self._build_prefix(self.tenant_id, self.subject_id)

        if prefix:
            full_prefix = prefix
        else:
            full_prefix = base_prefix

        if self.namespace:
            full_prefix = f"{base_prefix}:{self.namespace}"

        # Yield keys using the backend's list_memories
        async for key in self._keys_with_prefix(full_prefix):
            yield key

    # ── Internal methods ──────────────────────────────────────────────────

    async def _get(self, key: str) -> Any | None:
        """Get a single value by key."""
        full_key = self._build_key(key)

        try:
            # Try to get from backend as a memory record
            memory_id = self._parse_key(full_key)
            if memory_id is not None:
                record = await self.backend.get_memory(
                    memory_id, context=_make_tenant_ctx(self.tenant_id)
                )
                if record and record.status != "deleted":
                    return self._serialize(record)
        except Exception:
            logger.exception("Failed to get key %s", full_key)

        # Fall back to storing/retrieving via backend's list
        try:
            memories = await self.backend.list_memories(
                tenant_id=self.tenant_id,
                subject_id=self.subject_id,
                limit=DEFAULT_TOP_K * 10,
            )
            for m in memories:
                if m.status == "deleted":
                    continue
                # Match by subject_key (short form) or predicate (full key with namespace)
                if m.subject_key == self._extract_subject_key(full_key) or m.predicate == full_key:
                    return self._serialize(m)
        except Exception:
            logger.exception("Failed to list memories for key %s", full_key)

        return None

    async def _set(self, key: str, value: Any) -> None:
        """Set a single key-value pair."""
        full_key = self._build_key(key)

        try:
            from uuid import uuid4

            from agent_memory.context import TenantContext
            from agent_memory.domain.memory import MemoryRecord, MemoryVersion

            record = MemoryRecord(
                id=uuid4(),
                tenant_id=self.tenant_id,
                subject_id=self.subject_id,
                purpose="langchain-store",
                memory_type="semantic",
                subject_key=full_key,
                predicate=full_key,
            )

            version = MemoryVersion(
                memory_id=record.id,
                version=1,
                value=value,
                searchable_summary=str(value),
                confidence=1.0,
                sensitivity="internal",
                source_type="trusted_tool",
            )

            await self.backend.save_memory(
                record, version, context=TenantContext(tenant_id=self.tenant_id)
            )
        except Exception:
            logger.exception("Failed to set key %s", full_key)

    async def _delete(self, key: str) -> None:
        """Delete a single key."""
        full_key = self._build_key(key)

        try:
            # List memories and find the one matching this key, then update status
            memories = await self.backend.list_memories(
                tenant_id=self.tenant_id,
                subject_id=self.subject_id,
                limit=DEFAULT_TOP_K * 10,
            )
            for m in memories:
                if m.predicate == full_key or m.subject_key == self._extract_subject_key(full_key):
                    await self.backend.update_memory_status(
                        m.id,
                        "deleted",
                        context=_make_tenant_ctx(self.tenant_id),
                    )
        except Exception:
            logger.exception("Failed to delete key %s", full_key)

    async def _keys_with_prefix(self, prefix: str) -> AsyncIterator[str]:
        """Yield keys matching a prefix."""
        try:
            memories = await self.backend.list_memories(
                tenant_id=self.tenant_id,
                subject_id=self.subject_id,
                limit=DEFAULT_TOP_K * 100,
            )
            for m in memories:
                full_key = f"{prefix}:{m.subject_key}"
                if full_key.startswith(prefix):
                    yield full_key
        except Exception:
            logger.exception("Failed to yield keys with prefix %s", prefix)

    # ── Key management ──────────────────────────────────────────────────

    def _build_key(self, key: str) -> str:
        """Build a full key with namespace."""
        if self.namespace:
            return f"{self.tenant_id}:{self.subject_id}:{self.namespace}:{key}"
        return f"{self.tenant_id}:{self.subject_id}:{key}"

    def _build_prefix(self, tenant_id: str, subject_id: str) -> str:
        """Build a key prefix for filtering."""
        return f"{tenant_id}:{subject_id}"

    def _parse_key(self, key: str) -> str | None:
        """Extract the memory_id from a key (if stored as UUID)."""
        parts = key.split(":")
        if len(parts) >= 3:
            return parts[-1]  # Last part is the memory ID or subject_key
        return None

    def _extract_subject_key(self, full_key: str) -> str:
        """Extract the subject_key from a full key."""
        parts = full_key.split(":")
        return parts[-1] if parts else full_key

    def _serialize(self, record: MemoryRecord) -> dict[str, Any]:
        """Serialize a MemoryRecord to a dict."""

        return {
            "id": str(record.id),
            "tenant_id": record.tenant_id,
            "subject_id": record.subject_id,
            "memory_type": record.memory_type,
            "subject_key": record.subject_key,
            "predicate": record.predicate,
            "status": record.status,
            "current_version": record.current_version,
        }


def _make_tenant_ctx(tenant_id: str) -> Any:
    """Create a TenantContext (lazily imported to avoid circular imports)."""
    from agent_memory.context import TenantContext

    return TenantContext(tenant_id=tenant_id, actor_id=None)
