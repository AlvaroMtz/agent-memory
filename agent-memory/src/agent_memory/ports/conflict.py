"""ConflictResolver port — abstract interface for contradiction detection."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.domain.memory import MemoryRecord
from agent_memory.constants import ContradictionClass


@runtime_checkable
class ConflictResolver(Protocol):
    """Port for detecting and resolving contradictions between memories."""

    async def classify(
        self,
        existing: MemoryRecord,
        candidate: MemoryCandidate,
    ) -> ContradictionClass:
        """Classify the relationship between an existing memory and a new candidate."""
        ...

    async def resolve(
        self,
        existing: MemoryRecord,
        candidate: MemoryCandidate,
        classification: ContradictionClass,
    ) -> str:
        """Determine what action to take based on the classification.

        Returns one of:
        - "skip": duplicate, no action needed
        - "supersede": mark existing as superseded, activate new
        - "flag": mark candidate as pending_review
        - "reject": reject the candidate
        """
        ...


class ConflictResolverFactory(Protocol):
    """Factory for creating ConflictResolver instances."""

    def create(self, **kwargs) -> ConflictResolver:
        ...