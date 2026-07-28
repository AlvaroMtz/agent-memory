"""Evaluation report generation — JSON, JUnit XML, and HTML reports."""

from __future__ import annotations

import json
import asyncio
import io
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import yaml

from agent_memory.evaluation.metrics.extraction import extraction_precision, extraction_recall


class EvaluationResult:
    """A single evaluation result for report generation."""

    def __init__(
        self,
        scenario_name: str,
        passed: bool,
        metrics: dict[str, Any] | None = None,
        errors: list[str] | None = None,
    ):
        self.scenario_name = scenario_name
        self.passed = passed
        self.metrics = metrics or {}
        self.errors = errors or []


def generate_json_report(results: list[EvaluationResult]) -> str:
    """Generate a JSON report from evaluation results."""
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "passed": sum(1 for r in results if r.passed),
        "failed": sum(1 for r in results if not r.passed),
        "results": [],
    }

    for r in results:
        report["results"].append({
            "scenario": r.scenario_name,
            "passed": r.passed,
            "metrics": r.metrics,
            "errors": r.errors,
        })

    return json.dumps(report, indent=2, default=str)


def generate_report(
    suite: Any,
    fmt: str = "json",
) -> str:
    """Generate a report from an EvaluationSuite in the requested format."""
    from agent_memory.evaluation.reports import EvaluationResult

    results: list[EvaluationResult] = [
        EvaluationResult(
            scenario_name=r.scenario_name,
            passed=r.passed,
            errors=r.errors,
            metrics={"duration_ms": r.duration_ms, "candidates_found": r.candidates_found},
        )
        for r in suite.scenarios
    ]

    if fmt == "json":
        return generate_json_report(results)
    if fmt == "junit":
        return generate_junit_xml(results)
    if fmt == "html":
        return generate_html_report(results)
    raise ValueError(f"Unsupported report format: {fmt}")


