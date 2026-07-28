"""High-level async MemoryClient facade over backend, extractor, embedder, and consent."""

from __future__ import annotations

import logging
from typing import Any

from agent_memory.application.remember import extract_memories
from agent_memory.application.retrieve import retrieve
from agent_memory.context import MemoryContext
from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.domain.consent import ConsentRecord, ConsentGrant
from agent_memory.domain.retrieval import RetrievalResult
from agent_memory.ports.backend import MemoryBackend
from agent_memory.ports.consent import ConsentProvider
from agent_memory.ports.embedder import EmbeddingProvider
from agent_memory.ports.extractor import MemoryExtractor

logger = logging.getLogger(__name__)


class MemoryClient:
    """Async high-level facade over memory backend, extractor, embedder, and consent.

    Use this client in application code that already runs in an async context.
    For synchronous code, use ``SyncMemoryClient`` from ``agent_memory.sync_client``.

    Example::

        async with MemoryClient(backend, extractor, embedder, consent) as client:
            await client.remember("I like coffee.", context=ctx)
            results = await client.retrieve("coffee", context=ctx)
    """

    def __init__(
        self,
        backend: MemoryBackend,
        extractor: MemoryExtractor | None = None,
        embedder: EmbeddingProvider | None = None,
        consent: ConsentProvider | None = None,
    ) -> None:
        self._backend = backend
        self._extractor = extractor
        self._embedder = embedder
        self._consent = consent

    async def __aenter__(self) -> "MemoryClient":
        if hasattr(self._backend, "initialize"):
            await self._backend.initialize()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if hasattr(self._backend, "close"):
            await self._backend.close()

    # ── remember ───────────────────────────────────────────────────────────

    async def remember(
        self,
        text: str,
        context: MemoryContext,
        messages: list[dict[str, Any]] | None = None,
    ) -> list[MemoryCandidate]:
        """Extract memories from *text* (or *messages*) and persist them.

        If *messages* is provided, those messages are used directly.
        Otherwise a synthetic message is created from *text*.
        """
        if messages is None:
            messages = [
                {"id": "user-0", "role": "user", "content": text},
            ]

        candidates = await extract_memories(
            messages=messages,
            subject_id=context.subject_id,
            tenant_id=context.tenant_id,
            extractor=self._extractor,
            consent=self._consent,
        )
        return candidates

    # ── retrieve ───────────────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        context: MemoryContext,
        filters: dict[str, Any] | None = None,
        max_tokens: int = 1200,
    ) -> RetrievalResult:
        """Run the full retrieval pipeline.

        Returns a ``RetrievalResult`` with up to *max_tokens* tokens of results.
        """
        return await retrieve(
            tenant_id=context.tenant_id,
            subject_id=context.subject_id,
            query=query,
            filters=filters,
            backend=self._backend,
            embedder=self._embedder,
            consent=self._consent,
            max_tokens=max_tokens,
        )

    # ── consent ────────────────────────────────────────────────────────────

    async def grant_consent(
        self,
        subject_id: str,
        memory_types: list[str],
        sensitivity: str = "public",
        allow_read: bool = True,
        allow_write: bool = False,
    ) -> ConsentRecord:
        """Grant consent for a subject and return the persisted record."""
        if self._consent is None:
            raise RuntimeError("ConsentProvider not configured")
        from agent_memory.context import TenantContext

        grant = ConsentGrant(
            purpose="general",
            allow_read=allow_read,
            allow_write=allow_write,
            allowed_memory_types=set(memory_types),
            allowed_sensitivity={sensitivity},
        )
        ctx = TenantContext(tenant_id="default", actor_id=subject_id)
        return await self._consent.grant_consent(grant, context=ctx)

    async def revoke_consent(
        self,
        subject_id: str,
        consent_id: str | None = None,
    ) -> ConsentRecord:
        """Revoke consent. If *consent_id* is None, revokes all active consent."""
        if self._consent is None:
            raise RuntimeError("ConsentProvider not configured")
        from agent_memory.context import TenantContext

        records = await self._consent.list_consent(tenant_id="default", subject_id=subject_id)
        for record in records:
            if not record.is_revoked():
                cid = str(record.id) if consent_id is None else consent_id
                ctx = TenantContext(tenant_id="default", actor_id=subject_id)
                return await self._consent.revoke_consent(cid, context=ctx)
        raise ValueError(f"No active consent found for subject {subject_id}")

    async def check_consent(
        self,
        subject_id: str,
        memory_type: str,
        sensitivity: str,
    ) -> bool:
        """Check whether the subject has active consent for the given type."""
        if self._consent is None:
            return False
        record = await self._consent.get_active_consent(
            tenant_id="default",
            subject_id=subject_id,
            purpose="general",
        )
        if record is None:
            return False
        return record.allows_read(memory_type, sensitivity)

    # ── stats ──────────────────────────────────────────────────────────────

    async def get_stats(self, context: MemoryContext) -> dict[str, Any]:
        """Return summary statistics from the backend."""
        try:
            memories = await self._backend.list_memories(
                tenant_id=context.tenant_id,
                subject_id=context.subject_id,
                limit=1000,
            )
            counts: dict[str, int] = {}
            for mem in memories:
                counts[mem.memory_type] = counts.get(mem.memory_type, 0) + 1
            return {
                "total_memories": len(memories),
                "by_type": counts,
            }
        except Exception as exc:
            logger.warning("get_stats failed: %s", exc)
            return {"total_memories": 0, "by_type": {}, "error": str(exc)}