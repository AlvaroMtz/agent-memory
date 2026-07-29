"""Contract tests for EmbeddingProvider.

Reusable test suite that any embedding provider must pass.
"""

from __future__ import annotations

import pytest

from agent_memory.ports.embedder import EmbeddingProvider


class EmbedderContractSuite:
    """Contract test suite for EmbeddingProvider implementations.

    Usage:
        class TestMyEmbedder:
            @pytest.fixture
            def embedder(self):
                return MyEmbedder()

            def test_contract(self, embedder):
                EmbedderContractSuite().run_all(embedder)
    """

    async def run_all(self, embedder: EmbeddingProvider) -> None:
        """Run all contract tests."""
        await self._test_embed_text_returns_list(embedder)
        await self._test_embed_text_consistent_dimensions(embedder)
        await self._test_consistent_output(embedder)
        await self._test_different_texts_different_vectors(embedder)

    async def _test_embed_text_returns_list(self, embedder: EmbeddingProvider) -> None:
        """embed must return a list of floats."""
        result = await embedder.embed("test text")
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(v, float) for v in result)

    async def _test_embed_text_consistent_dimensions(self, embedder: EmbeddingProvider) -> None:
        """All embeddings must have the same dimensions."""
        v1 = await embedder.embed("hello")
        v2 = await embedder.embed("world")
        assert len(v1) == len(v2)

    async def _test_consistent_output(self, embedder: EmbeddingProvider) -> None:
        """Same input must produce same output (deterministic)."""
        v1 = await embedder.embed("consistent test")
        v2 = await embedder.embed("consistent test")
        assert v1 == v2

    async def _test_different_texts_different_vectors(self, embedder: EmbeddingProvider) -> None:
        """Different inputs should produce different vectors."""
        v1 = await embedder.embed("hello world")
        v2 = await embedder.embed("goodbye world")
        assert v1 != v2


class TestDeterministicEmbedderContract:
    """Run the contract suite against DeterministicEmbeddingProvider."""

    @pytest.fixture
    def embedder(self):
        from agent_memory.providers.deterministic_embeddings import DeterministicEmbeddingProvider

        return DeterministicEmbeddingProvider(dimensions=4)

    @pytest.mark.asyncio
    async def test_contract_suite(self, embedder):
        await EmbedderContractSuite().run_all(embedder)