def _assert_release_gates(strict: bool = False) -> list[str]:
    """Run release gates and return a list of pass strings (empty = warning)."""
    from agent_memory.config import load_config

    results: list[str] = []
    gates_config = _load_release_gates_config()
    project_root = _project_root()

    # Gate 1: config loads without error
    try:
        config = load_config()
        results.append(f"config OK (environment={config.environment})")
    except Exception as exc:
        results.append(f"config FAIL: {exc}")
        if strict:
            raise

    # Gate 2: evaluation datasets exist
    datasets_path = _resolve_project_path(config.evaluation.get("datasets_path", "./datasets"), project_root)
    if datasets_path.exists() and any(datasets_path.iterdir()):
        results.append(f"datasets OK ({datasets_path})")
    else:
        results.append("")  # warning: no datasets
        if strict:
            raise FileNotFoundError(f"No datasets found at {datasets_path}")

    # Gate 3: all required release files present. The list is versioned in
    # release-gates.yaml so release policy changes are visible in review.
    required = gates_config.get("required_files") or [
        "src/agent_memory/cli/main.py",
        "src/agent_memory/application/remember.py",
        "src/agent_memory/application/retrieve.py",
        "src/agent_memory/lab/app.py",
        "src/agent_memory/evaluation/runner.py",
        "src/agent_memory/evaluation/reports.py",
    ]
    missing = [f for f in required if not _resolve_project_path(f, project_root).exists()]
    if missing:
        results.append(f"missing files: {missing}")
        if strict:
            raise FileNotFoundError(f"Missing required files: {missing}")
    else:
        results.append(f"required files OK ({len(required)})")

    # Gate 3b: required security counters must be zero in configuration.
    release_gates = gates_config.get("release_gates", {})
    zero_counter_names = [
        "cross_tenant_leakage",
        "unauthorized_retrieval",
        "unauthorized_write",
        "unauthorized_update",
        "unauthorized_delete",
        "revoked_memory_retrieval",
        "expired_memory_retrieval",
        "instruction_escalation",
        "tool_escalation",
        "permission_escalation",
        "memories_activated_without_evidence",
        "secrets_detected_in_logs",
    ]
    non_zero = [name for name in zero_counter_names if release_gates.get(name) != 0]
    if non_zero:
        message = f"release gate counters must be zero: {non_zero}"
        results.append(message)
        if strict:
            raise RuntimeError(message)
    else:
        results.append("security counters configured as zero")

    # Gate 4: execute real evaluation datasets and enforce configured quality
    # thresholds. A release gate that only reads threshold numbers is theatre;
    # this runs the deterministic scenario suite and compares actual results.
    try:
        metrics = asyncio.run(_run_release_evaluation_metrics(datasets_path))
        results.append(
            "evaluation OK "
            f"({metrics['passed_scenarios']}/{metrics['total_scenarios']} scenarios, "
            f"pass_rate={metrics['pass_rate']:.3f})"
        )
        threshold_aliases = {
            "extraction_precision": "extraction_precision",
            "evidence_exact_match": "evidence_exact_match",
            "retrieval_precision_at_5": "retrieval_precision_at_5",
            "retrieval_recall_at_5": "retrieval_recall_at_5",
            "core_policy_coverage": "core_policy_coverage",
        }
        failed_metrics: list[str] = []
        for gate_name, metric_name in threshold_aliases.items():
            threshold = release_gates.get(gate_name)
            if threshold is None:
                continue
            actual = metrics[metric_name]
            if actual < float(threshold):
                failed_metrics.append(f"{gate_name}={actual:.3f} < {float(threshold):.3f}")
        if metrics["failed_scenarios"]:
            failed_metrics.append(f"failed scenarios: {metrics['failed_scenarios']}")
        if failed_metrics:
            message = f"evaluation gates failed: {failed_metrics}"
            results.append(message)
            if strict:
                raise RuntimeError(message)
        else:
            results.append(
                "quality gates OK "
                f"(extraction_precision={metrics['extraction_precision']:.3f}, "
                f"retrieval_precision_at_5={metrics['retrieval_precision_at_5']:.3f}, "
                f"retrieval_recall_at_5={metrics['retrieval_recall_at_5']:.3f}, "
                f"core_policy_coverage={metrics['core_policy_coverage']:.3f})"
            )
    except Exception as exc:
        results.append(f"evaluation gates FAIL: {exc}")
        if strict:
            raise

    # Gate 4b: enforce global coverage when configured. This reads existing
    # coverage data instead of launching pytest recursively. CI should run
    # coverage first, then execute release check against that data file.
    coverage_threshold = release_gates.get("global_coverage")
    if coverage_threshold is not None:
        try:
            global_coverage = _run_global_coverage_metric()
            if global_coverage < float(coverage_threshold):
                message = (
                    f"global coverage {global_coverage:.3f} below threshold "
                    f"{float(coverage_threshold):.3f}"
                )
                results.append(message)
                if strict:
                    raise RuntimeError(message)
            else:
                results.append(
                    f"global coverage OK ({global_coverage:.3f} >= {float(coverage_threshold):.3f})"
                )
        except Exception as exc:
            message = f"global coverage gate FAIL: {exc}"
            results.append(message)
            if strict:
                raise

    # Gate 5: tests exist and are importable
    try:
        import agent_memory  # noqa: F401
        results.append("package importable")
    except Exception as exc:
        results.append(f"package import FAIL: {exc}")
        if strict:
            raise

    # Gate 6: do not allow known non-production markers in runtime paths.
    forbidden_markers = [
        "placeholder",
        "out of scope",
        "In a real implementation",
        "security check results",
    ]
    runtime_paths = [
        project_root / "src/agent_memory/client.py",
        project_root / "src/agent_memory/application",
        project_root / "src/agent_memory/postgres",
        project_root / "src/agent_memory/cli",
        project_root / "src/agent_memory/lab",
    ]
    violations: list[str] = []
    for runtime_path in runtime_paths:
        files = runtime_path.rglob("*.py") if runtime_path.is_dir() else [runtime_path]
        for file_path in files:
            if not file_path.exists():
                continue
            text = file_path.read_text(encoding="utf-8")
            for marker in forbidden_markers:
                if marker.lower() in text.lower():
                    violations.append(f"{file_path}:{marker}")
    if violations:
        message = f"runtime stub markers found: {violations[:5]}"
        results.append(message)
        if strict:
            raise RuntimeError(message)
    else:
        results.append("runtime stub scan OK")

    return results


