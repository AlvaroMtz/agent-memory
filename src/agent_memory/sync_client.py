"""Synchronous MemoryClient wrapper using asyncio.run().

Use this class from synchronous application code.  All methods block
on the underlying async client via ``asyncio.run()``, so callers must
not be inside an existing event loop.

Example::

    with SyncMemoryClient(backend, extractor, embedder, consent) as client:
        result = client.remember(context=ctx, messages=[...])
        results = client.retrieve("coffee", context=ctx)
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from agent_memory.client import MemoryClient
from agent_memory.context import MemoryContext
from agent_memory.domain.consent import ConsentGrant, ConsentRecord
from agent_memory.domain.forget import ForgetResult
from agent_memory.domain.memory import MemoryRecord
from agent_memory.domain.remember import RememberResult
from agent_memory.domain.retrieval import RetrievalResult
from agent_memory.ports.backend import MemoryBackend
from agent_memory.ports.consent import ConsentProvider
from agent_memory.ports.embedder import EmbeddingProvider
from agent_memory.ports.encryption import EncryptionProvider
from agent_memory.ports.extractor import MemoryExtractor


class SyncMemoryClient:
    """Synchronous facade over the async ``MemoryClient``.

    Wraps every call in ``asyncio.run()`` so it can be used from
    regular (non-async) code without blocking on an event loop.
    """

    def __init__(
        self,
        backend: MemoryBackend,
        extractor: MemoryExtractor | None = None,
        embedder: EmbeddingProvider | None = None,
        consent: ConsentProvider | None = None,
        encryption: EncryptionProvider | None = None,
    ) -> None:
        self._client = MemoryClient(backend, extractor, embedder, consent, encryption)

    def __enter__(self) -> SyncMemoryClient:
        asyncio.run(self._client.__aenter__())
        return self

    def __exit__(self, *exc: Any) -> None:
        asyncio.run(self._client.__aexit__(*exc))

    # ── remember ───────────────────────────────────────────────────────────────

    def remember(
        self,
        *,
        context: MemoryContext,
        messages: list[dict[str, Any]],
    ) -> RememberResult:
        """Extract memories from *messages* and persist them."""
        return asyncio.run(self._client.remember(context=context, messages=messages))

    # ── retrieve ───────────────────────────────────────────────────────────────

    def retrieve(
        self,
        *,
        context: MemoryContext,
        query: str,
        limit: int | None = None,
    ) -> RetrievalResult:
        """Run the full retrieval pipeline.

        **Signature**: ``retrieve(*, context, query, limit=None)``
        """
        return asyncio.run(
            self._client.retrieve(
                context=context, query=query, limit=limit
            )
        )

    # ── list_memories ──────────────────────────────────────────────────────────

    def list_memories(
        self,
        context: MemoryContext,
        *,
        memory_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        """List memories for a subject."""
        return asyncio.run(
            self._client.list_memories(
                context=context,
                memory_type=memory_type,
                status=status,
                limit=limit,
                offset=offset,
            )
        )

    # ── forget ─────────────────────────────────────────────────────────────────

    def forget(
        self,
        *,
        context: MemoryContext,
        memory_id: UUID,
    ) -> ForgetResult:
        """Soft-delete a memory by ID.

        **Signature**: ``forget(*, context, memory_id)``
        """
        return asyncio.run(self._client.forget(context=context, memory_id=memory_id))

    # ── consent ────────────────────────────────────────────────────────────────

    def grant_consent(
        self,
        context: MemoryContext,
        grant: ConsentGrant | None = None,
        *,
        memory_types: list[str] | None = None,
        sensitivity: str = "public",
        allow_read: bool = True,
        allow_write: bool = False,
    ) -> ConsentRecord:
        """Grant consent using the context's tenant_id and purpose."""
        return asyncio.run(
            self._client.grant_consent(
                context,
                grant=grant,
                memory_types=memory_types,
                sensitivity=sensitivity,
                allow_read=allow_read,
                allow_write=allow_write,
            )
        )

    def revoke_consent(
        self,
        subject_id: str | None = None,
        context: MemoryContext | None = None,
        *,
        consent_id: UUID | None = None,
    ) -> ConsentRecord:
        """Revoke consent using the context's tenant_id."""
        return asyncio.run(self._client.revoke_consent(subject_id, context, consent_id=consent_id))

    def check_consent(
        self,
        subject_id: str,
        memory_type: str,
        sensitivity: str,
        context: MemoryContext,
    ) -> bool:
        """Check consent respecting the context's tenant_id and purpose."""
        return asyncio.run(
            self._client.check_consent(subject_id, memory_type, sensitivity, context)
        )

    # ── stats ──────────────────────────────────────────────────────────────────

    def get_stats(self, context: MemoryContext) -> dict[str, Any]:
        """Return summary statistics from the backend."""
        return asyncio.run(self._client.get_stats(context))
