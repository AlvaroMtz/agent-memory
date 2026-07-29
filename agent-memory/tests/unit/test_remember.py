"""Unit tests for the extraction pipeline (remember.py)."""

from __future__ import annotations

import pytest

from agent_memory.application.remember import (
    extract_memories,
    filter_extractable_messages,
    score_candidate,
)
from agent_memory.constants import EXTRACTABLE_ROLES
from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.providers.fake_extractor import FakeExtractor


class TestFilterExtractableMessages:
    """Filtering messages by role eligibility."""

    def test_only_user_and_trusted_tool_pass(self):
        messages = [
            {"id": "m1", "role": "user", "content": "I use TypeScript"},
            {"id": "m2", "role": "trusted_tool", "content": "Config loaded"},
            {"id": "m3", "role": "assistant", "content": "Here's some code"},
            {"id": "m4", "role": "system", "content": "System initialized"},
        ]
        result = filter_extractable_messages(messages)
        assert len(result) == 2
        assert all(m["role"] in EXTRACTABLE_ROLES for m in result)

    def test_assistant_and_system_filtered_out(self):
        messages = [
            {"id": "m1", "role": "assistant", "content": "Hello"},
            {"id": "m2", "role": "system", "content": "Ready"},
            {"id": "m3", "role": "developer", "content": "debug"},
            {"id": "m4", "role": "tool", "content": "tool call result"},
        ]
        result = filter_extractable_messages(messages)
        assert result == []

    def test_empty_messages_returns_empty_list(self):
        assert filter_extractable_messages([]) == []

    def test_user_only_preserves_order(self):
        messages = [
            {"id": "m1", "role": "user", "content": "First"},
            {"id": "m2", "role": "assistant", "content": "Answer"},
            {"id": "m3", "role": "user", "content": "Second"},
        ]
        result = filter_extractable_messages(messages)
        assert len(result) == 2
        assert result[0]["id"] == "m1"
        assert result[1]["id"] == "m3"


class TestExtractMemories:
    """Full extraction pipeline."""

    @pytest.mark.asyncio
    async def test_happy_path(self):
        """User message → candidate with valid evidence."""
        messages = [
            {"id": "m1", "role": "user", "content": "I like TypeScript"},
        ]
        candidate = MemoryCandidate(
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            value="TypeScript",
            source_message_id="m1",
            evidence_text="TypeScript",
            source_role="user",
        )
        extractor = FakeExtractor(responses={"I like TypeScript": [candidate]})

        result = await extract_memories(
            messages=messages,
            subject_id="user-1",
            tenant_id="tenant-a",
            extractor=extractor,
        )

        assert len(result) == 1
        assert result[0].predicate == "code_language"
        assert result[0].value == "TypeScript"
        # Evidence literal → boost applied
        assert result[0].confidence > 0.85

    @pytest.mark.asyncio
    async def test_no_extractable_messages(self):
        """Only assistant messages → empty result."""
        messages = [
            {"id": "m1", "role": "assistant", "content": "I'd recommend Python"},
        ]
        extractor = FakeExtractor()

        result = await extract_memories(
            messages=messages,
            subject_id="user-1",
            tenant_id="tenant-a",
            extractor=extractor,
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_consent_check_called_when_provided(self):
        """Consent provider is called when present — returns empty if no consent."""
        consent_call_args: dict | None = None

        class TrackingConsentProvider:
            async def get_active_consent(self, *, tenant_id, subject_id, purpose):
                nonlocal consent_call_args
                consent_call_args = dict(
                    tenant_id=tenant_id,
                    subject_id=subject_id,
                    purpose=purpose,
                )
                return None

        messages = [
            {"id": "m1", "role": "user", "content": "Hi"},
        ]
        extractor = FakeExtractor()
        consent = TrackingConsentProvider()

        result = await extract_memories(
            messages=messages,
            subject_id="user-1",
            tenant_id="tenant-a",
            extractor=extractor,
            consent=consent,
        )

        assert consent_call_args is not None
        assert consent_call_args["tenant_id"] == "tenant-a"
        assert consent_call_args["subject_id"] == "user-1"
        assert consent_call_args["purpose"] == "memory-extraction"
        assert result == []

    @pytest.mark.asyncio
    async def test_no_consent_no_check(self):
        """When consent is None, no consent check is performed."""
        messages = [
            {"id": "m1", "role": "user", "content": "My name is Ana"},
        ]
        candidate = MemoryCandidate(
            memory_type="semantic",
            subject_key="user",
            predicate="name",
            value="Ana",
            source_message_id="m1",
            evidence_text="Ana",
            source_role="user",
        )
        extractor = FakeExtractor(responses={"My name is Ana": [candidate]})

        result = await extract_memories(
            messages=messages,
            subject_id="user-1",
            tenant_id="tenant-a",
            extractor=extractor,
            consent=None,
        )

        assert len(result) == 1
        assert result[0].value == "Ana"


class TestScoreCandidate:
    """Candidate scoring based on evidence."""

    def test_literal_boost(self):
        """evidence_text is a literal substring → confidence boosted by 10%."""
        candidate = MemoryCandidate(
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            value="TypeScript",
            source_message_id="m1",
            evidence_text="TypeScript",
            source_role="user",
            confidence=0.85,
        )
        messages = [
            {"id": "m1", "role": "user", "content": "I like TypeScript for coding"},
        ]

        scored = score_candidate(candidate, messages)

        expected = round(min(1.0, 0.85 * 1.1), 4)
        assert scored.confidence == expected
        assert scored.confidence > 0.85

    def test_no_evidence_penalty(self):
        """evidence_text not found in source → confidence penalized by 20%."""
        candidate = MemoryCandidate(
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            value="Python",
            source_message_id="m1",
            evidence_text="Python",
            source_role="user",
            confidence=0.9,
        )
        messages = [
            {"id": "m1", "role": "user", "content": "I like TypeScript"},
        ]

        scored = score_candidate(candidate, messages)

        expected = round(0.9 * 0.8, 4)
        assert scored.confidence == expected
        assert scored.confidence < 0.9

    def test_missing_source_message_penalty(self):
        """No source message found → confidence penalized by 50%."""
        candidate = MemoryCandidate(
            memory_type="semantic",
            subject_key="user",
            predicate="name",
            value="Bob",
            source_message_id="nonexistent",
            evidence_text="Bob",
            source_role="user",
            confidence=1.0,
        )
        messages = [
            {"id": "m1", "role": "user", "content": "My name is Bob"},
        ]

        scored = score_candidate(candidate, messages)

        expected = round(1.0 * 0.5, 4)
        assert scored.confidence == expected

    def test_boost_caps_at_one(self):
        """Boosted confidence is capped at 1.0."""
        candidate = MemoryCandidate(
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            value="TypeScript",
            source_message_id="m1",
            evidence_text="TypeScript",
            source_role="user",
            confidence=0.95,
        )
        messages = [
            {"id": "m1", "role": "user", "content": "I like TypeScript"},
        ]

        scored = score_candidate(candidate, messages)

        expected = round(min(1.0, 0.95 * 1.1), 4)
        assert scored.confidence == expected
        assert scored.confidence <= 1.0
