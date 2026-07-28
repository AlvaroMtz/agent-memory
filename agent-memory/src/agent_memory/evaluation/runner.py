"""Basic scenario runner — load datasets, run scenarios, assert expectations."""

from __future__ import annotations

import json
import time
from pathlib import Path

import yaml

from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.domain.policies import validate_candidate
from agent_memory.evaluation.schema import (
    EvaluationScenario,
    EvaluationSuite,
    ScenarioResult,
)
from agent_memory.ports.backend import MemoryBackend
from agent_memory.ports.extractor import MemoryExtractor


def load_scenario(path: str | Path) -> EvaluationScenario:
    """Load a single scenario from a YAML or JSON file.

    Supports .yaml, .yml, and .json files.
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

    return EvaluationScenario(**data)


def load_dataset(directory: str | Path) -> list[EvaluationScenario]:
    """Load all scenarios from a directory of YAML/JSON files."""
    directory = Path(directory)
    scenarios: list[EvaluationScenario] = []

    for path in sorted(directory.iterdir()):
        if path.suffix in (".yaml", ".yml", ".json"):
            scenarios.append(load_scenario(path))

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

    # Convert messages to dict format expected by extractors
    messages = [msg.model_dump() for msg in scenario.messages]

    # Run extraction
    subject_id = scenario.context.get("subject_id", "default-subject")
    candidates = await extractor.extract(
        messages=messages,
        subject_id=subject_id,
    )

    # Check expected candidates
    candidates_found = len(candidates)
    if scenario.expected_candidates:
        for i, expected in enumerate(scenario.expected_candidates):
            matching = [
                c for c in candidates
                if (expected.predicate is None or c.predicate == expected.predicate)
                and (expected.value is None or c.value == expected.value)
            ]
            if not matching:
                errors.append(
                    f"Expected candidate #{i} (predicate={expected.predicate}, "
                    f"value={expected.value}) not found"
                )

    # Check expected memories (backend required)
    if scenario.expected_memories and backend is not None:
        all_memories = await backend.list_memories(
            tenant_id=scenario.context.get("tenant_id", "default"),
            subject_id=subject_id,
            limit=100,
        )
        memories_found = len(all_memories)

    duration_ms = (time.perf_counter() - start) * 1000

    # Determine pass/fail
    passed = len(errors) == 0
    if scenario.expected_to_fail:
        passed = not passed

    return ScenarioResult(
        scenario_name=scenario.name,
        passed=passed,
        errors=errors,
        candidates_found=candidates_found,
        candidates_expected=candidates_expected,
        memories_found=memories_found,
        memories_expected=memories_expected,
        queries_passed=0,
        queries_total=len(scenario.expected_queries),
        duration_ms=duration_ms,
    )


async def run_suite(
    scenarios: list[EvaluationScenario],
    extractor: MemoryExtractor,
    backend: MemoryBackend | None = None,
    suite_name: str = "evaluation",
) -> EvaluationSuite:
    """Run a complete evaluation suite.

    Args:
        scenarios: List of scenarios to run.
        extractor: The extractor to use.
        backend: Optional backend for persistence checks.
        suite_name: Name for the suite.

    Returns:
        EvaluationSuite with all results.
    """
    from datetime import datetime, timezone

    suite = EvaluationSuite(name=suite_name)
    suite.started_at = datetime.now(timezone.utc)

    for scenario in scenarios:
        result = await run_scenario(scenario, extractor, backend)
        suite.add_result(result)

    suite.finished_at = datetime.now(timezone.utc)
    return suite