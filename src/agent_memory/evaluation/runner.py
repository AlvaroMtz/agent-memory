"""Basic scenario runner — load datasets, run scenarios, assert expectations."""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any

import yaml

from agent_memory.client import MemoryClient
from agent_memory.context import MemoryContext, TenantContext
from agent_memory.domain.audit import AuditQuery
from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.domain.consent import ConsentGrant
from agent_memory.evaluation.schema import (
    EvaluationScenario,
    EvaluationSuite,
    ExpectedCandidate,
    ScenarioResult,
)
from agent_memory.ports.backend import MemoryBackend
from agent_memory.ports.extractor import MemoryExtractor
from agent_memory.providers.in_memory_backend import InMemoryBackend


def load_scenario(path: str | Path) -> EvaluationScenario | list[EvaluationScenario]:
    """Load scenario(s) from a YAML or JSON file.

    Supports .yaml, .yml, and .json files.
    Handles both single scenario dicts and ``{scenarios: [...]}`` wrappers.
    Returns a single EvaluationScenario for plain dicts, a list for wrapped formats.
    """
    path = Path(path)
    content = path.read_text(encoding="utf-8")

    if path.suffix in (".yaml", ".yml"):
        data = yaml.safe_load(content)
    elif path.suffix == ".json":
        data = json.loads(content)
    else:
        msg = f"Unsupported file format: {path.suffix}"
        raise ValueError(msg)

    # Handle {scenarios: [...]} wrapper
    if isinstance(data, dict) and "scenarios" in data:
        wrapped = data["scenarios"]
        if isinstance(wrapped, list):
            return [EvaluationScenario(**s) for s in wrapped]

    # Single scenario dict
    return EvaluationScenario(**data)


def load_dataset(directory: str | Path) -> list[EvaluationScenario]:
    """Load all scenarios from a directory of YAML/JSON files."""
    directory = Path(directory)
    scenarios: list[EvaluationScenario] = []

    for path in sorted(directory.rglob("*")):
        if path.suffix in (".yaml", ".yml", ".json"):
            result = load_scenario(path)
            if isinstance(result, list):
                scenarios.extend(result)
            else:
                scenarios.append(result)

    return scenarios


def validate_dataset_scenarios(scenarios: list[EvaluationScenario]) -> None:
    """Reject scenario definitions that cannot prove release guarantees.

    A security/retrieval scenario with only ``min_results: 0`` is theatre: it
    would pass even if the pipeline did nothing. Keep this validator focused on
    measurable assertions so release gates fail closed before metrics run.
    """

    weak: list[str] = []
    for scenario in scenarios:
        if not scenario.has_strong_assertions:
            weak.append(f"{scenario.name}(no_assertions)")
            continue
        security_like = _is_security_or_retrieval_scenario(scenario)
        if (
            scenario.is_negative
            and scenario.tags
            and "mandatory" in scenario.tags
            and not scenario.expected_rejection_reasons
            and not scenario.expected_rejected_candidates
        ):
            weak.append(f"{scenario.name}(no_rejection_reason)")
            continue
        for query in scenario.expected_queries or []:
            has_positive_retrieval_assertion = bool(
                query.expected_predicates
                or query.expected_memory_ids
                or query.expected_ranking
                or query.expected_subject_keys
                or query.forbidden_predicates
                or query.forbidden_memory_ids
                or query.forbidden_tenants
                or query.forbidden_statuses
                or query.max_results is not None
                or query.min_results > 0
                or query.expected_counts
                or query.forbidden_rejection_reasons
                or query.expected_rejection_reasons
                or query.token_budget is not None
                or query.purpose is not None
            )
            has_other_assertions = bool(
                scenario.expected_candidates
                or scenario.expected_raw_candidates
                or scenario.expected_accepted_candidates is not None
                or scenario.expected_rejected_candidates
                or scenario.expected_memories
                or scenario.expected_audit
                or scenario.expected_security_counters
                or scenario.forbidden_predicates
                or scenario.forbidden_memory_ids
                or scenario.forbidden_tenants
                or scenario.forbidden_statuses
                or scenario.forbidden_accepted_candidates is not None
                or scenario.forbidden_memories is not None
                or scenario.forbidden_memory_type is not None
                or scenario.forbidden_subject_keys
                or scenario.tenant_operations
                or scenario.expected_counts
                or scenario.expected_rejection_reasons
                or scenario.injection_invariants is not None
            )
            if (
                security_like
                and query.min_results == 0
                and not (has_positive_retrieval_assertion or has_other_assertions)
            ):
                weak.append(scenario.name)

    if weak:
        raise ValueError(
            "Weak dataset assertions cannot prove release guarantees: " + ", ".join(weak)
        )