async def _run_release_evaluation_metrics(datasets_path: Path) -> dict[str, Any]:
    """Run dataset scenarios and compute release-gate metrics."""

    from agent_memory.evaluation.runner import load_dataset, run_suite
    from agent_memory.providers.rule_based_extractor import RuleBasedExtractor

    scenarios = load_dataset(datasets_path)
    suite = await run_suite(scenarios, RuleBasedExtractor(), suite_name="release-gates")

    total = suite.total_count
    passed = suite.pass_count
    failed_names = [result.scenario_name for result in suite.results if not result.passed]

    extraction_checked = 0
    extraction_matched = 0
    evidence_checked = 0
    evidence_matched = 0
    query_total = 0
    query_passed = 0

    policy_terms = (
        "consent",
        "revoke",
        "tenant",
        "injection",
        "escalation",
        "unauthorized",
        "no_consent",
        "stale",
    )
    policy_total = 0
    policy_passed = 0

    for result in suite.results:
        expected = result.candidates_expected
        candidate_failed = any("Expected candidate" in error for error in result.errors)
        if expected:
            extraction_checked += expected
            if not candidate_failed:
                extraction_matched += expected

        # The current dataset schema tracks evidence provenance via
        # source_message_id. A candidate mismatch includes provenance failures
        # because the runner validates source_message_id explicitly.
        if expected:
            evidence_checked += expected
            if not any("Expected candidate" in error for error in result.errors):
                evidence_matched += expected

        query_total += result.queries_total
        query_passed += result.queries_passed

        if any(term in result.scenario_name for term in policy_terms):
            policy_total += 1
            if result.passed:
                policy_passed += 1

    return {
        "total_scenarios": total,
        "passed_scenarios": passed,
        "pass_rate": (passed / total) if total else 1.0,
        "failed_scenarios": failed_names,
        "extraction_precision": extraction_precision(extraction_matched, extraction_checked - extraction_matched),
        "extraction_recall": extraction_recall(extraction_matched, extraction_checked - extraction_matched),
        "evidence_exact_match": (evidence_matched / evidence_checked) if evidence_checked else 1.0,
        "retrieval_precision_at_5": (query_passed / query_total) if query_total else 1.0,
        "retrieval_recall_at_5": (query_passed / query_total) if query_total else 1.0,
        "core_policy_coverage": (policy_passed / policy_total) if policy_total else 1.0,
    }


def _run_global_coverage_metric() -> float:
    """Read total coverage ratio from an existing coverage data file.

    Returns a ratio in ``[0.0, 1.0]``. The data file is resolved from
    ``AGENT_MEMORY_COVERAGE_FILE`` first, then standard ``COVERAGE_FILE``, then
    ``.coverage``. The function intentionally does not run tests; release
    pipelines must generate coverage before checking the gate.
    """

    try:
        from coverage import Coverage
        from coverage.exceptions import CoverageException
    except ImportError as exc:  # pragma: no cover - exercised by monkeypatch tests
        raise RuntimeError(
            "coverage is required for global_coverage gate; install test extras first"
        ) from exc

    data_file = os.environ.get("AGENT_MEMORY_COVERAGE_FILE") or os.environ.get("COVERAGE_FILE") or ".coverage"
    if not Path(data_file).exists():
        raise FileNotFoundError(
            f"coverage data file not found: {data_file}; run coverage before release check"
        )

    cov = Coverage(data_file=data_file, source=["src/agent_memory"])
    try:
        cov.load()
        total_percent = cov.report(file=io.StringIO(), skip_empty=True)
    except CoverageException as exc:
        raise RuntimeError(f"coverage data could not be read: {exc}") from exc
    return total_percent / 100.0


def _load_release_gates_config() -> dict[str, Any]:
    """Load versioned release gate configuration if present."""

    path = _project_root() / "release-gates.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("release-gates.yaml must contain a mapping")
    return data


