"""Built-in deterministic/demo providers and plugin factories."""

from __future__ import annotations

from typing import Any

from agent_memory.providers.deterministic_embeddings import (
    DeterministicEmbeddingFactory,
    DeterministicEmbeddingProvider,
)
from agent_memory.providers.fake_extractor import FakeExtractor, FakeExtractorFactory
from agent_memory.providers.in_memory_backend import InMemoryBackend, InMemoryBackendFactory
from agent_memory.providers.rule_based_extractor import (
    RuleBasedExtractor,
    RuleBasedExtractorFactory,
)


class LangChainExtractorFactory:
    """Factory placeholder for the optional LangChain structured extractor.

    The entry point must be importable even when the optional ``langchain`` extra
    is absent. Creation fails with a precise dependency message instead of an
    import-time crash.
    """

    def create(self, *args: Any, **kwargs: Any) -> Any:
        try:
            from agent_memory.providers.langchain_extractor import LangChainStructuredExtractor
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "LangChainStructuredExtractor requires installing 'agent-memory[langchain]'"
            ) from exc
        return LangChainStructuredExtractor(*args, **kwargs)


__all__ = [
    "DeterministicEmbeddingFactory",
    "DeterministicEmbeddingProvider",
    "FakeExtractor",
    "FakeExtractorFactory",
    "InMemoryBackend",
    "InMemoryBackendFactory",
    "LangChainExtractorFactory",
    "RuleBasedExtractor",
    "RuleBasedExtractorFactory",
]