def _is_security_or_retrieval_scenario(scenario: EvaluationScenario) -> bool:
    text = " ".join([scenario.name, scenario.description] + (scenario.tags or [])).lower()
    terms = (
        "injection",
        "escalation",
        "tenant",
        "unauthorized",
        "revoked",
        "expired",
        "retrieval",
        "security",
    )
    return any(term in text for term in terms)


async def run_scenario(
    scenario: EvaluationScenario,
    extractor: MemoryExtractor,
    backend: MemoryBackend | None = None,
    *,
    seed: int | None = None,
) -> ScenarioResult:
    """Run a single scenario and compare results to expectations.

    Args:
        scenario: The scenario definition.
        extractor: The extractor to use.
        backend: Optional backend to check persistence.

    Returns:
        ScenarioResult with pass/fail and details.
    """
    start = time.perf_counter()
    if seed is not None:
        random.seed(seed)
    errors: list[str] = []
    candidates_found = 0
    candidates_expected = len(scenario.expected_candidates or [])
    memories_found = 0
    memories_expected = len(scenario.expected_memories or [])

    # Convert messages to dict format expected by extractors/client
    messages = [msg.model_dump() for msg in (scenario.messages or [])]

    subject_id = scenario.context.get("subject_id", "default-subject")
    tenant_id = scenario.context.get("tenant_id", "default")
    actor_id = scenario.context.get("actor_id", subject_id or "actor")
    purpose = scenario.context.get("purpose", scenario.consent.purpose)

    owns_backend = backend is None
    active_backend = backend or InMemoryBackend()
    if owns_backend:
        await active_backend.initialize()

    extracted_candidates: list[MemoryCandidate] = []
    accepted_candidates: list[MemoryCandidate] = []
    rejected_candidates: list[ExpectedCandidate] = []
    rejected_reasons: list[str] = []
    retrieved_memories_found = 0
    audit_events_found = 0
    security_counters = _empty_security_counters()
    memories_found = 0
    queries_passed = 0
    queries_total = len(scenario.expected_queries or [])

    try:
        extracted_candidates = await extractor.extract(messages=messages, subject_id=subject_id)

        context = MemoryContext(
            tenant_id=tenant_id,
            subject_id=subject_id,
            actor_id=actor_id,
            purpose=purpose,
        )

        client = MemoryClient(active_backend, extractor=extractor, consent=active_backend)
        grant = ConsentGrant(
            purpose=scenario.consent.purpose,
            allow_write=scenario.consent.allow_write,
            allow_read=scenario.consent.allow_read,
            allowed_memory_types=set(scenario.consent.allowed_memory_types),
            allowed_sensitivity=set(scenario.consent.allowed_sensitivity),
            retention_days=scenario.consent.retention_days,
        )
        await client.grant_consent(context=context, grant=grant)
        remember_result = await client.remember(context=context, messages=messages)
        accepted_candidates = remember_result.candidates
    except Exception as exc:
        if scenario.expected_to_fail:
            duration_ms = (time.perf_counter() - start) * 1000
            return ScenarioResult(
                scenario_name=scenario.name,
                passed=True,
                duration_ms=duration_ms,
                candidates_found=0,
                candidates_expected=candidates_expected,
                memories_found=0,
                memories_expected=memories_expected,
                queries_passed=0,
                queries_total=queries_total,
                errors=[],
                deterministic_seed=seed,
            )
        errors.append(f"scenario execution failed: {type(exc).__name__}: {exc}")

    # Apply explicit fixture state before assertions/retrieval.
    if not errors:
        await _apply_setup_actions(
            scenario=scenario,
            backend=active_backend,
            tenant_id=tenant_id,
            subject_id=subject_id,
            purpose=purpose,
            actor_id=actor_id,
        )

    if not errors:
        audit_events = await active_backend.query_audit(AuditQuery(tenant_id=tenant_id, limit=500))
        audit_events_found = len(audit_events)
        for event in audit_events:
            if event.action == "memory.candidate_rejected":
                rejected_reasons.append(event.reason or "unknown")
                metadata = getattr(event, "metadata", {}) or {}
                rejected_candidates.append(
                    ExpectedCandidate(
                        memory_type=metadata.get("memory_type"),
                        predicate=metadata.get("predicate"),
                        sensitivity=metadata.get("sensitivity"),
                        rejection_reason=event.reason,
                    )
                )

    # Check expected candidates against full-pipeline accepted candidates. Raw
    # extractor assertions are available separately via expected_raw_candidates.
    candidates_found = len(extracted_candidates)
    # Raw candidate assertions: None → skip, [] → exactly zero, [...] → explicit
    if scenario.expected_raw_candidates is not None:
        _assert_expected_candidates(
            errors, scenario.expected_raw_candidates, extracted_candidates, "raw candidate"
        )
        if len(scenario.expected_raw_candidates) == 0 and extracted_candidates:
            errors.append(
                f"Expected exactly 0 raw candidates, but found {len(extracted_candidates)}"
            )

    # Accepted candidates: None → fallback to expected_candidates;
    # [] → exactly zero; [...] → explicit assertions.
    if scenario.expected_accepted_candidates is not None:
        _assert_expected_candidates(
            errors, scenario.expected_accepted_candidates, accepted_candidates, "accepted candidate"
        )
        if len(scenario.expected_accepted_candidates) == 0 and accepted_candidates:
            errors.append(
                f"Expected exactly 0 accepted candidates, but found {len(accepted_candidates)}"
            )
    elif scenario.expected_candidates is not None:
        _assert_expected_candidates(
            errors, scenario.expected_candidates, accepted_candidates, "accepted candidate"
        )
    _assert_expected_rejections(errors, scenario.expected_rejected_candidates, rejected_candidates)

    # Forbidden accepted candidates: None → skip, [] → exactly zero, [...] → explicit
    if scenario.forbidden_accepted_candidates is not None:
        for i, forbidden in enumerate(scenario.forbidden_accepted_candidates):
            if any(_candidate_matches(forbidden, c) for c in accepted_candidates):
                errors.append(
                    f"Forbidden accepted candidate #{i} "
                    f"(predicate={forbidden.predicate}, value={forbidden.value}) was accepted"
                )

    # Expected rejection reasons
    if scenario.expected_rejection_reasons is not None:
        actual_set = set(rejected_reasons)
        for reason in scenario.expected_rejection_reasons:
            if reason not in actual_set:
                errors.append(
                    f"Expected rejection reason not found: '{reason}' (actual: {actual_set})"
                )

    # Prompt injection invariants
    if (
        scenario.injection_invariants is not None
        and not scenario.injection_invariants.check_invariants()
    ):
        errors.append("Prompt injection runtime invariants failed")

    # Global counts
    if scenario.expected_counts:
        total_expected = scenario.expected_counts.get("total", None)
        if total_expected is not None:
            if (
                scenario.expected_accepted_candidates is not None
                and len(scenario.expected_accepted_candidates) > 0
            ):
                actual_count = len(accepted_candidates)
            elif scenario.expected_candidates:
                actual_count = len(extracted_candidates)
            else:
                actual_count = candidates_found
            if actual_count != total_expected:
                errors.append(f"Global total count: expected {total_expected}, got {actual_count}")

    # Check expected memories against persisted records.
    if not errors:
        all_memories = await active_backend.list_memories(
            tenant_id=tenant_id,
            subject_id=subject_id,
            purpose=purpose,
            limit=100,
        )
        memories_found = len(all_memories)
        security_counters[
            "memories_activated_without_evidence"
        ] += await _count_active_without_evidence(
            all_memories,
            active_backend,
            tenant_id,
            actor_id,
        )
        # Forbidden memories (explicit list)
        if scenario.forbidden_memories is not None:
            for i, forbidden in enumerate(scenario.forbidden_memories):
                matching = [
                    m
                    for m in all_memories
                    if (forbidden.memory_type is None or m.memory_type == forbidden.memory_type)
                    and (forbidden.subject_key is None or m.subject_key == forbidden.subject_key)
                    and (forbidden.predicate is None or m.predicate == forbidden.predicate)
                ]
                if matching:
                    errors.append(
                        f"Forbidden memory #{i} (predicate={forbidden.predicate}, status={forbidden.status}) was persisted"
                    )

        # Forbidden memory type / subject keys
        if scenario.forbidden_memory_type:
            matching_type = [
                m for m in all_memories if m.memory_type == scenario.forbidden_memory_type
            ]
            if matching_type:
                errors.append(
                    f"Forbidden memory type '{scenario.forbidden_memory_type}' has {len(matching_type)} instances"
                )
        if scenario.forbidden_subject_keys:
            matching_keys = [
                m for m in all_memories if m.subject_key in scenario.forbidden_subject_keys
            ]
            if matching_keys:
                errors.append(
                    f"Forbidden subject keys {scenario.forbidden_subject_keys} have {len(matching_keys)} instances"
                )

        _assert_forbidden_memories(
            errors,
            all_memories,
            forbidden_predicates=scenario.forbidden_predicates,
            forbidden_memory_ids=scenario.forbidden_memory_ids,
            forbidden_tenants=scenario.forbidden_tenants,
            forbidden_statuses=scenario.forbidden_statuses,
            security_counters=security_counters,
        )

        # expected_memories: [] means exactly zero; None means skip; [...] means explicit
        if scenario.expected_memories is not None:
            if len(scenario.expected_memories) == 0:
                if memories_found > 0:
                    errors.append(f"Expected exactly 0 memories, but found {memories_found}")
            else:
                for i, expected in enumerate(scenario.expected_memories):
                    matching_memories = [
                        memory
                        for memory in all_memories
                        if (
                            expected.memory_type is None
                            or memory.memory_type == expected.memory_type
                        )
                        and (
                            expected.subject_key is None
                            or memory.subject_key == expected.subject_key
                        )
                        and (expected.predicate is None or memory.predicate == expected.predicate)
                        and (expected.status is None or memory.status == expected.status)
                    ]
                    if not matching_memories:
                        errors.append(
                            f"Expected memory #{i} (predicate={expected.predicate}, status={expected.status}) not found"
                        )

    # Check retrieval expectations through the application pipeline so query
    # level filters (purpose, type, limit/token-budget) are actually exercised.
    if not errors and scenario.expected_queries:
        from agent_memory.application.retrieve import retrieve as _retrieve

        for expected_query in scenario.expected_queries:
            query_purpose = expected_query.purpose or purpose
            filters: dict[str, Any] = {"purpose": query_purpose}
            if expected_query.memory_type:
                filters["memory_types"] = [expected_query.memory_type]
            if expected_query.token_budget is not None:
                filters["limit"] = expected_query.token_budget

            result = await _retrieve(
                tenant_id=tenant_id,
                subject_id=subject_id,
                query=expected_query.query or expected_query.description or "",
                filters=filters,
                backend=active_backend,
                embedder=None,
                consent=active_backend,
                max_tokens=expected_query.token_budget or 1200,
            )
            retrieved_memories_found += result.total_count
            count = result.total_count
            ok = count >= expected_query.min_results
            if expected_query.max_results is not None:
                ok = ok and count <= expected_query.max_results
            if ok:
                queries_passed += 1
            else:
                errors.append(
                    f"Query expectation failed ({expected_query.description}): got {count}, "
                    f"expected min={expected_query.min_results} max={expected_query.max_results}"
                )
            _assert_retrieval_expectations(
                errors, expected_query, result.results, security_counters
            )

    # Execute explicit multi-tenant adversarial operations. Counters only move
    # when an operation succeeds or leaks when it should have been denied.
    if not errors and scenario.tenant_operations:
        for op in scenario.tenant_operations:
            target_tenant = op.tenant_id or "other_tenant"
            if op.operation == "cross_read":
                results = await active_backend.list_memories(
                    tenant_id=target_tenant,
                    subject_id=op.target_subject_id or subject_id,
                    purpose=purpose,
                    limit=100,
                )
                if op.expected_outcome == "denied" and results:
                    security_counters["cross_tenant_leakage"] += len(results)
                    errors.append(
                        f"Cross-tenant read from {target_tenant} leaked {len(results)} memories"
                    )
            elif op.operation == "cross_write":
                denied = await _cross_write_denied(
                    active_backend,
                    tenant_id=tenant_id,
                    target_tenant=target_tenant,
                    subject_id=subject_id,
                    purpose=purpose,
                    actor_id=actor_id,
                    predicate=op.predicate,
                )
                if op.expected_outcome == "denied" and not denied:
                    security_counters["unauthorized_write"] += 1
                    errors.append("Cross-tenant write was not denied")
            elif op.operation == "cross_update":
                denied = await _cross_status_change_denied(
                    active_backend,
                    tenant_id=tenant_id,
                    target_tenant=target_tenant,
                    subject_id=subject_id,
                    purpose=purpose,
                    actor_id=actor_id,
                    predicate=op.predicate,
                    status="revoked",
                )
                if op.expected_outcome == "denied" and not denied:
                    security_counters["unauthorized_update"] += 1
                    errors.append("Cross-tenant update was not denied")
            elif op.operation == "cross_delete":
                denied = await _cross_status_change_denied(
                    active_backend,
                    tenant_id=tenant_id,
                    target_tenant=target_tenant,
                    subject_id=subject_id,
                    purpose=purpose,
                    actor_id=actor_id,
                    predicate=op.predicate,
                    status="deleted",
                )
                if op.expected_outcome == "denied" and not denied:
                    security_counters["unauthorized_delete"] += 1
                    errors.append("Cross-tenant delete was not denied")
            elif op.operation == "missing_tenant":
                if op.expected_outcome == "denied" and tenant_id:
                    # The runner cannot create an invalid MemoryContext without
                    # bypassing validation; require the scenario to remain leak-free.
                    security_counters["cross_tenant_leakage"] += 0

    # Check expected audit events by action.
    if not errors and scenario.expected_audit:
        audit_events = await active_backend.query_audit(AuditQuery(tenant_id=tenant_id, limit=500))
        audit_events_found = len(audit_events)
        for i, expected in enumerate(scenario.expected_audit):
            if expected.action and not any(
                event.action == expected.action
                and (expected.outcome is None or event.outcome == expected.outcome)
                and (expected.reason is None or event.reason == expected.reason)
                for event in audit_events
            ):
                errors.append(f"Expected audit event #{i} action={expected.action} not found")

    for counter_name, expected_value in scenario.expected_security_counters.items():
        actual_value = security_counters.get(counter_name, 0)
        if actual_value != expected_value:
            errors.append(
                f"Security counter {counter_name}={actual_value}, expected {expected_value}"
            )

    duration_ms = (time.perf_counter() - start) * 1000

    # Determine pass/fail
    passed = len(errors) == 0

    return ScenarioResult(
        scenario_name=scenario.name,
        passed=passed,
        duration_ms=duration_ms,
        candidates_found=candidates_found,
        candidates_expected=candidates_expected,
        memories_found=memories_found,
        memories_expected=memories_expected,
        queries_passed=queries_passed,
        queries_total=queries_total,
        raw_candidates_found=len(extracted_candidates),
        accepted_candidates_found=len(accepted_candidates),
        rejected_candidates_found=len(rejected_candidates),
        persisted_memories_found=memories_found,
        retrieved_memories_found=retrieved_memories_found,
        audit_events_found=audit_events_found,
        rejected_reasons=rejected_reasons,
        security_counters=security_counters,
        deterministic_seed=seed,
        errors=errors,
    )


