"""Concrete ConflictResolver implementation — detection and resolution of
contradictions between memory candidates and existing memory records.

Uses the classify_contradiction function from domain/policies.py and
resolves contradictions according to the ConflictResolver port protocol.
"""

from __future__ import annotations

from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.domain.memory import MemoryRecord
from agent_memory.domain.policies import classify_contradiction


class ContradictionResolver:
    """Concrete resolver that classifies contradictions and determines actions.

    Resolution actions:
    - duplicate → skip (candidate is identical to existing memory)
    - supports → accept (new info supports existing memory)
    - supersedes → supersede (preference change overrides old value)
    - contradicts → flag (conflicting semantic facts → pending_review)
    - unrelated → accept (different subject, no conflict)
    """

    async def classify(
        self,
        existing: MemoryRecord,
        candidate: MemoryCandidate,
        existing_value: object | None = None,
    ) -> str:
        """Classify the relationship between an existing memory and a new candidate.

        Delegates to the domain-level classify_contradiction function.
        Args:
            existing: The existing memory record.
            candidate: The new candidate.
            existing_value: Optional existing version value for value comparison.
        Returns one of: duplicate, supports, supersedes, contradicts, unrelated
        """
        return classify_contradiction(existing, candidate, existing_value=existing_value)

    async def resolve(
        self,
        existing: MemoryRecord,
        candidate: MemoryCandidate,
        classification: str,
    ) -> str:
        """Determine the action to take based on the classification.

        Args:
            existing: The existing memory record.
            candidate: The new candidate.
            classification: Result from classify().

        Returns:
            One of: "skip", "supersede", "flag", "reject"
        """
        mapping = {
            "duplicate": "skip",
            "supports": "accept",
            "supersedes": "supersede",
            "contradicts": "flag",
            "unrelated": "accept",
        }
        return mapping.get(classification, "reject")


class ContradictionResolverFactory:
    """Factory for creating ContradictionResolver instances."""

    def create(self, **kwargs) -> ContradictionResolver:
        return ContradictionResolver()
