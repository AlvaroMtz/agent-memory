"""Unit tests for deterministic providers."""

import pytest

from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.providers.deterministic_embeddings import DeterministicEmbeddingProvider
from agent_memory.providers.fake_extractor import FakeExtractor
from agent_memory.providers.rule_based_extractor import RuleBasedExtractor


class TestDeterministicEmbeddingProvider:
    """Test deterministic embedding provider."""

    async def test_same_text_same_vector(self):
        provider = DeterministicEmbeddingProvider(dimensions=128)
        v1 = await provider.embed("Hello world")
        v2 = await provider.embed("Hello world")
        assert v1 == v2

    async def test_different_text_different_vector(self):
        provider = DeterministicEmbeddingProvider(dimensions=128)
        v1 = await provider.embed("Hello world")
        v2 = await provider.embed("Goodbye world")
        assert v1 != v2

    async def test_dimensions_match(self):
        provider = DeterministicEmbeddingProvider(dimensions=64)
        vec = await provider.embed("test")
        assert len(vec) == 64

    async def test_embed_many(self):
        provider = DeterministicEmbeddingProvider(dimensions=128)
        vectors = await provider.embed_many(["a", "b", "c"])
        assert len(vectors) == 3
        assert all(len(v) == 128 for v in vectors)

    async def test_unit_vector_magnitude(self):
        provider = DeterministicEmbeddingProvider(dimensions=128)
        vec = await provider.embed("A longer test text for embedding")
        magnitude = sum(v * v for v in vec) ** 0.5
        assert abs(magnitude - 1.0) < 0.01

    async def test_empty_text(self):
        provider = DeterministicEmbeddingProvider(dimensions=128)
        vec = await provider.embed("")
        magnitude = sum(v * v for v in vec) ** 0.5
        assert magnitude == 0.0


class TestFakeExtractor:
    """Test fake extractor."""

    async def test_returns_empty_by_default(self):
        extractor = FakeExtractor()
        results = await extractor.extract(messages=[{"role": "user", "content": "Hello"}], subject_id="user-1")
        assert results == []

    async def test_returns_configured_response(self):
        candidates = [
            MemoryCandidate(
                memory_type="preference", subject_key="code",
                predicate="code_language", value="Python",
                source_message_id="msg-1", evidence_text="Python",
            ),
        ]
        extractor = FakeExtractor(responses={"Hello": candidates})
        results = await extractor.extract(
            messages=[{"role": "user", "content": "Hello", "id": "msg-1"}],
            subject_id="user-1",
        )
        assert len(results) == 1
        assert results[0].value == "Python"

    async def test_set_response_after_creation(self):
        extractor = FakeExtractor()
        candidates = [
            MemoryCandidate(
                memory_type="preference", subject_key="code",
                predicate="code_language", value="Rust",
                source_message_id="msg-1", evidence_text="Rust",
            ),
        ]
        extractor.set_response("Hello", candidates)
        results = await extractor.extract(
            messages=[{"role": "user", "content": "Hello", "id": "msg-1"}],
            subject_id="user-1",
        )
        assert len(results) == 1
        assert results[0].value == "Rust"


class TestRuleBasedExtractor:
    """Test rule-based extractor."""

    async def test_extract_preference_prefiero(self):
        extractor = RuleBasedExtractor()
        results = await extractor.extract(
            messages=[{"role": "user", "content": "Prefiero que los ejemplos sean en TypeScript.", "id": "msg-1"}],
            subject_id="user-1",
        )
        assert len(results) >= 1
        # Should match "response_language" or "code_language"
        predicates = {r.predicate for r in results}
        assert len(predicates) > 0

    async def test_extract_code_language(self):
        extractor = RuleBasedExtractor()
        results = await extractor.extract(
            messages=[{"role": "user", "content": "Mi lenguaje favorito es Python.", "id": "msg-1"}],
            subject_id="user-1",
        )
        assert len(results) == 1
        assert results[0].predicate == "code_language"
        assert results[0].value == "Python"

    async def test_ignores_assistant_messages(self):
        extractor = RuleBasedExtractor()
        results = await extractor.extract(
            messages=[
                {"role": "user", "content": "Prefiero Python.", "id": "msg-1"},
                {"role": "assistant", "content": "Python es un buen lenguaje.", "id": "msg-2"},
            ],
            subject_id="user-1",
        )
        # Only user messages should be extracted
        assert len(results) == 1
        assert results[0].source_role == "user"

    async def test_empty_messages(self):
        extractor = RuleBasedExtractor()
        results = await extractor.extract(messages=[], subject_id="user-1")
        assert results == []

    async def test_no_match(self):
        extractor = RuleBasedExtractor()
        results = await extractor.extract(
            messages=[{"role": "user", "content": "¿Cómo está el clima hoy?", "id": "msg-1"}],
            subject_id="user-1",
        )
        assert results == []

    async def test_trusted_tool_is_extracted(self):
        extractor = RuleBasedExtractor()
        results = await extractor.extract(
            messages=[{"role": "trusted_tool", "content": "Prefiero TypeScript.", "id": "msg-1"}],
            subject_id="user-1",
        )
        assert len(results) == 1