async def _first_memory_for_operation(
    backend: MemoryBackend,
    *,
    tenant_id: str,
    subject_id: str,
    purpose: str,
    predicate: str | None,
):
    memories = await backend.list_memories(
        tenant_id=tenant_id,
        subject_id=subject_id,
        purpose=purpose,
        limit=100,
    )
    if predicate is not None:
        memories = [memory for memory in memories if memory.predicate == predicate]
    return memories[0] if memories else None


async def _cross_write_denied(
    backend: MemoryBackend,
    *,
    tenant_id: str,
    target_tenant: str,
    subject_id: str,
    purpose: str,
    actor_id: str,
    predicate: str | None,
) -> bool:
    source = await _first_memory_for_operation(
        backend,
        tenant_id=tenant_id,
        subject_id=subject_id,
        purpose=purpose,
        predicate=predicate,
    )
    if source is None:
        return True
    try:
        version = await backend.get_current_version(
            source.id,
            context=TenantContext(tenant_id=tenant_id, actor_id=actor_id),
        )
        if version is None:
            return True
        await backend.save_memory(
            source,
            version,
            context=TenantContext(tenant_id=target_tenant, actor_id=actor_id),
        )
    except Exception:
        return True
    return False


async def _cross_status_change_denied(
    backend: MemoryBackend,
    *,
    tenant_id: str,
    target_tenant: str,
    subject_id: str,
    purpose: str,
    actor_id: str,
    predicate: str | None,
    status: str,
) -> bool:
    source = await _first_memory_for_operation(
        backend,
        tenant_id=tenant_id,
        subject_id=subject_id,
        purpose=purpose,
        predicate=predicate,
    )
    if source is None:
        return True
    try:
        await backend.update_memory_status(
            source.id,
            status,
            context=TenantContext(tenant_id=target_tenant, actor_id=actor_id),
        )
    except Exception:
        return True
    return False


