"""Extraction pipeline — high-level orchestration for memory extraction.

Pipeline steps: filter → validate roles → extract → validate evidence → score → return.
"""

from __future__ import annotations

from agent_memory.constants import DEFAULT_MINIMUM_CONFIDENCE, EXTRACTABLE_ROLES
from agent_memory.context import TenantContext
from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.domain.policies import validate_candidate, validate_extraction_role
from agent_memory.ports.backend import MemoryBackend
from agent_memory.ports.conflict import ConflictResolver
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
    conflict_resolver: ConflictResolver | None = None,
    backend: MemoryBackend | None = None,
) -> list[MemoryCandidate]:
    """Full extraction pipeline: filter → validate roles → extract → validate evidence → score → return.

    Args:
        messages: Conversation messages with id, role, content keys.
        subject_id: The subject to extract memories for.
        tenant_id: Tenant scope.
        extractor: MemoryExtractor implementation.
        consent: Optional ConsentProvider. When provided, checks active consent
                 before extraction. Returns empty list if consent is not granted.
        conflict_resolver: Optional ConflictResolver for contradiction detection.
                           When provided, checks each candidate against existing memories.
        backend: Optional MemoryBackend for loading existing memories during
                 contradiction detection. Required if conflict_resolver is provided.

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

    # Step 5: Validate candidate policy and score each candidate.  This is
    # intentionally fail-closed per candidate: invalid evidence, non-explicit
    # claims, low confidence, or forged source roles are rejected before any
    # caller can persist them.
    validated: list[MemoryCandidate] = []
    for candidate in candidates:
        try:
            validate_candidate(
                candidate,
                messages,
                minimum_confidence=DEFAULT_MINIMUM_CONFIDENCE,
                require_evidence=True,
            )
        except Exception:
            continue
        validated.append(score_candidate(candidate, messages))

    # Step 6: Contradiction detection and resolution
    if conflict_resolver is not None and backend is not None:
        existing_memories = await backend.list_memories(
            tenant_id=tenant_id,
            subject_id=subject_id,
            limit=500,
        )
        resolved: list[MemoryCandidate] = []
        for candidate in validated:
            skip_candidate = False
            for existing in existing_memories:
                classification = await conflict_resolver.classify(existing, candidate)
                action = await conflict_resolver.resolve(existing, candidate, classification)
                if action == "skip":
                    skip_candidate = True
                    break
                elif action == "supersede":
                    await backend.update_memory_status(
                        existing.id,
                        "superseded",
                        context=TenantContext(tenant_id=tenant_id),
                    )
                elif action == "flag":
                    # Semantic conflicts with equal authority must not become
                    # active automatically.  Mark the existing record for
                    # review and keep the candidate out of automatic activation.
                    await backend.update_memory_status(
                        existing.id,
                        "pending_review",
                        context=TenantContext(tenant_id=tenant_id),
                    )
                    skip_candidate = True
                    break
            if not skip_candidate:
                resolved.append(candidate)
        validated = resolved

    return validated
