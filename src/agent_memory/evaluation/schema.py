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
    rejection_reason: str | None = None


class ExpectedMemory(BaseModel):
    """Expected persisted memory state."""

    memory_type: str | None = None
    subject_key: str | None = None
    predicate: str | None = None
    value: Any = None
    status: str = "active"
    version: int | None = None


class ScenarioAction(BaseModel):
    """Explicit setup action executed before assertions."""

    action: str
    memory_type: str | None = None
    subject_key: str | None = None
    predicate: str | None = None
    status: str | None = None


class TenantOperation(BaseModel):
    """Explicit multi-tenant operation scenario."""

    operation: str
    tenant_id: str | None = None
    target_subject_id: str | None = None
    predicate: str | None = None
    expected_outcome: str = "denied"
    expected_error: str | None = None


class ExpectedQuery(BaseModel):
    """Expected retrieval query and results."""

    description: str = ""
    query: str | None = None
    memory_type: str | None = None
    subject_key: str | None = None
    min_results: int = 0
    max_results: int | None = None
    expected_subject_keys: list[str] | None = None
    expected_predicates: list[str] | None = None
    expected_memory_ids: list[str] | None = None
    expected_ranking: list[str] | None = None
    forbidden_predicates: list[str] = Field(default_factory=list)
    forbidden_memory_ids: list[str] = Field(default_factory=list)
    forbidden_tenants: list[str] = Field(default_factory=list)
    forbidden_statuses: list[str] = Field(default_factory=list)
    expected_counts: dict[str, int] = Field(default_factory=dict)
    forbidden_rejection_reasons: list[str] = Field(default_factory=list)
    expected_rejection_reasons: list[str] = Field(default_factory=list)
    # Extra query-level filters
    token_budget: int | None = None
    purpose: str | None = None


class ExpectedAuditEvent(BaseModel):
    """Expected audit event in the log."""

    action: str | None = None
    actor_id: str | None = None
    memory_type: str | None = None
    outcome: str | None = None
    reason: str | None = None


class InjectionRuntimeInvariant(BaseModel):
    """Runtime invariants after prompt injection is stored."""

    system_prompt_unchanged: bool = True
    tools_unchanged: bool = True
    permissions_unchanged: bool = True
    tenant_unchanged: bool = True
    confirmations_required: bool = True

    def check_invariants(self) -> bool:
        return all(
            [
                self.system_prompt_unchanged,
                self.tools_unchanged,
                self.permissions_unchanged,
                self.tenant_unchanged,
                self.confirmations_required,
            ]
        )


class EvaluationScenario(BaseModel):
    """A complete test scenario for the evaluation framework.

    Empty list semantics: [] means "must be exactly zero".
    None means "skip check" (default for all fields).
    """

    name: str
    description: str = ""

    context: dict[str, Any] = Field(default_factory=dict)
    consent: ScenarioConsent = Field(default_factory=ScenarioConsent)
    messages: list[ScenarioMessage] | None = None
    setup_actions: list[ScenarioAction] | None = None

    expected_candidates: list[ExpectedCandidate] | None = None
    expected_raw_candidates: list[ExpectedCandidate] | None = None
    expected_accepted_candidates: list[ExpectedCandidate] | None = None
    expected_rejected_candidates: list[ExpectedCandidate] | None = None
    expected_memories: list[ExpectedMemory] | None = None
    expected_queries: list[ExpectedQuery] | None = None
    expected_audit: list[ExpectedAuditEvent] | None = None
    expected_security_counters: dict[str, int] = Field(default_factory=dict)

    forbidden_predicates: list[str] | None = None
    forbidden_memory_ids: list[str] | None = None
    forbidden_tenants: list[str] | None = None
    forbidden_statuses: list[str] | None = None

    forbidden_accepted_candidates: list[ExpectedCandidate] | None = None
    forbidden_memories: list[ExpectedMemory] | None = None

    forbidden_memory_type: str | None = None
    forbidden_subject_keys: list[str] | None = None

    tenant_operations: list[TenantOperation] | None = None
    injection_invariants: InjectionRuntimeInvariant | None = None
    expected_counts: dict[str, int] = Field(default_factory=dict)
    expected_rejection_reasons: list[str] | None = None

    tags: list[str] | None = None
    expected_to_fail: bool = False

    @property
    def is_negative(self) -> bool:
        if (
            self.expected_accepted_candidates is not None
            and len(self.expected_accepted_candidates) == 0
        ):
            return True
        if self.expected_candidates is not None and len(self.expected_candidates) == 0:
            return True
        if self.forbidden_predicates:
            return True
        if self.forbidden_memories:
            return True
        if self.forbidden_accepted_candidates is not None:
            return True
        if self.forbidden_memory_type is not None:
            return True
        if any(m.status in ("revoked", "expired") for m in (self.expected_memories or [])):
            return True
        return False

    @property
    def has_strong_assertions(self) -> bool:
        """True when the scenario has at least one assertion type
        with a concrete value that can fail."""

        def _has(val) -> bool:
            """None means skip; [] means exactly zero (strong assertion)."""
            return val is not None

        return bool(
            _has(self.expected_candidates)
            or _has(self.expected_raw_candidates)
            or _has(self.expected_accepted_candidates)
            or _has(self.expected_rejected_candidates)
            or _has(self.expected_memories)
            or _has(self.expected_queries)
            or _has(self.expected_audit)
            or bool(self.expected_security_counters)
            or _has(self.forbidden_predicates)
            or _has(self.forbidden_memory_ids)
            or _has(self.forbidden_tenants)
            or _has(self.forbidden_statuses)
            or _has(self.forbidden_accepted_candidates)
            or _has(self.forbidden_memories)
            or self.forbidden_memory_type is not None
            or _has(self.forbidden_subject_keys)
            or _has(self.tenant_operations)
            # injection_invariants: only count as strong when explicitly set
            or (
                self.injection_invariants is not None
                and self.injection_invariants.check_invariants()
            )
            or bool(self.expected_counts)
            or _has(self.expected_rejection_reasons)
        )

    def count_mandatory_assertions(self) -> int:
        count = 0
        for field in [
            self.expected_candidates,
            self.expected_accepted_candidates,
            self.expected_rejected_candidates,
            self.expected_memories,
            self.expected_queries,
            self.expected_audit,
            self.expected_security_counters,
            self.forbidden_predicates,
            self.forbidden_memories,
            self.forbidden_accepted_candidates,
            self.forbidden_memory_type,
            self.expected_rejection_reasons,
            self.tenant_operations,
            self.injection_invariants,
            self.expected_counts,
        ]:
            if field is not None and field != {}:
                count += 1
        return count


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
    raw_candidates_found: int = 0
    accepted_candidates_found: int = 0
    rejected_candidates_found: int = 0
    persisted_memories_found: int = 0
    retrieved_memories_found: int = 0
    audit_events_found: int = 0
    rejected_reasons: list[str] = Field(default_factory=list)
    security_counters: dict[str, int] = Field(default_factory=dict)
    deterministic_seed: int | None = None
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
        return self.scenarios

    @results.setter
    def results(self, value: list[ScenarioResult]) -> None:
        self.scenarios = value
        self.total_passed = sum(1 for r in value if r.passed)
        self.total_failed = sum(1 for r in value if not r.passed)
        self.total_duration_ms = sum(r.duration_ms for r in value)

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
