"""Unit tests for policy validation functions."""

import pytest

from agent_memory.constants import EXTRACTABLE_ROLES, NON_EXTRACTABLE_ROLES
from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.domain.consent import ConsentRecord
from agent_memory.domain.memory import MemoryRecord
from agent_memory.domain.policies import (
    classify_contradiction,
    validate_candidate,
    validate_consent_for_read,
    validate_consent_for_write,
    validate_context_present,
    validate_evidence,
    validate_extraction_role,
)
from agent_memory.exceptions import (
    ConsentDeniedError,
    ConsentExpiredError,
    ConsentRevokedError,
    EvidenceNotFoundError,
    InvalidSourceRoleError,
    LowConfidenceError,
    MissingTenantError,
    NotExplicitlyStatedError,
    SourceMessageNotFoundError,
)


class TestValidateExtractionRole:
    """Test role validation for extraction."""

    def test_user_allowed(self):
        validate_extraction_role("user")  # should not raise

    def test_assistant_not_allowed(self):
        with pytest.raises(InvalidSourceRoleError):
            validate_extraction_role("assistant")

    def test_system_not_allowed(self):
        with pytest.raises(InvalidSourceRoleError):
            validate_extraction_role("system")

    def test_developer_not_allowed(self):
        with pytest.raises(InvalidSourceRoleError):
            validate_extraction_role("developer")

    def test_unknown_role_not_allowed(self):
        with pytest.raises(InvalidSourceRoleError):
            validate_extraction_role("unknown")


class TestValidateEvidence:
    """Test evidence validation."""

    def test_valid_evidence(self):
        candidate = MemoryCandidate(
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            value="TypeScript",
            source_message_id="msg-1",
            evidence_text="Prefiero TypeScript",
        )
        messages = [
            {"id": "msg-1", "role": "user", "content": "Prefiero TypeScript para ejemplos."},
        ]
        result = validate_evidence(candidate, messages)
        assert result.is_valid

    def test_source_not_found(self):
        candidate = MemoryCandidate(
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            value="TypeScript",
            source_message_id="nonexistent",
            evidence_text="Prefiero TypeScript",
        )
        messages = [
            {"id": "msg-1", "role": "user", "content": "Hola"},
        ]
        result = validate_evidence(candidate, messages)
        assert not result.is_valid

    def test_evidence_not_in_message(self):
        candidate = MemoryCandidate(
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            value="Python",
            source_message_id="msg-1",
            evidence_text="Prefiero Python",
        )
        messages = [
            {"id": "msg-1", "role": "user", "content": "Prefiero TypeScript."},
        ]
        result = validate_evidence(candidate, messages)
        assert not result.is_valid


class TestValidateCandidate:
    """Test full candidate validation pipeline."""

    def test_valid_candidate(self):
        candidate = MemoryCandidate(
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            value="TypeScript",
            source_message_id="msg-1",
            evidence_text="TypeScript",
            source_role="user",
        )
        messages = [
            {"id": "msg-1", "role": "user", "content": "Prefiero TypeScript."},
        ]
        validate_candidate(candidate, messages)  # should not raise

    def test_invalid_role(self):
        candidate = MemoryCandidate(
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            value="Python",
            source_message_id="msg-1",
            evidence_text="TypeScript",
            source_role="assistant",
        )
        messages = [{"id": "msg-1", "role": "assistant", "content": "Python es mejor."}]
        with pytest.raises(InvalidSourceRoleError):
            validate_candidate(candidate, messages)

    def test_low_confidence(self):
        candidate = MemoryCandidate(
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            value="Python",
            source_message_id="msg-1",
            evidence_text="Python",
            source_role="user",
            confidence=0.5,
        )
        messages = [{"id": "msg-1", "role": "user", "content": "Python ok."}]
        with pytest.raises(LowConfidenceError):
            validate_candidate(candidate, messages, minimum_confidence=0.85)

    def test_not_explicitly_stated(self):
        candidate = MemoryCandidate(
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            value="Python",
            source_message_id="msg-1",
            evidence_text="Python",
            source_role="user",
            explicitly_stated=False,
        )
        messages = [{"id": "msg-1", "role": "user", "content": "Python?"}]
        with pytest.raises(NotExplicitlyStatedError):
            validate_candidate(candidate, messages)

    def test_invalid_evidence(self):
        candidate = MemoryCandidate(
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            value="Rust",
            source_message_id="msg-1",
            evidence_text="me gusta Rust",
            source_role="user",
        )
        messages = [{"id": "msg-1", "role": "user", "content": "Prefiero Python."}]
        with pytest.raises(EvidenceNotFoundError):
            validate_candidate(candidate, messages)


