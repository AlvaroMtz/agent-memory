"""Unit tests for the MemoryClient (src/agent_memory/client.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_memory.client import MemoryClient
from agent_memory.context import MemoryContext


class TestMemoryClient:
    """Tests for the async MemoryClient facade."""

    @pytest.fixture
    def mock_backend(self) -> MagicMock:
        backend = MagicMock()
        backend.initialize = AsyncMock()
        backend.close = AsyncMock()
        backend.list_memories = AsyncMock(return_value=[])
        return backend

    @pytest.fixture
    def mock_extractor(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mock_embedder(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mock_consent(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def context(self) -> MemoryContext:
        return MemoryContext(
            tenant_id="t1",
            subject_id="s1",
            actor_id="a1",
            purpose="test",
        )

    @pytest.fixture
    def client(
        self,
        mock_backend: MagicMock,
        mock_extractor: MagicMock,
        mock_embedder: MagicMock,
        mock_consent: MagicMock,
    ) -> MemoryClient:
        return MemoryClient(mock_backend, mock_extractor, mock_embedder, mock_consent)

    @pytest.mark.asyncio
    async def test_init_with_backend(self, mock_backend: MagicMock):
        """Client initializes backend on __aenter__."""
        async with MemoryClient(mock_backend) as client:
            mock_backend.initialize.assert_called_once()
            assert client._backend is mock_backend

    @pytest.mark.asyncio
    async def test_remember_no_messages(self, client: MemoryClient, context: MemoryContext):
        """remember creates a synthetic message from text."""
        with patch(
            "agent_memory.client.extract_memories", new_callable=AsyncMock
        ) as mock_extract:
            mock_extract.return_value = []
            result = await client.remember("hello", context)
            assert result == []
            mock_extract.assert_called_once()
            args = mock_extract.call_args
            # Check that a synthetic message was created
            messages_arg = args[1]["messages"] if "messages" in args[1] else args[0][0]
            assert len(messages_arg) == 1
            assert messages_arg[0]["role"] == "user"
            assert messages_arg[0]["content"] == "hello"

    @pytest.mark.asyncio
    async def test_remember_with_messages(self, client: MemoryClient, context: MemoryContext):
        """remember uses provided messages."""
        messages = [{"id": "m1", "role": "user", "content": "test"}]
        with patch(
            "agent_memory.client.extract_memories", new_callable=AsyncMock
        ) as mock_extract:
            mock_extract.return_value = []
            result = await client.remember("ignored", context, messages=messages)
            assert result == []
            mock_extract.assert_called_once()
            args = mock_extract.call_args
            messages_arg = args[1]["messages"] if "messages" in args[1] else args[0][0]
            assert len(messages_arg) == 1

    @pytest.mark.asyncio
    async def test_retrieve(self, client: MemoryClient, context: MemoryContext):
        """retrieve calls the retrieve pipeline."""
        from agent_memory.domain.retrieval import RetrievalResult

        mock_result = RetrievalResult(
            query="test",
            results=[],
            total_count=0,
            token_count=0,
            token_budget=1200,
        )
        with patch("agent_memory.client.retrieve", new_callable=AsyncMock, return_value=mock_result):
            result = await client.retrieve("test", context)
            assert result.query == "test"

    @pytest.mark.asyncio
    async def test_grant_consent(self, client: MemoryClient, context: MemoryContext):
        """grant_consent calls the consent provider."""
        from agent_memory.domain.consent import ConsentRecord
        from uuid import uuid4

        mock_record = ConsentRecord(
            id=uuid4(),
            tenant_id="default",
            subject_id="s1",
            actor_id="s1",
            purpose="general",
            allow_read=True,
            allow_write=False,
            allowed_memory_types={"preference"},
            allowed_sensitivity={"public"},
        )
        client._consent.grant_consent = AsyncMock(return_value=mock_record)
        result = await client.grant_consent("s1", ["preference"])
        assert result.tenant_id == "default"
        client._consent.grant_consent.assert_called_once()

    @pytest.mark.asyncio
    async def test_revoke_consent(self, client: MemoryClient, context: MemoryContext):
        """revoke_consent revokes all active consent."""
        from agent_memory.domain.consent import ConsentRecord
        from uuid import uuid4

        mock_record = ConsentRecord(
            id=uuid4(),
            tenant_id="default",
            subject_id="s1",
            actor_id="s1",
            purpose="general",
            allow_read=True,
            allow_write=False,
            allowed_memory_types={"preference"},
            allowed_sensitivity={"public"},
        )
        client._consent.list_consent = AsyncMock(return_value=[mock_record])
        client._consent.revoke_consent = AsyncMock(return_value=mock_record)
        result = await client.revoke_consent("s1")
        assert result.tenant_id == "default"

    @pytest.mark.asyncio
    async def test_check_consent(self, client: MemoryClient, context: MemoryContext):
        """check_consent returns True when consent exists."""
        from agent_memory.domain.consent import ConsentRecord
        from uuid import uuid4

        mock_record = ConsentRecord(
            id=uuid4(),
            tenant_id="default",
            subject_id="s1",
            actor_id="s1",
            purpose="general",
            allow_read=True,
            allow_write=False,
            allowed_memory_types={"preference"},
            allowed_sensitivity={"public"},
        )
        client._consent.get_active_consent = AsyncMock(return_value=mock_record)
        result = await client.check_consent("s1", "preference", "public")
        assert result is True

    @pytest.mark.asyncio
    async def test_check_consent_no_provider(self, client: MemoryClient, context: MemoryContext):
        """check_consent returns False when consent provider is None."""
        client._consent = None
        result = await client.check_consent("s1", "preference", "public")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_stats(self, client: MemoryClient, context: MemoryContext):
        """get_stats returns memory counts."""
        client._backend.list_memories = AsyncMock(return_value=[])
        result = await client.get_stats(context)
        assert result["total_memories"] == 0
        assert result["by_type"] == {}