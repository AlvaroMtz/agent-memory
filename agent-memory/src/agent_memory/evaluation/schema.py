"""Dataset schema — Pydantic models for test scenario definition.

Each scenario defines a self-contained test case with:
- context (tenant_id, subject_id, purpose)
- consent grants
- messages (conversation history)
- expected extraction results
- expected persistence state
- expected retrieval results
- expected audit events

Scenarios are serialized as YAML or JSONL under datasets/.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ScenarioConsent(BaseModel):
    """Consent definition for a scenario."""

    purpose: str = "testing"
    allow_write: bool = True
    allow_read: bool = True
    allowed_memory_types: list[str] = Field(default_factory=lambda: ["preference", "semantic"])
    allowed_sensitivity: list[str] = Field(default_factory=lambda: ["public", "internal"])
    retention_days: int | None = None


class ScenarioMessage(BaseModel):
    """A single message in the scenario conversation."""

    id: str
    role: str  # "user", "assistant", "trusted_tool", "system"
    content: str


class ExpectedCandidate(BaseModel):
    """Expected extraction output for a scenario."""

    memory_type: str | None = None
    subject_key: str | None = None
    predicate: str | None = None
    value: Any = None
    source_message_id: str | None = None
    explicitly_stated: bool | None = None
    sensitivity: str | None = None


class ExpectedMemory(BaseModel):
    """Expected persisted memory state."""

    memory_type: str | None = None
    subject_key: str | None = None
    predicate: str | None = None
    value: Any = None
    status: str = "active"
    version: int | None = None


class ScenarioAction(BaseModel):
    """Explicit setup action executed before assertions.

    Actions model state transitions that cannot be expressed by messages alone,
    such as revoking or expiring a persisted memory before retrieval checks.
    """

    action: str
    memory_type: str | None = None
    subject_key: str | None = None
    predicate: str | None = None
    status: str | None = None


class ExpectedQuery(BaseModel):
    """Expected retrieval query and results."""

    description: str = ""
    memory_type: str | None = None
    subject_key: str | None = None
    min_results: int = 0
    max_results: int | None = None
    expected_subject_keys: list[str] | None = None


class ExpectedAuditEvent(BaseModel):
    """Expected audit event in the log."""

    action: str | None = None
    actor_id: str | None = None
    memory_type: str | None = None


class EvaluationScenario(BaseModel):
    """A complete test scenario for the evaluation framework.

    Defines inputs (context, consent, messages) and expected outputs
    (candidates, persistence, retrieval, audit).
    """

    name: str
    description: str = ""

    # Inputs
    context: dict[str, Any] = Field(default_factory=dict)
    consent: ScenarioConsent = Field(default_factory=ScenarioConsent)
    messages: list[ScenarioMessage] = Field(default_factory=list)
    setup_actions: list[ScenarioAction] = Field(default_factory=list)

    # Expected outputs
    expected_candidates: list[ExpectedCandidate] = Field(default_factory=list)
    expected_memories: list[ExpectedMemory] = Field(default_factory=list)
    expected_queries: list[ExpectedQuery] = Field(default_factory=list)
    expected_audit: list[ExpectedAuditEvent] = Field(default_factory=list)

    # Metadata
    tags: list[str] = Field(default_factory=list)
    expected_to_fail: bool = False


class ScenarioResult(BaseModel):
    """Result of running a single scenario."""

    scenario_name: str
    passed: bool
    errors: list[str] = Field(default_factory=list)
    candidates_found: int = 0
    candidates_expected: int = 0
    memories_found: int = 0
    memories_expected: int = 0
    queries_passed: int = 0
    queries_total: int = 0
    duration_ms: float = 0.0


class EvaluationSuite(BaseModel):
    """A collection of scenarios run together."""

    name: str = "unnamed"
    scenarios: list[ScenarioResult] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    total_passed: int = 0
    total_failed: int = 0
    total_duration_ms: float = 0.0

    @property
    def results(self) -> list[ScenarioResult]:
        """Backward-compatible alias for scenario results."""
        return self.scenarios

    @results.setter
    def results(self, value: list[ScenarioResult]) -> None:
        self.scenarios = value
        self.total_passed = sum(1 for result in value if result.passed)
        self.total_failed = sum(1 for result in value if not result.passed)
        self.total_duration_ms = sum(result.duration_ms for result in value)

    @property
    def total_count(self) -> int:
        return len(self.scenarios)

    @property
    def pass_count(self) -> int:
        return self.total_passed

    def add_result(self, result: ScenarioResult) -> None:
        self.scenarios.append(result)
        if result.passed:
            self.total_passed += 1
        else:
            self.total_failed += 1
        self.total_duration_ms += result.duration_ms
