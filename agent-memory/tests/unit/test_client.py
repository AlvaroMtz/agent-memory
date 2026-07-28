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
        from agent_memory.domain.memory import MemoryRecord
        backend.save_memory = AsyncMock(
            return_value=MemoryRecord(tenant_id="t", subject_id="s", purpose="p", memory_type="preference", subject_key="k", predicate="p")
        )
        backend.audit = AsyncMock()
        return backend

    @pytest.fixture
    def mock_extractor(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mock_embedder(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mock_consent(self) -> MagicMock:
        consent = MagicMock()
        consent.get_active_consent = AsyncMock(return_value=None)
        return consent

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
    async def test_remember_no_consent_returns_empty(self, client: MemoryClient, context: MemoryContext):
        """remember returns empty result when no consent is granted."""
        # Mock: no active consent
        client._consent.get_active_consent = AsyncMock(return_value=None)
        result = await client.remember(
            context=context,
            messages=[{"id": "m1", "role": "user", "content": "hello"}],
        )
        assert result.count == 0
        assert result.empty

    @pytest.mark.asyncio
    async def test_remember_with_consent(self, client: MemoryClient, context: MemoryContext):
        """remember persists candidates when consent is active."""
        from agent_memory.domain.consent import ConsentRecord
        from uuid import uuid4

        # Mock active consent
        mock_record = ConsentRecord(
            id=uuid4(),
            tenant_id="t1",
            subject_id="s1",
            actor_id="a1",
            purpose="test",
            allow_read=True,
            allow_write=True,
            allowed_memory_types={"preference"},
            allowed_sensitivity={"public"},
        )
        client._consent.get_active_consent = AsyncMock(return_value=mock_record)

        # Mock extractor to return a candidate
        from agent_memory.domain.candidate import MemoryCandidate
        client._extractor = MagicMock()
        client._extractor.extract = AsyncMock(
            return_value=[
                MemoryCandidate(
                    memory_type="preference",
                    subject_key="code",
                    predicate="code_language",
                    value="TypeScript",
                    source_message_id="m1",
                    evidence_text="TypeScript",
                    source_role="user",
                    confidence=0.9,
                )
            ]
        )

        result = await client.remember(
            context=context,
            messages=[{"id": "m1", "role": "user", "content": "TypeScript"}],
        )
        assert result.count == 1
        assert len(result.memories) == 1
        assert len(result.versions) == 1
        assert result.audit_id is not None
        assert result.purpose == "test"
        assert result.tenant_id == "t1"
        assert result.subject_id == "s1"
        client._backend.save_memory.assert_called_once()
        client._backend.audit.assert_called_once()

    @pytest.mark.asyncio
    async def test_remember_no_consent_provider(self, client: MemoryClient, context: MemoryContext):
        """remember fails closed if consent provider is not configured."""
        client._consent = None

        from agent_memory.domain.candidate import MemoryCandidate
        client._extractor = MagicMock()
        client._extractor.extract = AsyncMock(
            return_value=[
                MemoryCandidate(
                    memory_type="preference",
                    subject_key="code",
                    predicate="editor",
                    value="VS Code",
                    source_message_id="m1",
                    evidence_text="VS Code",
                    source_role="user",
                    confidence=0.9,
                )
            ]
        )

        result = await client.remember(
            context=context,
            messages=[{"id": "m1", "role": "user", "content": "VS Code"}],
        )
        assert result.count == 0
        assert result.empty
        client._backend.save_memory.assert_not_called()

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
        """grant_consent uses context for tenant_id and purpose."""
        from agent_memory.domain.consent import ConsentRecord
        from uuid import uuid4

        mock_record = ConsentRecord(
            id=uuid4(),
            tenant_id="t1",
            subject_id="s1",
            actor_id="a1",
            purpose="test",
            allow_read=True,
            allow_write=False,
            allowed_memory_types={"preference"},
            allowed_sensitivity={"public"},
        )
        client._consent.grant_consent = AsyncMock(return_value=mock_record)

        result = await client.grant_consent(
            context,
            memory_types=["preference"],
        )
        assert result.tenant_id == "t1"
        assert result.purpose == "test"
        client._consent.grant_consent.assert_called_once()
        # Verify the grant had the correct purpose
        call_grant = client._consent.grant_consent.call_args[0][0]
        assert call_grant.purpose == "test"

    @pytest.mark.asyncio
    async def test_revoke_consent(self, client: MemoryClient, context: MemoryContext):
        """revoke_consent uses context tenant_id."""
        from agent_memory.domain.consent import ConsentRecord
        from uuid import uuid4

        mock_record = ConsentRecord(
            id=uuid4(),
            tenant_id="t1",
            subject_id="s1",
            actor_id="a1",
            purpose="test",
            allow_read=True,
            allow_write=False,
            allowed_memory_types={"preference"},
            allowed_sensitivity={"public"},
        )
        client._consent.list_consent = AsyncMock(return_value=[mock_record])
        client._consent.revoke_consent = AsyncMock(return_value=mock_record)

        result = await client.revoke_consent("s1", context)
        assert result.tenant_id == "t1"
        # Verify context was passed
        call_ctx = client._consent.revoke_consent.call_args[1]["context"]
        assert call_ctx.tenant_id == "t1"

    @pytest.mark.asyncio
    async def test_check_consent(self, client: MemoryClient, context: MemoryContext):
        """check_consent uses context for tenant_id and purpose."""
        from agent_memory.domain.consent import ConsentRecord
        from uuid import uuid4

        mock_record = ConsentRecord(
            id=uuid4(),
            tenant_id="t1",
            subject_id="s1",
            actor_id="a1",
            purpose="test",
            allow_read=True,
            allow_write=False,
            allowed_memory_types={"preference"},
            allowed_sensitivity={"public"},
        )
        client._consent.get_active_consent = AsyncMock(return_value=mock_record)

        result = await client.check_consent("s1", "preference", "public", context)
        assert result is True
        # Verify correct tenant/purpose were used
        call_kwargs = client._consent.get_active_consent.call_args[1]
        assert call_kwargs["tenant_id"] == "t1"
        assert call_kwargs["purpose"] == "test"

    @pytest.mark.asyncio
    async def test_check_consent_no_provider(self, client: MemoryClient, context: MemoryContext):
        """check_consent returns False when consent provider is None."""
        client._consent = None
        result = await client.check_consent("s1", "preference", "public", context)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_stats(self, client: MemoryClient, context: MemoryContext):
        """get_stats returns memory counts."""
        client._backend.list_memories = AsyncMock(return_value=[])
        result = await client.get_stats(context)
        assert result["total_memories"] == 0
        assert result["by_type"] == {}

    @pytest.mark.asyncio
    async def test_list_memories(self, client: MemoryClient, context: MemoryContext):
        """list_memories delegates to backend."""
        client._backend.list_memories = AsyncMock(return_value=[])
        result = await client.list_memories(context, memory_type="preference")
        assert result == []
        client._backend.list_memories.assert_called_once()

    @pytest.mark.asyncio
    async def test_forget(self, client: MemoryClient, context: MemoryContext):
        """forget updates memory status to deleted."""
        from uuid import uuid4

        memory_id = uuid4()
        client._backend.update_memory_status = AsyncMock()
        await client.forget(memory_id, context)
        call_kwargs = client._backend.update_memory_status.call_args[1]
        assert call_kwargs["memory_id"] == memory_id
        assert call_kwargs["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_remember_no_extractor_returns_empty(self, client: MemoryClient, context: MemoryContext):
        """remember returns empty when no extractor configured."""
        from agent_memory.domain.consent import ConsentRecord

        client._consent.get_active_consent = AsyncMock(
            return_value=ConsentRecord(
                tenant_id="t1",
                subject_id="s1",
                actor_id="a1",
                purpose="test",
                allow_read=True,
                allow_write=True,
                allowed_memory_types={"preference"},
                allowed_sensitivity={"public"},
            )
        )
        client._extractor = None

        result = await client.remember(
            context=context,
            messages=[{"id": "m1", "role": "user", "content": "hello"}],
        )
        assert result.count == 0
