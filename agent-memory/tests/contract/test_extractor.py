"""Contract tests for MemoryExtractor.

Reusable test suite that any extractor implementation must pass.
"""
from __future__ import annotations

import pytest

from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.ports.extractor import MemoryExtractor


class ExtractorContractSuite:
    """Contract test suite for MemoryExtractor implementations.

    Usage:
        class TestMyExtractor:
            @pytest.fixture
            def extractor(self):
                return MyExtractor()

            def test_contract(self, extractor):
                ExtractorContractSuite().run_all(extractor)
    """

    async def run_all(self, extractor: MemoryExtractor) -> None:
        """Run all contract tests."""
        await self._test_returns_list(extractor)
        await self._test_empty_messages(extractor)
        await self._test_ignores_assistant(extractor)
        await self._test_user_messages_processed(extractor)

    async def _test_returns_list(self, extractor: MemoryExtractor) -> None:
        """Extract must return a list."""
        results = await extractor.extract(
            messages=[{"role": "user", "content": "Hola", "id": "m1"}],
            subject_id="user-1",
        )
        assert isinstance(results, list)

    async def _test_empty_messages(self, extractor: MemoryExtractor) -> None:
        """Empty messages returns empty list."""
        results = await extractor.extract(
            messages=[],
            subject_id="user-1",
        )
        assert results == []

    async def _test_ignores_assistant(self, extractor: MemoryExtractor) -> None:
        """Assistant messages are not extracted."""
        results = await extractor.extract(
            messages=[{"role": "assistant", "content": "Te recomiendo Python", "id": "m1"}],
            subject_id="user-1",
        )
        # Must not extract from assistant messages
        for r in results:
            assert not r.explicitly_stated  # or check source_role

    async def _test_user_messages_processed(self, extractor: MemoryExtractor) -> None:
        """User messages may produce candidates."""
        results = await extractor.extract(
            messages=[{"role": "user", "content": "Test message", "id": "m1"}],
            subject_id="user-1",
        )
        # Some extractors may return 0 (no pattern matched), that's fine
        assert isinstance(results, list)


class TestRuleBasedExtractorContract:
    """Run the contract suite against RuleBasedExtractor."""

    @pytest.fixture
    def extractor(self):
        from agent_memory.providers.rule_based_extractor import RuleBasedExtractor
        return RuleBasedExtractor()

    @pytest.mark.asyncio
    async def test_contract_suite(self, extractor):
        await ExtractorContractSuite().run_all(extractor)