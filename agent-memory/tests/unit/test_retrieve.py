"""Unit tests for the retrieval pipeline (retrieve.py)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from agent_memory.application.retrieve import (
    apply_consent_filter,
    apply_token_budget,
    retrieve,
    score_fusion,
    _empty_result,
)
from agent_memory.constants import MemoryStatus
from agent_memory.context import TenantContext
from agent_memory.domain.consent import ConsentRecord
from agent_memory.domain.memory import MemoryRecord, MemoryVersion
from agent_memory.domain.retrieval import RetrievedMemory, RetrievalResult
from agent_memory.ports.consent import ConsentProvider
from agent_memory.providers.deterministic_embeddings import DeterministicEmbeddingProvider
from agent_memory.providers.in_memory_backend import InMemoryBackend


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _save_test_memory(
    backend: InMemoryBackend,
    *,
    tenant_id: str = "t1",
    subject_id: str = "sub-1",
    memory_type: str = "preference",
    subject_key: str = "k",
    predicate: str = "likes",
    value: object = "test-value",
    confidence: float = 0.9,
) -> MemoryRecord:
    record = MemoryRecord(
        tenant_id=tenant_id,
        subject_id=subject_id,
        purpose="test",
        memory_type=memory_type,
        subject_key=subject_key,
        predicate=predicate,
        status="active",
        current_version=1,
    )
    version = MemoryVersion(
        memory_id=record.id,
        version=1,
        value=value,
        confidence=confidence,
        sensitivity="public",
        source_type="user_explicit",
    )
    context = TenantContext(tenant_id=tenant_id)
    await backend.save_memory(record, version, context=context)
    return record


async def _grant_read_consent(
    backend: InMemoryBackend,
    *,
    tenant_id: str = "t1",
    subject_id: str = "sub-1",
    purpose: str = "test",
) -> None:
    await backend.save_consent(
        ConsentRecord(
            tenant_id=tenant_id,
            subject_id=subject_id,
            actor_id="tester",
            purpose=purpose,
            allow_write=True,
            allow_read=True,
            allowed_memory_types={"preference", "semantic"},
            allowed_sensitivity={"public", "internal"},
        ),
        context=TenantContext(tenant_id=tenant_id, actor_id="tester"),
    )


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def backend() -> InMemoryBackend:
    return InMemoryBackend()


@pytest.fixture
def embedder() -> DeterministicEmbeddingProvider:
    return DeterministicEmbeddingProvider(dimensions=4)


@pytest.fixture
def sample_memories() -> list[RetrievedMemory]:
    now = datetime.now(timezone.utc)
    return [
        RetrievedMemory(
            id=uuid.uuid4(),
            version=1,
            memory_type="preference",
            predicate="likes",
            value="coffee",
            score=0.0,
            score_breakdown={"vector": 0.8, "lexical": 0.0, "recency": 0.1, "confidence": 0.0},
            confidence=0.9,
            source_type="user",
            sensitivity="public",
            created_at=now,
        ),
        RetrievedMemory(
            id=uuid.uuid4(),
            version=1,
            memory_type="semantic",
            predicate="works_at",
            value="ACME",
            score=0.0,
            score_breakdown={"vector": 0.0, "lexical": 0.6, "recency": 0.0, "confidence": 0.1},
            confidence=0.8,
            source_type="user",
            sensitivity="internal",
            created_at=now,
        ),
        RetrievedMemory(
            id=uuid.uuid4(),
            version=1,
            memory_type="preference",
            predicate="likes",
            value="tea",
            score=0.0,
            score_breakdown={"vector": 0.3, "lexical": 0.0, "recency": 0.1, "confidence": 0.1},
            confidence=0.7,
            source_type="user",
            sensitivity="public",
            created_at=now,
        ),
    ]


class StubConsentProvider:
    """ConsentProvider stub that allows/denies based on subject_id."""

    def __init__(self, allowed_subjects: set[str] | None = None):
        self.allowed_subjects = allowed_subjects or set()

    def check_read_access(
        self,
        tenant_id: str,
        subject_id: str,
        memory_type: str | None = None,
        sensitivity: str | None = None,
    ) -> bool:
        return subject_id in self.allowed_subjects


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestRetrieve:
    """Tests for the top-level retrieve() function."""

    async def test_retrieve_empty_no_backend(self):
        """No backend → empty result."""
        result = await retrieve(tenant_id="t1")
        assert isinstance(result, RetrievalResult)
        assert result.empty

    async def test_retrieve_with_backend_empty(self, backend: InMemoryBackend):
        """Empty backend → empty result."""
        await backend.initialize()
        result = await retrieve(tenant_id="t1", backend=backend)
        assert result.empty
        assert result.total_count == 0

    async def test_retrieve_returns_results(self, backend: InMemoryBackend):
        """Backend with memories → non-empty result."""
        await backend.initialize()
        await _save_test_memory(backend)
        await _grant_read_consent(backend)
        result = await retrieve(
            tenant_id="t1",
            subject_id="sub-1",
            backend=backend,
            consent=backend,
            filters={"purpose": "test"},
        )
        assert not result.empty
        assert result.total_count >= 1

    async def test_retrieve_filters_by_memory_type(self, backend: InMemoryBackend):
        """Filter by memory_type → only matching types."""
        await backend.initialize()
        await _save_test_memory(backend, memory_type="preference", value="x")
        await _save_test_memory(backend, memory_type="semantic", value="y")
        result = await retrieve(
            tenant_id="t1", subject_id="sub-1", backend=backend,
            filters={"memory_types": ["semantic"]},
        )
        for r in result.results:
            assert r.memory_type == "semantic"

    async def test_retrieve_with_embedding(self, backend: InMemoryBackend, embedder: DeterministicEmbeddingProvider):
        """Vector search path does not error."""
        await backend.initialize()
        await _save_test_memory(backend, value="hello")
        result = await retrieve(
            tenant_id="t1", subject_id="sub-1", query="hello",
            backend=backend, embedder=embedder,
        )
        assert isinstance(result, RetrievalResult)


class TestScoreFusion:
    """Tests for score_fusion()."""

    def test_fusion_uses_score_breakdown(self, sample_memories: list[RetrievedMemory]):
        """Score matches ScoreBreakdown.total weights."""
        fused = score_fusion(sample_memories)
        for r in fused:
            bd = r.score_breakdown or {}
            expected = (
                bd.get("vector", 0.0) * 0.4
                + bd.get("lexical", 0.0) * 0.3
                + bd.get("recency", 0.0) * 0.15
                + bd.get("confidence", 0.0) * 0.15
            )
            assert abs(r.score - expected) < 1e-9

    def test_fusion_all_results_preserved(self, sample_memories: list[RetrievedMemory]):
        """Number of results preserved."""
        fused = score_fusion(sample_memories)
        assert len(fused) == len(sample_memories)

    def test_fusion_empty_list(self):
        """Empty input → empty output."""
        assert score_fusion([]) == []

    def test_fusion_missing_breakdown(self):
        """Missing breakdown filled with zeros."""
        r = RetrievedMemory(
            id=uuid.uuid4(), version=1, memory_type="preference",
            predicate="likes", value="v", score=0.5,
            score_breakdown={}, confidence=0.9,
            source_type="user", sensitivity="public",
            created_at=datetime.now(timezone.utc),
        )
        fused = score_fusion([r])
        assert fused[0].score == 0.0


class TestApplyConsentFilter:
    """Tests for apply_consent_filter()."""

    def test_all_allowed(self, sample_memories: list[RetrievedMemory]):
        """All subjects allowed → all results pass."""
        consent = StubConsentProvider(allowed_subjects={"sub-1"})
        filtered = apply_consent_filter(sample_memories, consent, "t1", "sub-1")
        assert len(filtered) == len(sample_memories)

    def test_none_allowed(self, sample_memories: list[RetrievedMemory]):
        """No subjects allowed → empty results."""
        consent = StubConsentProvider(allowed_subjects=set())
        filtered = apply_consent_filter(sample_memories, consent, "t1", "sub-1")
        assert filtered == []


class TestApplyTokenBudget:
    """Tests for apply_token_budget()."""

    def test_budget_allows_all(self, sample_memories: list[RetrievedMemory]):
        """Large budget → all results pass."""
        truncated = apply_token_budget(sample_memories, max_tokens=10_000)
        assert len(truncated) == len(sample_memories)

    def test_budget_truncates(self):
        """Small budget truncates results (50 tokens per result)."""
        now = datetime.now(timezone.utc)
        results = [
            RetrievedMemory(
                id=uuid.uuid4(), version=1, memory_type="preference",
                predicate="a", value="a", score=1.0,
                score_breakdown={}, confidence=0.9,
                source_type="user", sensitivity="public",
                created_at=now,
            ) for _ in range(5)
        ]
        truncated = apply_token_budget(results, max_tokens=100)
        assert len(truncated) == 2

    def test_empty_list(self):
        """Empty input → empty output."""
        assert apply_token_budget([], max_tokens=100) == []


class TestEmptyResult:
    """Tests for _empty_result()."""

    def test_empty_result_structure(self):
        """Empty result has correct shape."""
        r = _empty_result("test-query")
        assert isinstance(r, RetrievalResult)
        assert r.query == "test-query"
        assert r.results == []
        assert r.total_count == 0
        assert r.token_count == 0
        assert r.token_budget == 1200
        assert r.empty