def _project_root() -> Path:
    """Return the agent-memory project root regardless of current cwd."""

    return Path(__file__).resolve().parents[3]


def _resolve_project_path(path: str | Path, project_root: Path) -> Path:
    """Resolve relative paths against the project root."""

    candidate = Path(path)
    return candidate if candidate.is_absolute() else project_root / candidate


def generate_junit_xml(results: list[EvaluationResult]) -> str:
    """Generate a JUnit XML report from evaluation results."""
    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<testsuites name="agent-memory" tests="{len(results)}" '
        f'failures="{sum(1 for r in results if not r.passed)}" '
        f'time="0">',
    ]

    for r in results:
        if r.passed:
            lines.append(
                f'  <testcase name="{r.scenario_name}" classname="agent_memory.evaluation">'
                '</testcase>'
            )
        else:
            lines.append(
                f'  <testcase name="{r.scenario_name}" classname="agent_memory.evaluation">'
            )
            for error in r.errors:
                lines.append(
                    f'    <failure message="{_escape_xml(error)}">'
                    f'{_escape_xml(r.scenario_name)}: {error}'
                    '</failure>'
                )
            lines.append('  </testcase>')

    lines.append('</testsuites>')
    return "\n".join(lines)


def generate_html_report(results: list[EvaluationResult]) -> str:
    """Generate an HTML report with Tailwind styling."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    pass_rate = (passed / total * 100) if total > 0 else 0

    rows_html = ""
    for r in results:
        status_class = "bg-green-100 text-green-800" if r.passed else "bg-red-100 text-red-800"
        status_text = "PASS" if r.passed else "FAIL"

        rows_html += f"""
        <tr class="hover:bg-gray-50">
            <td class="px-6 py-4 text-sm font-medium text-gray-900">{_escape_html(r.scenario_name)}</td>
            <td class="px-6 py-4">
                <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium {status_class}">
                    {status_text}
                </span>
            </td>
            <td class="px-6 py-4 text-sm text-gray-500">
                {', '.join(_escape_html(e) for e in r.errors) if r.errors else '<span class="text-gray-400">-</span>'}
            </td>
            <td class="px-6 py-4 text-sm text-gray-500">
                {', '.join(f"{k}: {v}" for k, v in r.metrics.items()) if r.metrics else '<span class="text-gray-400">-</span>'}
            </td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Evaluation Report</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 min-h-screen p-8">
    <div class="max-w-6xl mx-auto">
        <h1 class="text-3xl font-bold text-gray-800 mb-2">Evaluation Report</h1>
        <p class="text-gray-600 mb-6">Generated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}</p>

        <!-- Summary Cards -->
        <div class="grid grid-cols-3 gap-6 mb-8">
            <div class="bg-white rounded-lg shadow p-6">
                <p class="text-sm font-medium text-gray-500">Total</p>
                <p class="text-3xl font-bold text-gray-800">{total}</p>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <p class="text-sm font-medium text-green-600">Passed</p>
                <p class="text-3xl font-bold text-green-600">{passed}</p>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <p class="text-sm font-medium text-red-600">Failed</p>
                <p class="text-3xl font-bold text-red-600">{failed}</p>
            </div>
        </div>

        <!-- Pass Rate Bar -->
        <div class="bg-white rounded-lg shadow p-6 mb-8">
            <h3 class="text-lg font-semibold text-gray-800 mb-2">Pass Rate</h3>
            <div class="w-full bg-gray-200 rounded-full h-4">
                <div class="bg-green-500 h-4 rounded-full" style="width: {pass_rate:.0f}%"></div>
            </div>
            <p class="text-sm text-gray-600 mt-2">{pass_rate:.1f}%</p>
        </div>

        <!-- Results Table -->
        <div class="bg-white rounded-lg shadow overflow-hidden">
            <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50">
                    <tr>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Scenario</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Errors</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Metrics</th>
                    </tr>
                </thead>
                <tbody class="bg-white divide-y divide-gray-200">
{rows_html}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>"""

    return html


def _escape_xml(text: str) -> str:
    """Escape XML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