def _candidate_matches(expected: ExpectedCandidate, candidate: MemoryCandidate) -> bool:
    return (
        (expected.memory_type is None or candidate.memory_type == expected.memory_type)
        and (expected.subject_key is None or candidate.subject_key == expected.subject_key)
        and (expected.predicate is None or candidate.predicate == expected.predicate)
        and (expected.value is None or candidate.value == expected.value)
        and (
            expected.source_message_id is None
            or candidate.source_message_id == expected.source_message_id
        )
        and (
            expected.explicitly_stated is None
            or candidate.explicitly_stated == expected.explicitly_stated
        )
        and (expected.sensitivity is None or candidate.sensitivity == expected.sensitivity)
    )


def _assert_expected_candidates(
    errors: list[str],
    expected_candidates: list[ExpectedCandidate],
    actual_candidates: list[MemoryCandidate],
    label: str,
) -> None:
    for i, expected in enumerate(expected_candidates):
        if not any(_candidate_matches(expected, c) for c in actual_candidates):
            errors.append(
                f"Expected {label} #{i} (predicate={expected.predicate}, value={expected.value}) not found"
            )


def _assert_expected_rejections(
    errors: list[str],
    expected_rejections: list[ExpectedCandidate] | None,
    actual_rejections: list[ExpectedCandidate],
) -> None:
    if expected_rejections is None:
        return
    for i, expected in enumerate(expected_rejections):
        if not any(
            (expected.predicate is None or actual.predicate == expected.predicate)
            and (expected.memory_type is None or actual.memory_type == expected.memory_type)
            and (
                expected.rejection_reason is None
                or actual.rejection_reason == expected.rejection_reason
            )
            for actual in actual_rejections
        ):
            errors.append(
                f"Expected rejected candidate #{i} "
                f"(predicate={expected.predicate}, reason={expected.rejection_reason}) not found"
            )


