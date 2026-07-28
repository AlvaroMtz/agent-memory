"""Synchronous MemoryClient wrapper using asyncio.run().

Use this class from synchronous application code.  All methods block
on the underlying async client via ``asyncio.run()``, so callers must
not be inside an existing event loop.

Example::

    with SyncMemoryClient(backend, extractor, embedder, consent) as client:
        client.remember("I like coffee.", context=ctx)
        results = client.retrieve("coffee", context=ctx)
"""

from __future__ import annotations

import asyncio
from typing import Any

from agent_memory.client import MemoryClient
from agent_memory.context import MemoryContext
from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.domain.consent import ConsentRecord
from agent_memory.domain.retrieval import RetrievalResult
from agent_memory.ports.backend import MemoryBackend
from agent_memory.ports.consent import ConsentProvider
from agent_memory.ports.embedder import EmbeddingProvider
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
    ) -> None:
        self._client = MemoryClient(backend, extractor, embedder, consent)

    def __enter__(self) -> "SyncMemoryClient":
        asyncio.run(self._client.__aenter__())
        return self

    def __exit__(self, *exc: Any) -> None:
        asyncio.run(self._client.__aexit__(*exc))

    # ── remember ───────────────────────────────────────────────────────────

    def remember(
        self,
        text: str,
        context: MemoryContext,
        messages: list[dict[str, Any]] | None = None,
    ) -> list[MemoryCandidate]:
        """Extract and persist memories from *text* (or *messages*).**
        """
        return asyncio.run(self._client.remember(text, context, messages))

    # ── retrieve ───────────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        context: MemoryContext,
        filters: dict[str, Any] | None = None,
        max_tokens: int = 1200,
    ) -> RetrievalResult:
        """Run the full retrieval pipeline."""
        return asyncio.run(
            self._client.retrieve(query, context, filters, max_tokens)
        )

    # ── consent ────────────────────────────────────────────────────────────

    def grant_consent(
        self,
        subject_id: str,
        memory_types: list[str],
        sensitivity: str = "public",
        allow_read: bool = True,
        allow_write: bool = False,
    ) -> ConsentRecord:
        """Grant consent for a subject."""
        return asyncio.run(
            self._client.grant_consent(
                subject_id,
                memory_types,
                sensitivity,
                allow_read,
                allow_write,
            )
        )

    def revoke_consent(
        self,
        subject_id: str,
        consent_id: str | None = None,
    ) -> ConsentRecord:
        """Revoke consent."""
        return asyncio.run(self._client.revoke_consent(subject_id, consent_id))

    def check_consent(
        self,
        subject_id: str,
        memory_type: str,
        sensitivity: str,
    ) -> bool:
        """Check whether the subject has active consent."""
        return asyncio.run(
            self._client.check_consent(subject_id, memory_type, sensitivity)
        )

    # ── stats ──────────────────────────────────────────────────────────────

    def get_stats(self, context: MemoryContext) -> dict[str, Any]:
        """Return summary statistics from the backend."""
        return asyncio.run(self._client.get_stats(context))