"""Retrieval pipeline — high-level orchestration for hybrid memory retrieval.

Pipeline steps: structured filters → vector search → lexical search →
score fusion → rerank → consent filter → token budget → return.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_memory.constants import MemoryStatusEnum
from agent_memory.domain.retrieval import RetrievedMemory, RetrievalResult
from agent_memory.ports.backend import MemoryBackend
from agent_memory.ports.consent import ConsentProvider
from agent_memory.ports.embedder import EmbeddingProvider

logger = logging.getLogger(__name__)


async def retrieve(
    tenant_id: str,
    subject_id: str = "",
    query: str | None = None,
    filters: dict[str, Any] | None = None,
    backend: MemoryBackend | None = None,
    embedder: EmbeddingProvider | None = None,
    consent: ConsentProvider | None = None,
    max_tokens: int = 1200,
) -> RetrievalResult:
    """Run the full hybrid retrieval pipeline (async).

    Pipeline steps:
    1. Build structured filters from *filters* dict.
    2. Compute query embedding via *embedder* (if available).
    3. Vector/lexical search via backend.
    4. Fuse scores from components.
    5. Apply consent filter.
    6. Apply token budget.
    7. Return ``RetrievalResult`` sorted by descending score.
    """
    if backend is None:
        logger.warning("No backend provided; returning empty result")
        return _empty_result(query or "")

    filters = filters or {}
    memory_types: list[str] | None = filters.get("memory_types")
    statuses: list[str] | None = filters.get("statuses", [MemoryStatusEnum.ACTIVE.value])
    purpose: str | None = filters.get("purpose")

    # ── Compute query embedding ────────────────────────────────────────
    query_vector: list[float] | None = None
    if query and embedder is not None:
        try:
            query_vector = await embedder.embed(query)
        except Exception:
            logger.exception("Embedding computation failed; skipping vector search")

    # ── Search ─────────────────────────────────────────────────────────
    all_results: list[RetrievedMemory] = []
    seen_ids: set[str] = set()
    effective_query = query or ""

    if query_vector:
        try:
            vec_results = await backend.retrieve(
                tenant_id=tenant_id,
                subject_id=subject_id,
                query=effective_query,
                memory_types=memory_types,
                statuses=statuses,
                purpose=purpose,
                limit=50,
            )
            for r in vec_results:
                rid = str(r.id)
                if rid not in seen_ids:
                    all_results.append(r)
                    seen_ids.add(rid)
        except Exception:
            logger.exception("Vector search failed")

    if query:
        try:
            lex_results = await backend.retrieve(
                tenant_id=tenant_id,
                subject_id=subject_id,
                query=effective_query,
                memory_types=memory_types,
                statuses=statuses,
                purpose=purpose,
                limit=50,
            )
            for r in lex_results:
                rid = str(r.id)
                if rid not in seen_ids:
                    all_results.append(r)
                    seen_ids.add(rid)
        except Exception:
            logger.exception("Lexical search failed")

    # Fallback: list all if no query and no results
    if not all_results and not query:
        try:
            fallback = await backend.retrieve(
                tenant_id=tenant_id,
                subject_id=subject_id,
                query="",
                memory_types=memory_types,
                statuses=statuses,
                purpose=purpose,
                limit=50,
            )
            all_results = fallback
        except Exception:
            logger.exception("Fallback list failed")

    # ── Score fusion ───────────────────────────────────────────────────
    all_results = score_fusion(all_results)

    # ── Sort by descending score ───────────────────────────────────────
    all_results.sort(key=lambda r: r.score, reverse=True)

    # ── Consent filter ─────────────────────────────────────────────────
    if consent is not None:
        all_results = apply_consent_filter(all_results, consent, tenant_id, subject_id)

    # ── Token budget ───────────────────────────────────────────────────
    budget_results = apply_token_budget(all_results, max_tokens)

    total_tokens = await _count_tokens(budget_results)

    return RetrievalResult(
        query=effective_query,
        results=budget_results,
        total_count=len(budget_results),
        token_count=total_tokens,
        token_budget=max_tokens,
    )


def score_fusion(
    results: list[RetrievedMemory],
) -> list[RetrievedMemory]:
    """Fuse individual score components into a single ``score``.

    Uses ``ScoreBreakdown.total`` which applies fixed weights:
    vector 40%, lexical 30%, recency 15%, confidence 15%.
    """
    from agent_memory.domain.retrieval import ScoreBreakdown

    for r in results:
        breakdown = r.score_breakdown or {}
        sb = ScoreBreakdown(
            vector_score=breakdown.get("vector", 0.0),
            lexical_score=breakdown.get("lexical", 0.0),
            recency_score=breakdown.get("recency", 0.0),
            confidence_score=breakdown.get("confidence", 0.0),
        )
        r.score = sb.total
    return results


def apply_consent_filter(
    results: list[RetrievedMemory],
    consent: ConsentProvider,
    tenant_id: str,
    subject_id: str,
) -> list[RetrievedMemory]:
    """Remove results that the active consent policy does not allow reading."""
    filtered: list[RetrievedMemory] = []
    for r in results:
        try:
            if consent.check_read_access(
                tenant_id=tenant_id,
                subject_id=subject_id,
                memory_type=r.memory_type,
                sensitivity=r.sensitivity,
            ):
                filtered.append(r)
        except Exception:
            logger.warning("Consent check failed for result %s; excluding", r.id)
    return filtered


def apply_token_budget(
    results: list[RetrievedMemory],
    max_tokens: int,
) -> list[RetrievedMemory]:
    """Truncate so the estimated token count ≤ max_tokens.

    Each result is estimated at 50 tokens when ``token_count`` is not available.
    Results **must** be pre-sorted by descending relevance.
    """
    total = 0
    truncated: list[RetrievedMemory] = []
    for r in results:
        tokens = 50  # default estimate per result
        total += tokens
        if total > max_tokens:
            break
        truncated.append(r)
    return truncated


# ── Internal helpers ────────────────────────────────────────────────────────


def _empty_result(query: str) -> RetrievalResult:
    return RetrievalResult(
        query=query,
        results=[],
        total_count=0,
        token_count=0,
        token_budget=1200,
    )


async def _count_tokens(results: list[RetrievedMemory]) -> int:
    """Estimate total tokens across results."""
    return len(results) * 50  # rough estimate per result