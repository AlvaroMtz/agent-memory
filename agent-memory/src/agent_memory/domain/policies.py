"""Policy models and validation functions.

Policies govern what can be extracted, retrieved, and how data is handled.
All policies follow fail-closed semantics.
"""

from __future__ import annotations

from agent_memory.constants import EXTRACTABLE_ROLES, NON_EXTRACTABLE_ROLES
from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.domain.consent import ConsentGrant, ConsentRecord
from agent_memory.domain.evidence import Evidence, EvidenceValidationResult
from agent_memory.domain.memory import MemoryRecord
from agent_memory.exceptions import (
    ConsentDeniedError,
    ConsentExpiredError,
    ConsentRevokedError,
    EvidenceNotFoundError,
    InvalidSourceRoleError,
    LowConfidenceError,
    MissingTenantError,
    NotExplicitlyStatedError,
    SensitiveInferenceError,
    SourceMessageNotFoundError,
)


def validate_extraction_role(role: str) -> None:
    """Validate that a message role is eligible for extraction.

    Raises InvalidSourceRoleError if the role is not allowed.
    """
    if role in NON_EXTRACTABLE_ROLES:
        raise InvalidSourceRoleError(
            f"Messages with role '{role}' are not eligible for extraction. "
            f"Allowed roles: {EXTRACTABLE_ROLES}"
        )
    if role not in EXTRACTABLE_ROLES:
        raise InvalidSourceRoleError(
            f"Unknown role '{role}'. Allowed roles: {EXTRACTABLE_ROLES}"
        )


def validate_evidence(candidate: MemoryCandidate, messages: list[dict]) -> EvidenceValidationResult:
    """Validate that a candidate has verifiable evidence.

    Evidence must:
    - reference an existing source_message_id
    - have evidence_text that appears literally in the source
    """
    source = None
    for msg in messages:
        if msg.get("id") == candidate.source_message_id:
            source = msg
            break

    if source is None:
        return EvidenceValidationResult(
            is_valid=False,
            reason=f"source_message_id '{candidate.source_message_id}' not found",
        )

    message_content = source.get("content", "")
    if candidate.evidence_text not in message_content:
        return EvidenceValidationResult(
            is_valid=False,
            reason=f"evidence_text '{candidate.evidence_text}' is not a literal substring of the source message",
        )

    return EvidenceValidationResult(is_valid=True)


def validate_candidate(
    candidate: MemoryCandidate,
    messages: list[dict],
    *,
    minimum_confidence: float = 0.85,
    require_evidence: bool = True,
) -> None:
    """Full validation pipeline for a memory candidate.

    Raises on first validation failure.
    """
    # Role check
    validate_extraction_role(candidate.source_role)

    # Evidence check
    if require_evidence or candidate.explicitly_stated:
        ev_result = validate_evidence(candidate, messages)
        if not ev_result.is_valid:
            raise EvidenceNotFoundError(ev_result.reason or "Evidence validation failed")

    # Explicitly stated
    if not candidate.explicitly_stated:
        raise NotExplicitlyStatedError("Candidate must be explicitly stated")

    # Confidence threshold
    if candidate.confidence < minimum_confidence:
        raise LowConfidenceError(
            f"Confidence {candidate.confidence:.2f} below minimum threshold {minimum_confidence}"
        )

    # Prevent sensitive inference
    if candidate.sensitivity == "sensitive" and not candidate.explicitly_stated:
        raise SensitiveInferenceError(
            "Sensitive-sensitivity candidates require explicit extraction"
        )


def validate_consent_for_write(
    consent: ConsentRecord | None,
    memory_type: str,
    sensitivity: str,
) -> None:
    """Validate that consent allows writing a memory.

    Raises consent-related exceptions on failure.
    """
    if consent is None:
        raise ConsentDeniedError("No consent record found")

    if not consent.is_active():
        if consent.is_revoked():
            raise ConsentRevokedError("Consent has been revoked")
        raise ConsentExpiredError("Consent has expired")

    if not consent.allows_write(memory_type, sensitivity):
        raise ConsentDeniedError(
            f"Consent does not allow write for memory_type={memory_type}, sensitivity={sensitivity}"
        )


def validate_consent_for_read(
    consent: ConsentRecord | None,
    memory_type: str,
    sensitivity: str,
) -> None:
    """Validate that consent allows reading a memory.

    Raises consent-related exceptions on failure.
    """
    if consent is None:
        raise ConsentDeniedError("No consent record found")

    if not consent.is_active():
        if consent.is_revoked():
            raise ConsentRevokedError("Consent has been revoked")
        raise ConsentExpiredError("Consent has expired")

    if not consent.allows_read(memory_type, sensitivity):
        raise ConsentDeniedError(
            f"Consent does not allow read for memory_type={memory_type}, sensitivity={sensitivity}"
        )


def validate_context_present(tenant_id: str | None) -> None:
    """Fail-closed: if no tenant_id is provided, deny the operation."""
    if not tenant_id:
        raise MissingTenantError("tenant_id is required and must be non-empty")


# ── Contradiction detection ────────────────────────────────────────────────────


def classify_contradiction(
    existing: MemoryRecord,
    candidate: MemoryCandidate,
    existing_value: object | None = None,
) -> str:
    """Classify the relationship between an existing memory and a new candidate.

    Args:
        existing: The existing memory record.
        candidate: The new candidate.
        existing_value: Optional existing version value for value comparison.
                        If not provided, only predicate/subject_key are compared
                        (all same-key candidates are classified as duplicate).

    Returns one of: duplicate, supports, supersedes, contradicts, unrelated
    """
    # Same predicate and subject_key → check value
    if existing.predicate == candidate.predicate and existing.subject_key == candidate.subject_key:
        if existing_value is not None:
            # Compare values to distinguish duplicate from supersede/contradict
            if str(candidate.value) == str(existing_value):
                return "duplicate"
            if existing.memory_type == "preference":
                return "supersedes"
            return "contradicts"
        return "duplicate"

    # Same predicate, different subject_key
    if existing.predicate == candidate.predicate:
        if existing.memory_type == "preference":
            return "supersedes"
        return "contradicts"

    # Related subject key
    if existing.subject_key == candidate.subject_key:
        return "supports"

    return "unrelated"