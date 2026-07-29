"""Retrieval pipeline — high-level orchestration for hybrid memory retrieval.

Pipeline steps: structured filters → vector search → lexical search →
score fusion → rerank → consent filter → token budget → return.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from agent_memory.constants import MemoryStatusEnum
from agent_memory.domain.retrieval import RetrievalResult, RetrievedMemory
from agent_memory.ports.backend import MemoryBackend
from agent_memory.ports.consent import ConsentProvider
from agent_memory.ports.embedder import EmbeddingProvider
from agent_memory.ports.encryption import EncryptionContext, EncryptionProvider

logger = logging.getLogger(__name__)


async def retrieve(
    tenant_id: str,
    subject_id: str = "",
    query: str | None = None,
    filters: dict[str, Any] | None = None,
    backend: MemoryBackend | None = None,
    embedder: EmbeddingProvider | None = None,
    consent: ConsentProvider | None = None,
    limit: int | None = None,
    max_tokens: int = 1200,
    encryption: EncryptionProvider | None = None,
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
    effective_limit: int = limit if limit is not None else int(filters.get("limit", 50))

    # Fail closed: without an active read consent for this purpose, do not search,
    # do not compute embeddings, and do not decrypt/return anything.
    active_consent = None
    if consent is None:
        logger.info("retrieve blocked: no consent provider configured")
        return _empty_result(query or "")

    active_consent = await consent.get_active_consent(
        tenant_id=tenant_id,
        subject_id=subject_id,
        purpose=purpose or "",
    )
    if active_consent is None or not active_consent.allow_read:
        logger.info("retrieve blocked: no active read consent")
        return _empty_result(query or "")

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
                query_vector=query_vector,
                purpose=purpose,
                limit=effective_limit,
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
                query_vector=None,
                purpose=purpose,
                limit=effective_limit,
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
                query_vector=query_vector,
                purpose=purpose,
                limit=effective_limit,
            )
            all_results = fallback
        except Exception:
            logger.exception("Fallback list failed")

    # ── Score fusion ───────────────────────────────────────────────────
    all_results = score_fusion(all_results)

    # ── Sort by descending score ───────────────────────────────────────
    all_results.sort(key=lambda r: r.score, reverse=True)

    # ── Consent filter ─────────────────────────────────────────────────
    all_results = apply_consent_filter(all_results, active_consent)

    # ── Token budget ───────────────────────────────────────────────────
    budget_results = apply_token_budget(all_results, max_tokens)

    # ── Decrypt values ─────────────────────────────────────────────────
    decrypted_results: list[RetrievedMemory] = []
    for r in budget_results:
        if _is_encrypted_json(r.value):
            r.value = (
                await _decrypt_value(r.value, encryption, tenant_id) if encryption else r.value
            )
        if _is_encrypted_json(r.evidence_text):
            r.evidence_text = (
                await _decrypt_evidence(r.evidence_text, encryption, tenant_id)
                if encryption
                else r.evidence_text
            )
        decrypted_results.append(r)

    total_tokens = await _count_tokens(decrypted_results)

    return RetrievalResult(
        query=effective_query,
        results=budget_results,
        total_count=len(budget_results),
        token_count=total_tokens,
        token_budget=max_tokens,
    )


def _is_encrypted_json(value: Any) -> bool:
    """Check if a value looks like encrypted JSON."""
    if isinstance(value, dict):
        return value.get("encrypted") is True or value.get("encrypted") == "true"
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return isinstance(parsed, dict) and parsed.get("encrypted") is True
        except (json.JSONDecodeError, TypeError):
            return False
    return False


async def _decrypt_value(value: Any, encryption: EncryptionProvider, tenant_id: str) -> Any:
    """Decrypt an encrypted value. Returns the encrypted payload if decryption fails.

    Retrieval must fail closed: if the provider cannot decrypt, we do not invent
    plaintext and we do not drop errors into logs with sensitive material.
    """
    if encryption is None:
        return value

    from agent_memory.ports.encryption import EncryptedPayload

    try:
        if _is_encrypted_json(value):
            payload_data = value if isinstance(value, dict) else json.loads(value)
            ciphertext = base64.b64decode(payload_data["ciphertext"])
            nonce = base64.b64decode(payload_data["nonce"]) if payload_data.get("nonce") else None
            payload = EncryptedPayload(
                ciphertext=ciphertext,
                nonce=nonce,
                algorithm=payload_data.get("algorithm", "aes-256-gcm"),
                key_id=payload_data.get("key_id"),
            )
            ctx = EncryptionContext(tenant_id=tenant_id, purpose=None, key_id=payload.key_id)
            plaintext = await encryption.decrypt(payload, context=ctx)
            return json.loads(plaintext.decode("utf-8"))
    except Exception:
        pass
    return value


async def _decrypt_evidence(
    evidence: str | None,
    encryption: EncryptionProvider,
    tenant_id: str,
) -> str | None:
    """Decrypt evidence text. Returns encrypted evidence if decryption fails."""
    if evidence is None:
        return None

    if encryption is None:
        return evidence

    from agent_memory.ports.encryption import EncryptedPayload

    try:
        if _is_encrypted_json(evidence):
            payload_data = json.loads(evidence)
            ciphertext = base64.b64decode(payload_data["ciphertext"])
            nonce = base64.b64decode(payload_data["nonce"]) if payload_data.get("nonce") else None
            payload = EncryptedPayload(
                ciphertext=ciphertext,
                nonce=nonce,
                algorithm=payload_data.get("algorithm", "aes-256-gcm"),
                key_id=payload_data.get("key_id"),
            )
            ctx = EncryptionContext(tenant_id=tenant_id, purpose=None, key_id=payload.key_id)
            plaintext = await encryption.decrypt(payload, context=ctx)
            return plaintext.decode("utf-8")
    except Exception:
        pass
    return evidence


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
    consent_record,
    tenant_id: str | None = None,
    subject_id: str | None = None,
) -> list[RetrievedMemory]:
    """Remove results that the active consent policy does not allow reading."""
    filtered: list[RetrievedMemory] = []
    for r in results:
        if hasattr(consent_record, "allows_read"):
            if consent_record.allows_read(r.memory_type, r.sensitivity):
                filtered.append(r)
        elif (
            hasattr(consent_record, "check_read_access")
            and tenant_id is not None
            and subject_id is not None
        ):
            try:
                if consent_record.check_read_access(
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
