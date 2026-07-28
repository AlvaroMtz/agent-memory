"""Basic scenario runner — load datasets, run scenarios, assert expectations."""

from __future__ import annotations

import json
import time
from pathlib import Path

import yaml

from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.client import MemoryClient
from agent_memory.context import MemoryContext, TenantContext
from agent_memory.domain.audit import AuditQuery
from agent_memory.domain.consent import ConsentGrant
from agent_memory.evaluation.schema import (
    EvaluationScenario,
    EvaluationSuite,
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


async def run_scenario(
    scenario: EvaluationScenario,
    extractor: MemoryExtractor,
    backend: MemoryBackend | None = None,
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
    errors: list[str] = []
    candidates_found = 0
    candidates_expected = len(scenario.expected_candidates)
    memories_found = 0
    memories_expected = len(scenario.expected_memories)

    # Convert messages to dict format expected by extractors/client
    messages = [msg.model_dump() for msg in scenario.messages]

    subject_id = scenario.context.get("subject_id", "default-subject")
    tenant_id = scenario.context.get("tenant_id", "default")
    actor_id = scenario.context.get("actor_id", subject_id or "actor")
    purpose = scenario.context.get("purpose", scenario.consent.purpose)

    owns_backend = backend is None
    active_backend = backend or InMemoryBackend()
    if owns_backend:
        await active_backend.initialize()

    extracted_candidates: list[MemoryCandidate] = []
    memories_found = 0
    queries_passed = 0
    queries_total = len(scenario.expected_queries)

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
        await client.remember(context=context, messages=messages)
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

    # Check expected candidates
    candidates_found = len(extracted_candidates)
    if scenario.expected_candidates:
        for i, expected in enumerate(scenario.expected_candidates):
            matching = [
                c for c in extracted_candidates
                if (expected.memory_type is None or c.memory_type == expected.memory_type)
                and (expected.subject_key is None or c.subject_key == expected.subject_key)
                and (expected.predicate is None or c.predicate == expected.predicate)
                and (expected.value is None or c.value == expected.value)
                and (expected.source_message_id is None or c.source_message_id == expected.source_message_id)
                and (expected.explicitly_stated is None or c.explicitly_stated == expected.explicitly_stated)
                and (expected.sensitivity is None or c.sensitivity == expected.sensitivity)
            ]
            if not matching:
                errors.append(
                    f"Expected candidate #{i} (predicate={expected.predicate}, "
                    f"value={expected.value}) not found"
                )

    # Check expected memories against persisted records.
    if not errors:
        all_memories = await active_backend.list_memories(
            tenant_id=tenant_id,
            subject_id=subject_id,
            purpose=purpose,
            limit=100,
        )
        memories_found = len(all_memories)
        for i, expected in enumerate(scenario.expected_memories):
            matching_memories = [
                memory for memory in all_memories
                if (expected.memory_type is None or memory.memory_type == expected.memory_type)
                and (expected.subject_key is None or memory.subject_key == expected.subject_key)
                and (expected.predicate is None or memory.predicate == expected.predicate)
                and (expected.status is None or memory.status == expected.status)
            ]
            if not matching_memories:
                errors.append(
                    f"Expected memory #{i} (predicate={expected.predicate}, status={expected.status}) not found"
                )

    # Check retrieval expectations. The current schema has no query text, so the
    # runner uses an empty query fallback unless a future dataset adds one.
    if not errors and scenario.expected_queries:
        client = MemoryClient(active_backend, extractor=extractor, consent=active_backend)
        context = MemoryContext(
            tenant_id=tenant_id,
            subject_id=subject_id,
            actor_id=actor_id,
            purpose=purpose,
        )
        for expected_query in scenario.expected_queries:
            result = await client.retrieve(
                context=context,
                query=expected_query.description or "",
                filters={
                    "purpose": purpose,
                    "memory_types": [expected_query.memory_type] if expected_query.memory_type else None,
                },
            )
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

    # Check expected audit events by action.
    if not errors and scenario.expected_audit:
        audit_events = await active_backend.query_audit(AuditQuery(tenant_id=tenant_id, limit=500))
        for i, expected in enumerate(scenario.expected_audit):
            if expected.action and not any(event.action == expected.action for event in audit_events):
                errors.append(f"Expected audit event #{i} action={expected.action} not found")

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
        errors=errors,
    )


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

    status_actions = list(scenario.setup_actions)
    if not status_actions:
        status_actions = [
            expected for expected in scenario.expected_memories
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
        result = await run_scenario(scenario, extractor, backend)
        results.append(result)
    output.results = results
    return output
