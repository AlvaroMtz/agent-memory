"""Unit tests for domain models."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from agent_memory.domain.audit import AuditEvent
from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.domain.consent import ConsentGrant, ConsentRecord
from agent_memory.domain.evidence import Evidence
from agent_memory.domain.memory import MemoryRecord, MemoryVersion
from agent_memory.domain.retrieval import RetrievalResult, RetrievedMemory, ScoreBreakdown


class TestMemoryRecord:
    """Test MemoryRecord domain model."""

    def test_create_default(self):
        record = MemoryRecord(
            tenant_id="tenant-a",
            subject_id="user-1",
            purpose="assistant-personalization",
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
        )
        assert record.status == "candidate"
        assert record.current_version == 0
        assert isinstance(record.id, UUID)

    def test_is_active_only_when_active(self):
        record = MemoryRecord(
            tenant_id="t",
            subject_id="s",
            purpose="p",
            memory_type="preference",
            subject_key="k",
            predicate="p",
            status="active",
        )
        assert record.is_active()

    def test_is_active_false_when_not_active(self):
        for status in ["candidate", "superseded", "revoked", "expired", "rejected", "deleted"]:
            record = MemoryRecord(
                tenant_id="t",
                subject_id="s",
                purpose="p",
                memory_type="preference",
                subject_key="k",
                predicate="p",
                status=status,  # type: ignore
            )
            assert not record.is_active(), f"should not be active for status {status}"

    def test_is_expired_by_status(self):
        record = MemoryRecord(
            tenant_id="t",
            subject_id="s",
            purpose="p",
            memory_type="preference",
            subject_key="k",
            predicate="p",
            status="expired",
        )
        assert record.is_expired()

    def test_is_expired_by_date(self):
        record = MemoryRecord(
            tenant_id="t",
            subject_id="s",
            purpose="p",
            memory_type="preference",
            subject_key="k",
            predicate="p",
            status="active",
            valid_until=datetime(2020, 1, 1, tzinfo=UTC),
        )
        assert record.is_expired()

    def test_supersede_changes_status(self):
        record = MemoryRecord(
            tenant_id="t",
            subject_id="s",
            purpose="p",
            memory_type="preference",
            subject_key="k",
            predicate="p",
            status="active",
        )
        record.supersede()
        assert record.status == "superseded"

    def test_revoke_changes_status(self):
        record = MemoryRecord(
            tenant_id="t",
            subject_id="s",
            purpose="p",
            memory_type="preference",
            subject_key="k",
            predicate="p",
            status="active",
        )
        record.revoke()
        assert record.status == "revoked"


class TestMemoryVersion:
    """Test MemoryVersion domain model."""

    def test_create_default(self):
        version = MemoryVersion(
            memory_id=UUID(int=0),
            version=1,
            value="Python",
            confidence=0.95,
        )
        assert version.version == 1
        assert version.value == "Python"
        assert version.confidence == 0.95
        assert version.sensitivity == "internal"

    def test_confidence_validation(self):
        with pytest.raises(ValueError):
            MemoryVersion(
                memory_id=UUID(int=0),
                version=1,
                value="Python",
                confidence=1.5,  # invalid
            )


class TestMemoryCandidate:
    """Test MemoryCandidate domain model."""

    def test_create_valid(self):
        candidate = MemoryCandidate(
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            value="TypeScript",
            source_message_id="msg-1",
            evidence_text="TypeScript",
        )
        assert candidate.is_valid()
        assert candidate.identity_key == ("preference", "code", "code_language")

    def test_is_valid_false_without_evidence(self):
        candidate = MemoryCandidate(
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            value="TypeScript",
            source_message_id="",
            evidence_text="",
        )
        assert not candidate.is_valid()


class TestConsentGrant:
    """Test ConsentGrant domain model."""

    def test_default_deny(self):
        grant = ConsentGrant(purpose="test")
        assert not grant.allow_write
        assert not grant.allow_read
        assert grant.allowed_memory_types == {"preference"}

    def test_full_access(self):
        grant = ConsentGrant(
            purpose="test",
            allow_write=True,
            allow_read=True,
            allowed_memory_types={"semantic", "preference"},
        )
        assert grant.allow_write
        assert grant.allow_read


class TestConsentRecord:
    """Test ConsentRecord domain model."""

    def test_is_active_when_not_revoked(self):
        record = ConsentRecord(
            tenant_id="t",
            subject_id="s",
            actor_id="a",
            purpose="p",
            allow_write=True,
            allow_read=True,
            allowed_memory_types={"preference", "semantic"},
            allowed_sensitivity={"public", "internal", "personal"},
        )
        assert record.is_active()

    def test_is_not_active_when_revoked(self):
        record = ConsentRecord(
            tenant_id="t",
            subject_id="s",
            actor_id="a",
            purpose="p",
            allow_write=True,
            allow_read=True,
            allowed_memory_types={"preference"},
            allowed_sensitivity={"public"},
            revoked_at=datetime.now(UTC),
        )
        assert not record.is_active()

    def test_allows_write_checks_type_and_sensitivity(self):
        record = ConsentRecord(
            tenant_id="t",
            subject_id="s",
            actor_id="a",
            purpose="p",
            allow_write=True,
            allow_read=True,
            allowed_memory_types={"preference"},
            allowed_sensitivity={"public"},
        )
        assert record.allows_write("preference", "public")
        assert not record.allows_write("semantic", "public")
        assert not record.allows_write("preference", "sensitive")

    def test_revoke_sets_revoked_at(self):
        record = ConsentRecord(
            tenant_id="t",
            subject_id="s",
            actor_id="a",
            purpose="p",
            allow_write=True,
            allow_read=True,
            allowed_memory_types={"preference"},
            allowed_sensitivity={"public"},
        )
        record.revoke()
        assert record.is_revoked()


class TestEvidence:
    """Test Evidence model."""

    def test_evidence_literal_substring(self):
        ev = Evidence(
            source_message_id="msg-1",
            evidence_text="TypeScript",
            source_role="user",
            message_content="Prefiero que los ejemplos sean en TypeScript.",
        )
        assert ev.evidence_is_literal_substring()

    def test_evidence_not_found(self):
        ev = Evidence(
            source_message_id="msg-1",
            evidence_text="Python",
            source_role="user",
            message_content="Prefiero TypeScript.",
        )
        assert not ev.evidence_is_literal_substring()


class TestRetrievalModels:
    """Test retrieval domain models."""

    def test_retrieved_memory(self):
        memory = RetrievedMemory(
            id=UUID(int=0),
            version=1,
            memory_type="preference",
            predicate="code_language",
            value="Python",
            score=0.95,
            score_breakdown={"vector": 0.9, "lexical": 0.85},
            confidence=0.95,
            source_type="user_explicit",
            sensitivity="public",
            created_at=datetime.now(UTC),
        )
        assert memory.score == 0.95

    def test_retrieval_result(self):
        result = RetrievalResult(
            query="test",
            results=[],
            total_count=0,
            token_count=0,
            token_budget=1200,
        )
        assert result.empty

    def test_score_breakdown_formula(self):
        breakdown = ScoreBreakdown(
            vector_score=1.0,
            lexical_score=1.0,
            recency_score=1.0,
            confidence_score=1.0,
        )
        assert breakdown.total == pytest.approx(1.0)

        breakdown2 = ScoreBreakdown(
            vector_score=0.5,
            lexical_score=0.5,
            recency_score=0.5,
            confidence_score=0.5,
        )
        assert breakdown2.total == pytest.approx(0.5)


class TestAuditEvent:
    """Test AuditEvent model."""

    def test_create_default(self):
        event = AuditEvent(
            tenant_id="tenant-a",
            actor_id="user-1",
            action="memory.retrieved",
        )
        assert event.outcome == "allowed"
        assert isinstance(event.id, UUID)

    def test_denied_outcome(self):
        event = AuditEvent(
            tenant_id="tenant-a",
            actor_id="user-1",
            action="security.access_denied",
            outcome="denied",
            reason="No consent",
        )
        assert event.outcome == "denied"
