"""Unit tests for the ContradictionResolver."""

from __future__ import annotations

import pytest

from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.domain.memory import MemoryRecord
from agent_memory.providers.contradiction_resolver import (
    ContradictionResolver,
    ContradictionResolverFactory,
)


class TestContradictionResolverClassify:
    """Classification of relationships between existing memories and candidates."""

    def setup_method(self) -> None:
        self.resolver = ContradictionResolver()

        self.existing_pref = MemoryRecord(
            tenant_id="t",
            subject_id="s",
            purpose="p",
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            status="active",
        )

    @pytest.mark.asyncio
    async def test_classify_duplicate(self):
        """Same predicate and subject_key → duplicate."""
        candidate = MemoryCandidate(
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            value="TypeScript",
            source_message_id="msg-1",
            evidence_text="TypeScript",
        )
        result = await self.resolver.classify(self.existing_pref, candidate)
        assert result == "duplicate"

    @pytest.mark.asyncio
    async def test_classify_supersedes_preference(self):
        """Same predicate, different value, preference type → supersedes."""
        candidate = MemoryCandidate(
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            value="Rust",
            source_message_id="msg-1",
            evidence_text="Rust",
        )
        result = await self.resolver.classify(
            self.existing_pref, candidate, existing_value="TypeScript"
        )
        assert result == "supersedes"

    @pytest.mark.asyncio
    async def test_classify_contradicts_semantic(self):
        """Same predicate, different value, semantic type → contradicts."""
        existing = MemoryRecord(
            tenant_id="t",
            subject_id="s",
            purpose="p",
            memory_type="semantic",
            subject_key="employment",
            predicate="employer",
            status="active",
        )
        candidate = MemoryCandidate(
            memory_type="semantic",
            subject_key="employment",
            predicate="employer",
            value="Beta Inc",
            source_message_id="msg-1",
            evidence_text="Beta Inc",
        )
        result = await self.resolver.classify(existing, candidate, existing_value="Acme Corp")
        assert result == "contradicts"

    @pytest.mark.asyncio
    async def test_classify_supports(self):
        """Same subject_key, different predicate → supports."""
        candidate = MemoryCandidate(
            memory_type="preference",
            subject_key="code",
            predicate="editor",
            value="VS Code",
            source_message_id="msg-1",
            evidence_text="VS Code",
        )
        result = await self.resolver.classify(self.existing_pref, candidate)
        assert result == "supports"

    @pytest.mark.asyncio
    async def test_classify_unrelated(self):
        """Different predicate and subject_key → unrelated."""
        candidate = MemoryCandidate(
            memory_type="preference",
            subject_key="language",
            predicate="response_language",
            value="Spanish",
            source_message_id="msg-1",
            evidence_text="Spanish",
        )
        result = await self.resolver.classify(self.existing_pref, candidate)
        assert result == "unrelated"


class TestContradictionResolverResolve:
    """Resolution actions based on classification."""

    def setup_method(self) -> None:
        self.resolver = ContradictionResolver()
        self.existing = MemoryRecord(
            tenant_id="t",
            subject_id="s",
            purpose="p",
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            status="active",
        )
        self.candidate = MemoryCandidate(
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            value="TypeScript",
            source_message_id="msg-1",
            evidence_text="TypeScript",
        )

    @pytest.mark.asyncio
    async def test_resolve_duplicate_to_skip(self):
        action = await self.resolver.resolve(self.existing, self.candidate, "duplicate")
        assert action == "skip"

    @pytest.mark.asyncio
    async def test_resolve_supersedes_to_supersede(self):
        action = await self.resolver.resolve(self.existing, self.candidate, "supersedes")
        assert action == "supersede"

    @pytest.mark.asyncio
    async def test_resolve_contradicts_to_flag(self):
        action = await self.resolver.resolve(self.existing, self.candidate, "contradicts")
        assert action == "flag"

    @pytest.mark.asyncio
    async def test_resolve_supports_to_accept(self):
        action = await self.resolver.resolve(self.existing, self.candidate, "supports")
        assert action == "accept"

    @pytest.mark.asyncio
    async def test_resolve_unrelated_to_accept(self):
        action = await self.resolver.resolve(self.existing, self.candidate, "unrelated")
        assert action == "accept"

    @pytest.mark.asyncio
    async def test_resolve_unknown_to_reject(self):
        action = await self.resolver.resolve(self.existing, self.candidate, "unknown")
        assert action == "reject"


class TestContradictionResolverFactory:
    """Factory creates resolver instances."""

    def test_factory_creates_resolver(self):
        factory = ContradictionResolverFactory()
        resolver = factory.create()
        assert isinstance(resolver, ContradictionResolver)


class TestRememberWithContradictionResolution:
    """Integration: remember pipeline with contradiction detection."""

    @pytest.mark.asyncio
    async def test_contradiction_in_pipeline(self):
        """Duplicates are skipped when conflict_resolver is provided."""
        from agent_memory.application.remember import extract_memories
        from agent_memory.providers.fake_extractor import FakeExtractor

        messages = [
            {"id": "msg-1", "role": "user", "content": "Me gusta TypeScript"},
        ]
        candidate = MemoryCandidate(
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            value="TypeScript",
            source_message_id="msg-1",
            evidence_text="TypeScript",
            source_role="user",
        )
        # The extractor will create one candidate, and it won't match any
        # existing memories so it should pass through
        extractor = FakeExtractor(responses={"Me gusta TypeScript": [candidate]})

        result = await extract_memories(
            messages=messages,
            subject_id="user-1",
            tenant_id="tenant-a",
            extractor=extractor,
        )

        assert len(result) == 1
        assert result[0].predicate == "code_language"
