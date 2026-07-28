"""Integration tests for LangChain integration layer.

Tests MemoryMiddleware, ContextAdapter, AgentMemoryStoreAdapter, and tools
integration without requiring actual LangChain installation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest

from agent_memory.context import MemoryContext, TenantContext
from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.domain.memory import MemoryRecord, MemoryVersion
from agent_memory.domain.retrieval import RetrievedMemory, RetrievalResult
from agent_memory.langchain.context import ContextAdapter
from agent_memory.langchain.middleware import MemoryMiddleware, MemoryMiddlewareConfig
from agent_memory.langchain.store_adapter import AgentMemoryStoreAdapter
from agent_memory.langchain.tools import (
    MEMORY_TOOL_KEY,
    TRUSTED_TOOL_SOURCE,
    is_trusted_tool,
    mark_tool_as_trusted,
    trust_tool_output,
)
from agent_memory.providers.in_memory_backend import InMemoryBackend


# ── Mock LangChain objects ──────────────────────────────────────────────────


class MockRunnableConfig:
    """Mock LangChain RunnableConfig for testing."""

    def __init__(self, metadata: dict[str, Any] | None = None, tags: list[str] | None = None) -> None:
        self.metadata = metadata or {}
        self.tags = tags or []

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class MockBaseMessage:
    """Mock LangChain BaseMessage for testing."""

    def __init__(
        self,
        role: str = "user",
        content: str = "Hello",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.role = role
        self.content = content
        self.metadata = metadata or {}
        self.type = role


class MockToolCall:
    """Mock LangChain ToolCall for testing."""

    def __init__(self, name: str = "test_tool", metadata: dict[str, Any] | None = None) -> None:
        self.name = name
        self.metadata = metadata or {}

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def backend() -> InMemoryBackend:
    return InMemoryBackend()


@pytest.fixture
def middleware(backend: InMemoryBackend) -> MemoryMiddleware:
    return MemoryMiddleware(
        backend=backend,
        config=MemoryMiddlewareConfig(
            enabled=True,
            auto_extract=True,
        ),
    )


# ── Tests ───────────────────────────────────────────────────────────────────


class TestMemoryMiddlewareConfig:
    """Tests for MemoryMiddlewareConfig."""

    def test_default_config(self):
        """Config has correct defaults."""
        config = MemoryMiddlewareConfig()
        assert config.enabled is True
        assert config.auto_extract is True
        assert config.context_selector is None
        assert config.top_k == 8
        assert config.max_tokens == 1200

    def test_custom_config(self):
        """Config can be customized."""
        config = MemoryMiddlewareConfig(
            enabled=False,
            auto_extract=False,
            top_k=4,
            max_tokens=500,
        )
        assert config.enabled is False
        assert config.auto_extract is False
        assert config.top_k == 4
        assert config.max_tokens == 500


class TestMemoryMiddleware:
    """Tests for MemoryMiddleware."""

    async def test_middleware_creation(self, backend: InMemoryBackend):
        """Middleware can be created with required backend."""
        mw = MemoryMiddleware(backend=backend)
        assert mw.backend is backend
        assert mw.embedder is None
        assert mw.extractor is None

    async def test_middleware_disabled(self, middleware: MemoryMiddleware):
        """Disabled middleware returns empty context."""
        middleware.config.enabled = False
        result = await middleware.before_model_hook()
        assert "_memory_context" in result
        assert result["_memory_context"].get("retrieved_memories") == []

    async def test_before_model_hook_with_backend(self, middleware: MemoryMiddleware):
        """Middleware with backend returns memory context."""
        middleware.config.enabled = True
        result = await middleware.before_model_hook(
            tenant_id="test-tenant",
            subject_id="test-user",
        )
        assert "_memory_context" in result
        assert "retrieved_memories" in result["_memory_context"]

    async def test_after_agent_hook_no_messages(self, middleware: MemoryMiddleware):
        """after_agent_hook returns empty list when no messages."""
        middleware.config.enabled = True
        middleware.config.auto_extract = True
        candidates = await middleware.after_agent_hook("response")
        assert candidates == []

    async def test_after_agent_hook_disabled(self, middleware: MemoryMiddleware):
        """after_agent_hook returns empty when auto_extract is False."""
        middleware.config.enabled = True
        middleware.config.auto_extract = False
        candidates = await middleware.after_agent_hook(
            "response",
            messages=[{"role": "user", "content": "hello", "id": "1"}],
        )
        assert candidates == []

    async def test_callback_context(self, middleware: MemoryMiddleware):
        """Context manager works end-to-end."""
        async with middleware.callback_context(
            tenant_id="t", subject_id="s", messages=[]
        ):
            pass  # Should not raise

    async def test_context_selector(self, middleware: MemoryMiddleware):
        """Custom context_selector is used."""
        middleware.config.context_selector = lambda kwargs: ("custom-tenant", "custom-user")
        result = await middleware.before_model_hook()
        assert "_memory_context" in result


class TestContextAdapter:
    """Tests for ContextAdapter."""

    def test_extract_from_runtime_full(self):
        """Extracts all context fields from runnable config."""
        adapter = ContextAdapter()
        config = MockRunnableConfig(
            metadata={
                "tenant_id": "acme",
                "subject_id": "user-123",
                "actor_id": "agent-456",
                "purpose": "conversation",
            },
        )
        ctx = adapter.extract_from_runtime(config)
        assert isinstance(ctx, MemoryContext)
        assert ctx.tenant_id == "acme"
        assert ctx.subject_id == "user-123"
        assert ctx.actor_id == "agent-456"
        assert ctx.purpose == "conversation"

    def test_extract_from_runtime_tags(self):
        """Extracts context from tags with prefix."""
        adapter = ContextAdapter()
        config = MockRunnableConfig(
            tags=["tenant:acme", "subject:user-1", "agent:bot-1", "purpose:chat"],
        )
        ctx = adapter.extract_from_runtime(config)
        assert ctx.tenant_id == "acme"
        assert ctx.subject_id == "user-1"
        assert ctx.actor_id == "bot-1"
        assert ctx.purpose == "chat"

    def test_extract_from_runtime_missing_tenant(self):
        """Raises ValueError when tenant_id is missing."""
        adapter = ContextAdapter()
        config = MockRunnableConfig(
            metadata={
                "subject_id": "user-1",
                "actor_id": "agent-1",
                "purpose": "chat",
            },
        )
        with pytest.raises(ValueError, match="tenant_id is required"):
            adapter.extract_from_runtime(config)

    def test_extract_from_runtime_missing_subject(self):
        """Raises ValueError when subject_id is missing."""
        adapter = ContextAdapter()
        config = MockRunnableConfig(
            metadata={
                "tenant_id": "acme",
                "actor_id": "agent-1",
                "purpose": "chat",
            },
        )
        with pytest.raises(ValueError, match="subject_id is required"):
            adapter.extract_from_runtime(config)

    def test_extract_from_message_user(self):
        """Extracts metadata from user message."""
        adapter = ContextAdapter()
        msg = MockBaseMessage(role="user", content="Hello world")
        result = adapter.extract_from_message(msg)
        assert result["role"] == "user"
        assert result["content"] == "Hello world"

    def test_extract_from_message_system(self):
        """System messages are extracted but should not trigger processing."""
        adapter = ContextAdapter()
        msg = MockBaseMessage(role="system", content="System prompt")
        result = adapter.extract_from_message(msg)
        assert result["role"] == "system"

    def test_should_process_user(self):
        """User messages should be processed."""
        adapter = ContextAdapter()
        msg = MockBaseMessage(role="user", content="Hello")
        assert adapter.should_process(msg) is True

    def test_should_process_assistant(self):
        """Assistant messages should be processed."""
        adapter = ContextAdapter()
        msg = MockBaseMessage(role="assistant", content="Hi there")
        assert adapter.should_process(msg) is True

    def test_should_process_system(self):
        """System messages should NOT be processed."""
        adapter = ContextAdapter()
        msg = MockBaseMessage(role="system", content="System prompt")
        assert adapter.should_process(msg) is False


class TestAgentMemoryStoreAdapter:
    """Tests for AgentMemoryStoreAdapter."""

    async def test_adapter_creation(self, backend: InMemoryBackend):
        """Adapter can be created with required backend."""
        adapter = AgentMemoryStoreAdapter(
            backend=backend,
            namespace="test",
            tenant_id="t1",
            subject_id="s1",
        )
        assert adapter.tenant_id == "t1"
        assert adapter.subject_id == "s1"
        assert adapter.namespace == "test"

    async def test_mset_mget(self, backend: InMemoryBackend):
        """Can set and get values via mset/mget."""
        adapter = AgentMemoryStoreAdapter(
            backend=backend,
            tenant_id="t1",
            subject_id="s1",
        )
        await adapter.mset([("key1", "value1"), ("key2", {"nested": True})])
        results = await adapter.mget(["key1", "key2"])
        assert results[0] is not None
        assert results[1] is not None

    async def test_mget_missing_key(self, backend: InMemoryBackend):
        """mget returns None for missing keys."""
        adapter = AgentMemoryStoreAdapter(
            backend=backend,
            tenant_id="t1",
            subject_id="s1",
        )
        results = await adapter.mget(["nonexistent"])
        assert results[0] is None

    async def test_mdelete(self, backend: InMemoryBackend):
        """mdelete removes stored values."""
        adapter = AgentMemoryStoreAdapter(
            backend=backend,
            tenant_id="t1",
            subject_id="s1",
        )
        await adapter.mset([("key1", "value1")])
        await adapter.mdelete(["key1"])
        results = await adapter.mget(["key1"])
        assert results[0] is None

    async def test_tenant_isolation(self, backend: InMemoryBackend):
        """Different tenants see different data."""
        adapter1 = AgentMemoryStoreAdapter(
            backend=backend,
            tenant_id="tenant-a",
            subject_id="s1",
        )
        adapter2 = AgentMemoryStoreAdapter(
            backend=backend,
            tenant_id="tenant-b",
            subject_id="s1",
        )

        await adapter1.mset([("key1", "value-a")])

        # tenant-b should not see tenant-a's data
        results = await adapter2.mget(["key1"])
        assert results[0] is None

    async def test_yield_keys(self, backend: InMemoryBackend):
        """yield_keys returns stored keys."""
        adapter = AgentMemoryStoreAdapter(
            backend=backend,
            tenant_id="t1",
            subject_id="s1",
        )
        await adapter.mset([("key1", "v1"), ("key2", "v2")])
        keys = [k async for k in adapter.yield_keys()]
        assert len(keys) >= 2


class TestToolsIntegration:
    """Tests for tools integration."""

    def test_trusted_tool_decorator_sync(self):
        """Sync function decorated with trust_tool_output."""
        @trust_tool_output("test_tool")
        def sync_func() -> dict:
            return {"result": "ok"}

        result = sync_func()
        assert result[MEMORY_TOOL_KEY]["source"] == TRUSTED_TOOL_SOURCE
        assert result[MEMORY_TOOL_KEY]["tool_name"] == "test_tool"

    def test_trusted_tool_decorator_async(self):
        """Async function decorated with trust_tool_output."""
        @trust_tool_output("async_tool")
        async def async_func() -> dict:
            return {"result": "async-ok"}

        import asyncio

        result = asyncio.run(async_func())
        assert result[MEMORY_TOOL_KEY]["source"] == TRUSTED_TOOL_SOURCE
        assert result[MEMORY_TOOL_KEY]["tool_name"] == "async_tool"

    def test_is_trusted_tool_dict(self):
        """is_trusted_tool works with dict tool calls."""
        tool_call = {
            "name": "weather",
            "metadata": {
                MEMORY_TOOL_KEY: {"source": TRUSTED_TOOL_SOURCE, "tool_name": "weather"},
            },
        }
        assert is_trusted_tool(tool_call) is True

    def test_is_not_trusted_tool(self):
        """is_trusted_tool returns False for non-trusted tools."""
        tool_call = {
            "name": "weather",
            "metadata": {},
        }
        assert is_trusted_tool(tool_call) is False

    def test_mark_tool_as_trusted(self):
        """mark_tool_as_trusted adds metadata to tool call."""
        tool_call: dict[str, Any] = {"name": "search"}
        result = mark_tool_as_trusted(tool_call, "search")
        assert result["metadata"][MEMORY_TOOL_KEY]["source"] == TRUSTED_TOOL_SOURCE
        assert result["metadata"][MEMORY_TOOL_KEY]["tool_name"] == "search"


class TestStoreAdapterIntegration:
    """Integration tests for StoreAdapter with InMemoryBackend."""

    async def test_full_lifecycle(self, backend: InMemoryBackend):
        """Full lifecycle: set -> get -> delete."""
        adapter = AgentMemoryStoreAdapter(
            backend=backend,
            tenant_id="t1",
            subject_id="s1",
        )

        # Set
        await adapter.mset([("pref:language", "en"), ("pref:timezone", "UTC")])

        # Get
        values = await adapter.mget(["pref:language", "pref:timezone"])
        assert values[0] is not None
        assert values[1] is not None

        # Delete
        await adapter.mdelete(["pref:language"])
        result = await adapter.mget(["pref:language"])
        assert result[0] is None

    async def test_namespace_isolation(self, backend: InMemoryBackend):
        """Different namespaces are isolated."""
        adapter1 = AgentMemoryStoreAdapter(
            backend=backend,
            tenant_id="t1",
            subject_id="s1",
            namespace="ns1",
        )
        adapter2 = AgentMemoryStoreAdapter(
            backend=backend,
            tenant_id="t1",
            subject_id="s1",
            namespace="ns2",
        )

        await adapter1.mset([("key", "value")])
        results = await adapter2.mget(["key"])
        assert results[0] is None


class TestContextAdapterEdgeCases:
    """Edge case tests for ContextAdapter."""

    def test_extract_fallback_kwargs(self):
        """Falls back to kwargs when metadata is missing."""
        adapter = ContextAdapter()
        config = MockRunnableConfig()
        ctx = adapter.extract_from_runtime(
            config,
            tenant_id="kwarg-tenant",
            subject_id="kwarg-subject",
            actor_id="kwarg-actor",
            purpose="kwarg-purpose",
        )
        assert ctx.tenant_id == "kwarg-tenant"
        assert ctx.subject_id == "kwarg-subject"
        assert ctx.actor_id == "kwarg-actor"
        assert ctx.purpose == "kwarg-purpose"

    def test_should_process_tool(self):
        """Tool messages should be processed."""
        adapter = ContextAdapter()
        msg = MockBaseMessage(role="tool", content="Tool output")
        assert adapter.should_process(msg) is True

    def test_should_process_unknown_role(self):
        """Unknown roles are not processed."""
        adapter = ContextAdapter()
        msg = MockBaseMessage(role="unknown_role", content="")
        assert adapter.should_process(msg) is False