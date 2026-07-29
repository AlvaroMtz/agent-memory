"""Deterministic embedding provider for tests.

Produces stable, reproducible embeddings without external APIs.
Uses a hash-based approach: same text → same vector.
"""

from __future__ import annotations

import hashlib


class DeterministicEmbeddingProvider:
    """Embedding provider that produces deterministic vectors.

    Uses token-level hashing to create stable embeddings.
    NOT suitable for production — for testing and demos only.
    """

    def __init__(self, dimensions: int = 128) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, text: str) -> list[float]:
        """Generate a deterministic embedding vector for the given text."""
        return self._hash_to_vector(text)

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Generate deterministic embedding vectors for multiple texts."""
        return [self._hash_to_vector(t) for t in texts]

    def _hash_to_vector(self, text: str) -> list[float]:
        """Convert text to a deterministic float vector via hashing."""
        vec = [0.0] * self._dimensions
        tokens = text.lower().split()

        for i, token in enumerate(tokens):
            h = hashlib.sha256(token.encode()).digest()
            for j in range(self._dimensions):
                # Use each byte of the hash to influence a different dimension
                byte_val = h[j % len(h)]
                # Normalize to [-1.0 / len(tokens), 1.0 / len(tokens)]
                vec[j] += (byte_val - 127.5) / 127.5

        # Normalize by token count
        if tokens:
            vec = [v / len(tokens) for v in vec]

        # Normalize to unit vector
        magnitude = sum(v * v for v in vec) ** 0.5
        if magnitude > 0:
            vec = [v / magnitude for v in vec]

        return vec


class DeterministicEmbeddingFactory:
    """Factory for DeterministicEmbeddingProvider."""

    def create(self, dimensions: int = 128) -> DeterministicEmbeddingProvider:
        return DeterministicEmbeddingProvider(dimensions=dimensions)
