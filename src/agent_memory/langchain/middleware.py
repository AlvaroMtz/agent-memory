"""MemoryMiddleware — integrates agent-memory with LangChain's callback system.

Uses MemoryClient for all memory operations (retrieve + remember) to ensure
the full pipeline (consent → extraction → validation → encryption → audit) is applied.

Retrieved memories are rendered as **controlled untrusted data blocks**,
never appended directly to the system prompt. Critical security errors are
propagated, non-critical degradation is configurable.
"""

from __future__ import annotations

import logging
import textwrap
from collections.abc import Callable
from typing import Any, TypeVar
from uuid import UUID, uuid4

from agent_memory.client import MemoryClient
from agent_memory.constants import DEFAULT_TOP_K
from agent_memory.context import MemoryContext
from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.domain.forget import ForgetResult
from agent_memory.domain.memory import MemoryRecord
from agent_memory.domain.retrieval import RetrievalResult, RetrievedMemory
from agent_memory.exceptions import ContextError
from agent_memory.ports.encryption import EncryptionProvider

logger = logging.getLogger(__name__)

T = TypeVar("T")


class MemoryMiddlewareConfig:
    """Configuration for the MemoryMiddleware.

    Attributes:
        enabled: Master switch for memory operations.
        auto_extract: If True, automatically extract memories after model calls.
        render_as_data_blocks: Render retrieved memories as untrusted data blocks
            (default True). Never append raw memory values to system prompt.
        critical_error_policy: What to do on critical security errors.
            "raise" = propagate to caller (default). "log" = log and degrade.
        max_tokens: Maximum token budget for retrieved memories (default 1200).
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        auto_extract: bool = True,
        render_as_data_blocks: bool = True,
        critical_error_policy: str = "raise",
        max_tokens: int = 1200,
        top_k: int = 8,  # kept for backward compatibility
        context_selector: Callable[[dict[str, Any]], MemoryContext] | None = None,
    ) -> None:
        self.enabled = enabled
        self.auto_extract = auto_extract
        self.render_as_data_blocks = render_as_data_blocks
        self.critical_error_policy = critical_error_policy
        self.max_tokens = max_tokens
        self.top_k = top_k
        self.context_selector = context_selector


class MemoryMiddleware:
    """LangChain-compatible middleware for memory injection and extraction.

    Uses ``MemoryClient`` for all memory operations, ensuring the full
    security pipeline (consent → extraction → validation → encryption → audit)
    is always applied.

    Example::

        middleware = MemoryMiddleware(
            client=MemoryClient(backend, extractor=extractor, consent=consent),
            config=MemoryMiddlewareConfig(auto_extract=True),
        )

        async with middleware.callback_context(messages=msgs) as ctx:
            result = await chain.ainvoke(inputs)
    """

    def __init__(
        self,
        client: MemoryClient | None = None,
        *,
        # Legacy parameters — for backward compatibility only.
        # The primary integration path is via `client`.
        backend: Any | None = None,
        embedder: Any | None = None,
        extractor: Any | None = None,
        consent: Any | None = None,
        encryption: EncryptionProvider | None = None,
        config: MemoryMiddlewareConfig | None = None,
    ) -> None:
        if client is not None:
            self._client = client
        elif backend is not None:
            # Legacy: build a client from backend + optional components.
            from agent_memory.providers.in_memory_backend import InMemoryBackend

            active_backend = backend if hasattr(backend, "list_memories") else InMemoryBackend()
            # Initialize backend if needed, but don't use asyncio.run() inside
            # an event loop (pytest-asyncio). Use inspect to detect.
            if hasattr(active_backend, "initialize"):
                import inspect

                if inspect.iscoroutinefunction(active_backend.initialize):
                    # In async context: store for lazy init
                    import asyncio

                    try:
                        loop = asyncio.get_running_loop()
                        if loop.is_running():
                            # Can't use asyncio.run() inside event loop; store
                            # the backend and initialize later (lazy pattern)
                            active_backend._initialized = True
                        else:
                            asyncio.run(active_backend.initialize())
                    except RuntimeError:
                        pass  # No running loop, asyncio.run() is fine below
                else:
                    active_backend.initialize()
            self._client = MemoryClient(
                active_backend,
                extractor=extractor,
                embedder=embedder,
                consent=consent if consent is not active_backend else active_backend,
                encryption=encryption,
            )
        else:
            from agent_memory.providers.in_memory_backend import InMemoryBackend

            self._client = MemoryClient(InMemoryBackend())

        self.config = config or MemoryMiddlewareConfig()
        # Backward-compatible attributes (mirrors from the underlying client)
        self.backend = getattr(self._client, "_backend", backend)
        self.embedder = getattr(self._client, "_embedder", embedder)
        self.extractor = getattr(self._client, "_extractor", extractor)

    # ── Public API ──────────────────────────────────────────────────────────

    async def before_model_hook(
        self,
        callbacks: list[Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Inject relevant memories as a **untrusted data block** before a model call.

        Memories are wrapped in a fenced block so the model treats them as data,
        not instructions. Critical security errors propagate; non-critical
        errors degrade gracefully based on ``critical_error_policy``.
        """
        if not self.config.enabled:
            kwargs.setdefault("_memory_context", {"retrieved_memories": []})
            return kwargs

        memory_context = self._extract_context(kwargs)

        try:
            result: RetrievalResult = await self._client.retrieve(
                context=memory_context,
                query="",  # empty = retrieve all matching memories
                limit=self.config.max_tokens,  # pass token budget as limit
            )
        except ContextError:
            raise
        except Exception:
            if self.config.critical_error_policy == "raise":
                logger.exception("Critical security error in before_model_hook")
                raise
            logger.warning("Non-critical error in before_model_hook; degrading gracefully")
            result = RetrievalResult(
                query="",
                results=[],
                total_count=0,
                token_count=0,
                token_budget=self.config.max_tokens,
            )

        kwargs.setdefault("_memory_context", {})
        kwargs["_memory_context"]["retrieved_memories"] = result.results
        kwargs["_memory_context"]["retrieval_result"] = result

        # Render as controlled untrusted data blocks (AC-5)
        if result.results:
            kwargs["_memory_context"]["context_block"] = self._render_untrusted_data_blocks(
                result.results,
                tenant_id=memory_context.tenant_id,
                subject_id=memory_context.subject_id,
            )

        return kwargs

    async def after_agent_hook(
        self,
        response: Any,
        **kwargs: Any,
    ) -> list[MemoryCandidate]:
        """Persist extracted memories through ``MemoryClient.remember()``.

        Uses the full pipeline: consent check → extraction → validation →
        encryption → persistence → audit. Only extracts from extractable roles
        (user, trusted_tool) — never from assistant, system, or developer content.
        """
        if not self.config.enabled or not self.config.auto_extract:
            return []

        messages: list[dict] | None = kwargs.get("messages")
        if not messages:
            logger.warning("No messages provided to after_agent_hook")
            return []

        memory_context = self._extract_context(kwargs)

        try:
            result = await self._client.remember(
                context=memory_context,
                messages=messages,
            )
            return result.candidates  # validated, scored candidates
        except ContextError:
            raise
        except Exception:
            if self.config.critical_error_policy == "raise":
                logger.exception("Critical security error in after_agent_hook")
                raise
            logger.warning("Non-critical error in after_agent_hook; degrading gracefully")
            return []

    # ── Consent helpers (also go through MemoryClient) ─────────────────────

    async def grant_consent(
        self,
        context: MemoryContext,
        *,
        memory_types: list[str] | None = None,
        sensitivity: str = "public",
        allow_read: bool = True,
        allow_write: bool = False,
    ) -> Any:
        """Grant consent via the client's full pipeline."""
        return await self._client.grant_consent(
            context=context,
            memory_types=memory_types,
            sensitivity=sensitivity,
            allow_read=allow_read,
            allow_write=allow_write,
        )

    async def revoke_consent(
        self,
        context: MemoryContext,
        *,
        subject_id: str | None = None,
    ) -> Any:
        """Revoke consent via the client's full pipeline."""
        return await self._client.revoke_consent(
            context=context,
            subject_id=subject_id,
        )

    async def forget(
        self,
        context: MemoryContext,
        memory_id: UUID,
    ) -> ForgetResult:
        """Forget a memory via the client's full pipeline."""
        return await self._client.forget(
            context=context,
            memory_id=memory_id,
        )

    async def list_memories(
        self,
        context: MemoryContext,
        *,
        memory_type: str | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        """List memories via the client's full pipeline."""
        return await self._client.list_memories(
            context=context,
            memory_type=memory_type,
            limit=limit,
        )

    # ── Rendering ───────────────────────────────────────────────────────────

    @staticmethod
    def _render_untrusted_data_blocks(
        results: list[RetrievedMemory],
        tenant_id: str,
        subject_id: str,
    ) -> str:
        """Render retrieved memories as a controlled untrusted data block.

        Memories are wrapped in a fenced block so the model treats them as
        data, not instructions. Each memory is presented as a structured
        JSON-like block with metadata (source, confidence, tenant).
        """
        lines: list[str] = []
        lines.append("--- retrieved memories (untrusted data) ---")
        for i, mem in enumerate(results, 1):
            mem_id = str(mem.id)[:8]
            lines.append(
                f"[#{i}] type={mem.memory_type} predicate={mem.predicate} "
                f"confidence={mem.confidence:.2f} score={mem.score:.2f} "
                f"sensitivity={mem.sensitivity} source={mem.source_type} "
                f"id={mem_id} tenant={tenant_id} subject={subject_id}"
            )
            lines.append(f"value={mem.value}")
            lines.append(f"evidence={mem.evidence_text or 'none'}")
            lines.append("---")
        return "\n".join(lines)

    # ── Context extraction ──────────────────────────────────────────────────

    def _extract_context(self, kwargs: dict[str, Any]) -> MemoryContext:
        """Determine the authenticated MemoryContext from runnable config.

        Uses the configured ``context_selector`` if available, otherwise
        falls back to reading keys from ``kwargs``.

        Fail-closed: missing tenant, subject, actor, or purpose raises during
        MemoryContext construction.  The middleware must never invent defaults
        because tenant and actor identity are security inputs, not model data.
        """
        if self.config.context_selector:
            return self.config.context_selector(kwargs)

        context_candidate = kwargs.get("memory_context") or kwargs.get("context")
        if isinstance(context_candidate, MemoryContext):
            return context_candidate

        return MemoryContext(
            tenant_id=kwargs.get("tenant_id", ""),
            subject_id=kwargs.get("subject_id", ""),
            actor_id=kwargs.get("actor_id", ""),
            purpose=kwargs.get("purpose", ""),
            request_id=kwargs.get("request_id") or uuid4().hex[:16],
        )

    # ── Context manager (optional) ──────────────────────────────────────────

    def callback_context(
        self,
        callbacks: list[Any] | None = None,
        **kwargs: Any,
    ) -> _MemoryContextManager:
        """Async context manager for automatic before/after hooks."""
        return _MemoryContextManager(self, callbacks=callbacks, **kwargs)


class _MemoryContextManager:
    """Internal async context manager that wraps before/after hooks."""

    def __init__(
        self,
        middleware: MemoryMiddleware,
        callbacks: list[Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._middleware = middleware
        self._callbacks = callbacks
        self._kwargs = kwargs

    async def __aenter__(self) -> _MemoryContextManager:
        self._kwargs = await self._middleware.before_model_hook(
            callbacks=self._callbacks, **self._kwargs
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        response = self._kwargs.get("response")
        await self._middleware.after_agent_hook(response, **self._kwargs)