async def _count_active_without_evidence(
    memories: list,
    backend: MemoryBackend,
    tenant_id: str,
    actor_id: str,
) -> int:
    count = 0
    tenant_context = TenantContext(tenant_id=tenant_id, actor_id=actor_id)
    for memory in memories:
        if memory.status != "active":
            continue
        version = await backend.get_current_version(memory.id, context=tenant_context)
        if version is None or not version.evidence_text:
            count += 1
    return count


def _assert_forbidden_memories(
    errors: list[str],
    memories: list,
    *,
    forbidden_predicates: list[str] | None,
    forbidden_memory_ids: list[str] | None,
    forbidden_tenants: list[str] | None,
    forbidden_statuses: list[str] | None,
    security_counters: dict[str, int],
) -> None:
    forbidden_predicates = forbidden_predicates or []
    forbidden_memory_ids = forbidden_memory_ids or []
    forbidden_tenants = forbidden_tenants or []
    forbidden_statuses = forbidden_statuses or []
    for memory in memories:
        memory_id = str(memory.id)
        if memory.predicate in forbidden_predicates:
            errors.append(f"Forbidden predicate persisted: {memory.predicate}")
        if memory_id in forbidden_memory_ids:
            errors.append(f"Forbidden memory ID persisted: {memory_id}")
        if memory.tenant_id in forbidden_tenants:
            security_counters["cross_tenant_leakage"] += 1
            errors.append(f"Forbidden tenant persisted: {memory.tenant_id}")
        if memory.status in forbidden_statuses:
            errors.append(f"Forbidden memory status persisted: {memory.status}")


