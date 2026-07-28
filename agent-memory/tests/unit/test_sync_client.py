"""Unit tests for the SyncMemoryClient (src/agent_memory/sync_client.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_memory.sync_client import SyncMemoryClient
from agent_memory.context import MemoryContext


class TestSyncMemoryClient:
    """Tests for the synchronous SyncMemoryClient."""

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
    ) -> SyncMemoryClient:
        return SyncMemoryClient(mock_backend, mock_extractor, mock_embedder, mock_consent)

    def test_enter_exits(self, client: SyncMemoryClient):
        """Context manager enters and exits."""
        with client:
            pass  # Should not raise

    def test_remember(self, client: SyncMemoryClient, context: MemoryContext):
        """remember delegates to async client."""
        with patch(
            "agent_memory.sync_client.MemoryClient.remember", new_callable=AsyncMock
        ) as mock_remember:
            mock_remember.return_value = []
            result = client.remember("hello", context)
            assert result == []

    def test_retrieve(self, client: SyncMemoryClient, context: MemoryContext):
        """retrieve delegates to async client."""
        from agent_memory.domain.retrieval import RetrievalResult

        mock_result = RetrievalResult(
            query="test",
            results=[],
            total_count=0,
            token_count=0,
            token_budget=1200,
        )
        with patch(
            "agent_memory.sync_client.MemoryClient.retrieve", new_callable=AsyncMock
        ) as mock_retrieve:
            mock_retrieve.return_value = mock_result
            result = client.retrieve("test", context)
            assert result.query == "test"

    def test_grant_consent(self, client: SyncMemoryClient):
        """grant_consent delegates to async client."""
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
        with patch(
            "agent_memory.sync_client.MemoryClient.grant_consent", new_callable=AsyncMock
        ) as mock_grant:
            mock_grant.return_value = mock_record
            result = client.grant_consent("s1", ["preference"])
            assert result.tenant_id == "default"

    def test_revoke_consent(self, client: SyncMemoryClient):
        """revoke_consent delegates to async client."""
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
        with patch(
            "agent_memory.sync_client.MemoryClient.revoke_consent", new_callable=AsyncMock
        ) as mock_revoke:
            mock_revoke.return_value = mock_record
            result = client.revoke_consent("s1")
            assert result.tenant_id == "default"

    def test_check_consent(self, client: SyncMemoryClient):
        """check_consent delegates to async client."""
        with patch(
            "agent_memory.sync_client.MemoryClient.check_consent", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = True
            result = client.check_consent("s1", "preference", "public")
            assert result is True

    def test_get_stats(self, client: SyncMemoryClient, context: MemoryContext):
        """get_stats delegates to async client."""
        with patch(
            "agent_memory.sync_client.MemoryClient.get_stats", new_callable=AsyncMock
        ) as mock_stats:
            mock_stats.return_value = {"total_memories": 5, "by_type": {"preference": 5}}
            result = client.get_stats(context)
            assert result["total_memories"] == 5