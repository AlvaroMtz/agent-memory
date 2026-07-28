"""Extraction pipeline — high-level orchestration for memory extraction.

Pipeline steps: filter → validate roles → extract → validate evidence → score → return.
"""

from __future__ import annotations

from agent_memory.constants import EXTRACTABLE_ROLES
from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.domain.evidence import Evidence, EvidenceValidationResult
from agent_memory.domain.policies import validate_evidence, validate_extraction_role
from agent_memory.ports.consent import ConsentProvider
from agent_memory.ports.extractor import MemoryExtractor


def filter_extractable_messages(messages: list[dict]) -> list[dict]:
    """Filter only messages with extractable roles (user, trusted_tool)."""
    return [msg for msg in messages if msg.get("role") in EXTRACTABLE_ROLES]


def score_candidate(
    candidate: MemoryCandidate,
    messages: list[dict],
) -> MemoryCandidate:
    """Assign a score to a candidate based on evidence quality.

    Base score equals candidate.confidence.
    Boosted by 10% if evidence text is a literal substring of the source message.
    Penalized by 20% if evidence text is not a literal substring.
    Penalized by 50% if the source message is not found.

    Returns a new MemoryCandidate with updated confidence.
    """
    score = candidate.confidence

    # Find source message
    source: dict | None = None
    for msg in messages:
        if msg.get("id") == candidate.source_message_id:
            source = msg
            break

    if source is not None:
        message_content = source.get("content", "")
        if candidate.evidence_text in message_content:
            # Boost for literal substring evidence
            score = min(1.0, score * 1.1)
        else:
            # Penalty for non-literal evidence
            score = score * 0.8
    else:
        # Penalty for missing source message
        score = score * 0.5

    return candidate.model_copy(update={"confidence": round(score, 4)})


async def extract_memories(
    messages: list[dict],
    subject_id: str,
    tenant_id: str,
    extractor: MemoryExtractor,
    consent: ConsentProvider | None = None,
) -> list[MemoryCandidate]:
    """Full extraction pipeline: filter → validate roles → extract → validate evidence → score → return.

    Args:
        messages: Conversation messages with id, role, content keys.
        subject_id: The subject to extract memories for.
        tenant_id: Tenant scope.
        extractor: MemoryExtractor implementation.
        consent: Optional ConsentProvider. When provided, checks active consent
                 before extraction. Returns empty list if consent is not granted.

    Returns:
        List of validated and scored MemoryCandidate objects.
    """
    # Step 1: Filter only extractable messages (user, trusted_tool)
    extractable = filter_extractable_messages(messages)

    # Step 2: Validate each message role
    for msg in extractable:
        validate_extraction_role(msg.get("role", ""))

    # Step 3: Consent check — fail-closed before extraction
    if consent is not None:
        record = await consent.get_active_consent(
            tenant_id=tenant_id,
            subject_id=subject_id,
            purpose="memory-extraction",
        )
        if record is None:
            return []

    # Step 4: Extract candidates from filtered messages
    candidates = await extractor.extract(
        messages=extractable,
        subject_id=subject_id,
    )

    # Step 5: Validate evidence and score each candidate
    validated: list[MemoryCandidate] = []
    for candidate in candidates:
        ev_result = validate_evidence(candidate, messages)
        scored = score_candidate(candidate, messages)
        if ev_result.is_valid:
            validated.append(scored)

    return validated