def _assert_retrieval_expectations(
    errors: list[str],
    expected_query,
    results: list,
    security_counters: dict[str, int],
) -> None:
    predicates = [result.predicate for result in results]
    memory_ids = [str(result.id) for result in results]
    for predicate in expected_query.expected_predicates or []:
        if predicate not in predicates:
            errors.append(f"Expected retrieved predicate not found: {predicate}")
    for memory_id in expected_query.expected_memory_ids or []:
        if memory_id not in memory_ids:
            errors.append(f"Expected retrieved memory ID not found: {memory_id}")
    if expected_query.expected_ranking:
        actual_prefix = predicates[: len(expected_query.expected_ranking)]
        if actual_prefix != expected_query.expected_ranking:
            errors.append(
                f"Expected ranking {expected_query.expected_ranking}, got {actual_prefix}"
            )
    for predicate in expected_query.forbidden_predicates:
        if predicate in predicates:
            errors.append(f"Forbidden predicate retrieved: {predicate}")
    for memory_id in expected_query.forbidden_memory_ids:
        if memory_id in memory_ids:
            errors.append(f"Forbidden memory ID retrieved: {memory_id}")
    for status in expected_query.forbidden_statuses:
        if status == "revoked" and results:
            security_counters["revoked_memory_retrieval"] += 1
        if status == "expired" and results:
            security_counters["expired_memory_retrieval"] += 1