class TestValidateConsentForWrite:
    """Test consent validation for write operations."""

    def test_no_consent(self):
        with pytest.raises(ConsentDeniedError):
            validate_consent_for_write(None, "preference", "public")

    def test_valid_consent(self):
        consent = ConsentRecord(
            tenant_id="t", subject_id="s", actor_id="a",
            purpose="p", allow_write=True, allow_read=True,
            allowed_memory_types={"preference"},
            allowed_sensitivity={"public"},
        )
        validate_consent_for_write(consent, "preference", "public")  # should not raise

    def test_revoked_consent(self):
        from datetime import datetime, timezone
        consent = ConsentRecord(
            tenant_id="t", subject_id="s", actor_id="a",
            purpose="p", allow_write=True, allow_read=True,
            allowed_memory_types={"preference"},
            allowed_sensitivity={"public"},
            revoked_at=datetime.now(timezone.utc),
        )
        with pytest.raises(ConsentRevokedError):
            validate_consent_for_write(consent, "preference", "public")

    def test_expired_consent(self):
        from datetime import datetime, timezone
        consent = ConsentRecord(
            tenant_id="t", subject_id="s", actor_id="a",
            purpose="p", allow_write=True, allow_read=True,
            allowed_memory_types={"preference"},
            allowed_sensitivity={"public"},
            expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(ConsentExpiredError):
            validate_consent_for_write(consent, "preference", "public")

    def test_type_not_allowed(self):
        consent = ConsentRecord(
            tenant_id="t", subject_id="s", actor_id="a",
            purpose="p", allow_write=True, allow_read=True,
            allowed_memory_types={"preference"},
            allowed_sensitivity={"public"},
        )
        with pytest.raises(ConsentDeniedError):
            validate_consent_for_write(consent, "semantic", "public")


class TestValidateConsentForRead:
    """Test consent validation for read operations."""

    def test_no_consent(self):
        with pytest.raises(ConsentDeniedError):
            validate_consent_for_read(None, "preference", "public")


class TestValidateContextPresent:
    """Test fail-closed tenant validation."""

    def test_valid_tenant(self):
        validate_context_present("tenant-a")  # should not raise

    def test_none_tenant(self):
        with pytest.raises(MissingTenantError):
            validate_context_present(None)

    def test_empty_tenant(self):
        with pytest.raises(MissingTenantError):
            validate_context_present("")


class TestClassifyContradiction:
    """Test contradiction classification."""

    def test_duplicate(self):
        existing = MemoryRecord(
            tenant_id="t", subject_id="s", purpose="p",
            memory_type="preference", subject_key="code",
            predicate="code_language", status="active",
        )
        candidate = MemoryCandidate(
            memory_type="preference", subject_key="code",
            predicate="code_language", value="Python",
            source_message_id="m1", evidence_text="Python",
        )
        assert classify_contradiction(existing, candidate) == "duplicate"

    def test_preference_supersedes(self):
        existing = MemoryRecord(
            tenant_id="t", subject_id="s", purpose="p",
            memory_type="preference", subject_key="code",
            predicate="code_language", status="active",
        )
        candidate = MemoryCandidate(
            memory_type="preference", subject_key="code",
            predicate="response_language", value="Spanish",
            source_message_id="m1", evidence_text="Spanish",
        )
        assert classify_contradiction(existing, candidate) == "supports"

    def test_unrelated(self):
        existing = MemoryRecord(
            tenant_id="t", subject_id="s", purpose="p",
            memory_type="preference", subject_key="code",
            predicate="code_language", status="active",
        )
        candidate = MemoryCandidate(
            memory_type="semantic", subject_key="job",
            predicate="role", value="Engineer",
            source_message_id="m1", evidence_text="Engineer",
        )
        assert classify_contradiction(existing, candidate) == "unrelated"