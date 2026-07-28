"""MemoryMiddleware — integrates agent-memory with LangChain's callback system.

Provides before_model_hook and after_agent_hook for automatic memory injection
and extraction during agent conversation loops.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine, TypeVar

from agent_memory.application.remember import extract_memories
from agent_memory.application.retrieve import retrieve as app_retrieve
from agent_memory.constants import DEFAULT_TOP_K
from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.domain.retrieval import RetrievalResult
from agent_memory.exceptions import MemoryNotFoundError
from agent_memory.ports.backend import MemoryBackend
from agent_memory.ports.consent import ConsentProvider
from agent_memory.ports.embedder import EmbeddingProvider
from agent_memory.ports.extractor import MemoryExtractor

logger = logging.getLogger(__name__)

T = TypeVar("T")


class MemoryMiddlewareConfig:
    """Configuration for the MemoryMiddleware.

    Attributes:
        enabled: Master switch for memory operations.
        auto_extract: If True, automatically extract memories after model calls.
        context_selector: Optional callable that extracts
            (tenant_id, subject_id) from the LangChain runnable config.
        top_k: Maximum number of memories to inject as context (default 8).
        max_tokens: Maximum token budget for retrieved memories (default 1200).
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        auto_extract: bool = True,
        context_selector: Callable[[dict[str, Any]], tuple[str, str]] | None = None,
        top_k: int = DEFAULT_TOP_K,
        max_tokens: int = 1200,
    ) -> None:
        self.enabled = enabled
        self.auto_extract = auto_extract
        self.context_selector = context_selector
        self.top_k = top_k
        self.max_tokens = max_tokens


class MemoryMiddleware:
    """LangChain-compatible middleware for memory injection and extraction.

    This middleware integrates with LangChain's callback system:

    before_model_hook():
        Called before a model is invoked. Injects relevant memories
        as context into the prompt (e.g. user preferences, system rules).

    after_agent_hook():
        Called after the agent responds. Processes the response to
        extract new memories via the extraction pipeline.

    Example::

        middleware = MemoryMiddleware(
            backend=backend,
            embedder=embedder,
            extractor=extractor,
            consent=consent_provider,
            config=MemoryMiddlewareConfig(auto_extract=True),
        )

        async with middleware.callback_context():
            result = await chain.ainvoke(inputs)

    Notes:
        - The middleware is reentrant and async-safe.
        - All memory operations are gated by the ``enabled`` flag.
        - ``context_selector`` is optional; if not provided the middleware
          defaults to using ``subject_id`` from the config's ``agent_id`` field
          and ``tenant_id`` from the config's ``tenant_id`` field.
    """

    def __init__(
        self,
        backend: MemoryBackend,
        embedder: EmbeddingProvider | None = None,
        extractor: MemoryExtractor | None = None,
        consent: ConsentProvider | None = None,
        config: MemoryMiddlewareConfig | None = None,
    ) -> None:
        self.backend = backend
        self.embedder = embedder
        self.extractor = extractor
        self.consent = consent
        self.config = config or MemoryMiddlewareConfig()

    # ── Public API ──────────────────────────────────────────────────────────

    async def before_model_hook(
        self,
        callbacks: list[Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Inject relevant memories as context before a model call.

        Extracts (tenant_id, subject_id) via the config's context_selector,
        then runs the retrieval pipeline and prepends results to the prompt.

        Returns:
            Updated kwargs dict with an ``_memory_context`` key containing
            a dict of { "retrieved_memories": list[RetrievedMemory], ... }.

        Raises:
            MemoryNotFoundError: If the tenant_id/subject_id cannot be
                determined from the runnable config.
        """
        if not self.config.enabled:
            kwargs.setdefault("_memory_context", {"retrieved_memories": []})
            return kwargs

        tenant_id, subject_id = self._extract_context(kwargs)

        # Build filters from kwargs if present
        filters: dict[str, Any] | None = kwargs.get("filters")

        try:
            result: RetrievalResult = await app_retrieve(
                tenant_id=tenant_id,
                subject_id=subject_id,
                filters=filters,
                backend=self.backend,
                embedder=self.embedder,
                consent=self.consent,
                max_tokens=self.config.max_tokens,
            )
        except Exception:
            logger.exception("Memory retrieval failed in before_model_hook")
            result = RetrievalResult(
                query="", results=[], total_count=0,
                token_count=0, token_budget=self.config.max_tokens,
            )

        kwargs.setdefault("_memory_context", {})
        kwargs["_memory_context"]["retrieved_memories"] = result.results
        kwargs["_memory_context"]["retrieval_result"] = result
        return kwargs

    async def after_agent_hook(
        self,
        response: Any,
        **kwargs: Any,
    ) -> list[MemoryCandidate]:
        """Extract new memories from the agent response.

        Runs the extraction pipeline (via ``extract_memories``) on the
        conversation messages passed in ``kwargs["messages"]``.

        Args:
            response: The agent's response (not used directly).
            **kwargs: Must contain at least:
                - ``messages``: list of message dicts with id/role/content.
                - ``_memory_context``: optional dict from a prior before_model_hook.

        Returns:
            List of validated ``MemoryCandidate`` objects extracted from the
            response.
        """
        if not self.config.enabled or not self.config.auto_extract:
            return []

        messages: list[dict] | None = kwargs.get("messages")
        if not messages:
            logger.warning("No messages provided to after_agent_hook")
            return []

        tenant_id, subject_id = self._extract_context(kwargs)

        try:
            candidates = await extract_memories(
                messages=messages,
                subject_id=subject_id,
                tenant_id=tenant_id,
                extractor=self.extractor,
                consent=self.consent,
            )
        except Exception:
            logger.exception("Memory extraction failed in after_agent_hook")
            return []

        return candidates

    # ── Context extraction ──────────────────────────────────────────────────

    def _extract_context(
        self, kwargs: dict[str, Any]
    ) -> tuple[str, str]:
        """Determine (tenant_id, subject_id) from the runnable config.

        Uses the configured ``context_selector`` if available, otherwise
        falls back to reading keys from ``kwargs``.

        Returns:
            (tenant_id, subject_id) tuple.
        """
        if self.config.context_selector:
            return self.config.context_selector(kwargs)

        # Default extraction from kwargs
        tenant_id = kwargs.get("tenant_id", "default-tenant")
        subject_id = kwargs.get("subject_id", kwargs.get("agent_id", "default-user"))
        return tenant_id, subject_id

    # ── Context manager (optional) ──────────────────────────────────────────

    def callback_context(
        self,
        callbacks: list[Any] | None = None,
        **kwargs: Any,
    ) -> _MemoryContextManager:
        """Async context manager for automatic before/after hooks.

        Example::

            async with middleware.callback_context(messages=msgs) as ctx:
                result = await chain.ainvoke(inputs)

        The context manager automatically calls before_model_hook and
        after_agent_hook, making manual hook invocation unnecessary.
        """
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