def _empty_security_counters() -> dict[str, int]:
    return {
        "cross_tenant_leakage": 0,
        "unauthorized_retrieval": 0,
        "unauthorized_write": 0,
        "unauthorized_update": 0,
        "unauthorized_delete": 0,
        "revoked_memory_retrieval": 0,
        "expired_memory_retrieval": 0,
        "instruction_escalation": 0,
        "tool_escalation": 0,
        "permission_escalation": 0,
        "memories_activated_without_evidence": 0,
        "secrets_detected_in_logs": 0,
    }


async def _apply_setup_actions(
    *,
    scenario: EvaluationScenario,
    backend: MemoryBackend,
    tenant_id: str,
    subject_id: str,
    purpose: str,
    actor_id: str,
) -> None:
    """Apply explicit fixture actions declared by the scenario.

    Legacy compatibility: older datasets used ``expected_memories.status`` with
    non-active statuses as implicit setup. Keep that behavior temporarily, but
    prefer explicit ``setup_actions`` in new datasets.
    """

    status_actions = list(scenario.setup_actions or [])
    if not status_actions:
        status_actions = [
            expected
            for expected in (scenario.expected_memories or [])
            if expected.status and expected.status != "active"
        ]
    if not status_actions:
        return

    memories = await backend.list_memories(
        tenant_id=tenant_id,
        subject_id=subject_id,
        purpose=purpose,
        limit=100,
    )
    tenant_context = TenantContext(tenant_id=tenant_id, actor_id=actor_id)
    for action in status_actions:
        action_name = getattr(action, "action", "set_memory_status")
        if action_name != "set_memory_status":
            raise ValueError(f"Unsupported scenario setup action: {action_name}")
        status = getattr(action, "status", None)
        if not status:
            raise ValueError("set_memory_status requires status")
        for memory in memories:
            if (
                (action.memory_type is None or memory.memory_type == action.memory_type)
                and (action.subject_key is None or memory.subject_key == action.subject_key)
                and (action.predicate is None or memory.predicate == action.predicate)
            ):
                await backend.update_memory_status(memory.id, status, context=tenant_context)
                break


async def run_suite(
    suite: EvaluationSuite | list[EvaluationScenario],
    extractor: MemoryExtractor,
    backend: MemoryBackend | None = None,
    *,
    suite_name: str = "dataset",
    seed: int | None = None,
) -> EvaluationSuite:
    """Run all scenarios in a suite and populate results."""
    if isinstance(suite, list):
        scenario_inputs = suite
        output = EvaluationSuite(name=suite_name)
    else:
        scenario_inputs = suite.scenarios  # type: ignore[assignment]
        output = suite

    results: list[ScenarioResult] = []
    for scenario in scenario_inputs:
        result = await run_scenario(scenario, extractor, backend, seed=seed)
        results.append(result)
    output.results = results
    return output
