"""MemoryExtractor port — abstract interface for extracting memory candidates.

Extractors analyze messages and produce MemoryCandidate objects.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent_memory.domain.candidate import MemoryCandidate


@runtime_checkable
class MemoryExtractor(Protocol):
    """Port for memory extraction from messages.

    Implementations:
    - FakeExtractor: returns configured fixtures for tests
    - RuleBasedExtractor: deterministic regex-based extraction for demos
    - LangChainStructuredExtractor: LLM-based extraction with structured output
    """

    async def extract(
        self,
        *,
        messages: list[dict],
        subject_id: str,
    ) -> list[MemoryCandidate]:
        """Extract memory candidates from a list of messages.

        Args:
            messages: List of message dicts with id, role, content fields.
            subject_id: The subject extracting candidates for.

        Returns:
            List of MemoryCandidate objects found in the messages.
        """
        ...


class MemoryExtractorFactory(Protocol):
    """Factory for creating MemoryExtractor instances."""

    def create(self, **kwargs) -> MemoryExtractor:
        """Create a MemoryExtractor instance."""
        ...
