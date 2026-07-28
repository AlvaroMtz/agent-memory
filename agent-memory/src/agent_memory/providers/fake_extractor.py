"""Fake extractor for tests.

Returns configured fixture responses based on scenario identifiers.
"""

from __future__ import annotations

from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.ports.extractor import MemoryExtractor


class FakeExtractor:
    """Extractor that returns configured fixture responses.

    Useful for tests and controlled scenarios.
    """

    def __init__(self, responses: dict[str, list[MemoryCandidate]] | None = None) -> None:
        self._responses = responses or {}

    def set_response(
        self,
        scenario: str,
        candidates: list[MemoryCandidate],
    ) -> None:
        """Set the response for a given scenario."""
        self._responses[scenario] = candidates

    async def extract(
        self,
        *,
        messages: list[dict],
        subject_id: str,
    ) -> list[MemoryCandidate]:
        """Return cached responses based on message content."""
        # Build a scenario key from the messages
        key = self._build_key(messages)
        return self._responses.get(key, [])

    def _build_key(self, messages: list[dict]) -> str:
        """Build a scenario identifier from messages."""
        if not messages:
            return "__empty__"
        # Use the first user message content as a simple key
        for msg in messages:
            if msg.get("role") == "user":
                return msg.get("content", "")[:80]
        return messages[0].get("content", "")[:80]


class FakeExtractorFactory:
    """Factory for FakeExtractor."""

    def create(self, responses: dict[str, list[MemoryCandidate]] | None = None) -> FakeExtractor:
        return FakeExtractor(responses=responses)