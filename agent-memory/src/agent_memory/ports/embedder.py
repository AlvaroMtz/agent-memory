"""EmbeddingProvider port — abstract interface for generating text embeddings."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Port for generating text embeddings.

    Implementations:
    - DeterministicEmbeddingProvider: stable hash-based embeddings for tests
    - (future) OpenAIEmbeddingProvider: OpenAI API-based embeddings
    - (future) SentenceTransformerEmbeddingProvider: local model
    """

    @property
    def dimensions(self) -> int:
        """Number of dimensions in the embedding vectors."""
        ...

    async def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for a single text."""
        ...

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for multiple texts."""
        ...


class EmbeddingProviderFactory(Protocol):
    """Factory for creating EmbeddingProvider instances."""

    def create(self, **kwargs) -> EmbeddingProvider:
        """Create an EmbeddingProvider instance."""
        ...