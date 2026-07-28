"""Unit tests for the SyncMemoryClient (src/agent_memory/sync_client.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_memory.sync_client import SyncMemoryClient
from agent_memory.context import MemoryContext


class TestSyncMemoryClient:
    """Tests for the synchronous SyncMemoryClient facade."""

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
    ) -> SyncMemoryClient:
        return SyncMemoryClient(mock_backend, mock_extractor, mock_embedder, mock_consent)

    def test_init_with_backend(self, mock_backend: MagicMock):
        """Client initializes backend on __enter__."""
        with SyncMemoryClient(mock_backend) as client:
            mock_backend.initialize.assert_called_once()

    def test_remember_no_consent_returns_empty(self, client: SyncMemoryClient, context: MemoryContext):
        """remember returns empty result when no consent is granted."""
        client._client._consent.get_active_consent = AsyncMock(return_value=None)
        result = client.remember(
            context=context,
            messages=[{"id": "m1", "role": "user", "content": "hello"}],
        )
        assert result.count == 0
        assert result.empty

    def test_remember_with_consent(self, client: SyncMemoryClient, context: MemoryContext):
        """remember persists candidates when consent is active."""
        from agent_memory.domain.consent import ConsentRecord
        from agent_memory.domain.candidate import MemoryCandidate
        from uuid import uuid4

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
        client._client._consent.get_active_consent = AsyncMock(return_value=mock_record)
        client._client._extractor = MagicMock()
        client._client._extractor.extract = AsyncMock(
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

        result = client.remember(
            context=context,
            messages=[{"id": "m1", "role": "user", "content": "VS Code"}],
        )
        assert result.count == 1
        assert result.audit_id is not None
        client._client._backend.save_memory.assert_called_once()

    def test_retrieve(self, client: SyncMemoryClient, context: MemoryContext):
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
            result = client.retrieve("test", context)
            assert result.query == "test"

    def test_grant_consent(self, client: SyncMemoryClient, context: MemoryContext):
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
        client._client._consent.grant_consent = AsyncMock(return_value=mock_record)

        result = client.grant_consent(context, memory_types=["preference"])
        assert result.tenant_id == "t1"
        assert result.purpose == "test"

    def test_revoke_consent(self, client: SyncMemoryClient, context: MemoryContext):
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
        client._client._consent.list_consent = AsyncMock(return_value=[mock_record])
        client._client._consent.revoke_consent = AsyncMock(return_value=mock_record)

        result = client.revoke_consent("s1", context)
        assert result.tenant_id == "t1"

    def test_check_consent(self, client: SyncMemoryClient, context: MemoryContext):
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
        client._client._consent.get_active_consent = AsyncMock(return_value=mock_record)

        result = client.check_consent("s1", "preference", "public", context)
        assert result is True

    def test_get_stats(self, client: SyncMemoryClient, context: MemoryContext):
        """get_stats returns memory counts."""
        client._client._backend.list_memories = AsyncMock(return_value=[])
        result = client.get_stats(context)
        assert result["total_memories"] == 0
        assert result["by_type"] == {}