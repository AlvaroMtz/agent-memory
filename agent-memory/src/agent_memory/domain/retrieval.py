"""Retrieval models — results of a memory retrieval operation."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class RetrievedMemory(BaseModel):
    """A single memory returned from a retrieval operation."""

    id: UUID
    version: int
    memory_type: str
    predicate: str
    value: Any

    score: float
    score_breakdown: dict[str, float]

    confidence: float
    source_type: str
    sensitivity: str
    created_at: datetime

    searchable_summary: str = ""
    evidence_text: str | None = None


class RetrievalResult(BaseModel):
    """Complete result of a memory retrieval operation."""

    query: str
    results: list[RetrievedMemory]
    total_count: int
    token_count: int
    token_budget: int
    retrieval_id: str | None = None

    @property
    def empty(self) -> bool:
        return len(self.results) == 0


class ScoreBreakdown(BaseModel):
    """Detailed score breakdown for a single retrieved memory."""

    vector_score: float = 0.0
    lexical_score: float = 0.0
    recency_score: float = 0.0
    confidence_score: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.vector_score * 0.4
            + self.lexical_score * 0.3
            + self.recency_score * 0.15
            + self.confidence_score * 0.15
        )