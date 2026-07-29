"""Tests for release gate enforcement."""

from __future__ import annotations

import pytest

from agent_memory.evaluation import reports
from agent_memory.evaluation.schema import EvaluationSuite, ScenarioResult


class _Config:
    environment = "testing"

    def __init__(self, datasets_path: str = "datasets") -> None:
        self.evaluation = {"datasets_path": datasets_path}


async def _passing_evaluation_metrics(datasets_path):
    return {
        "passed_scenarios": 0,
        "total_scenarios": 0,
        "pass_rate": 1.0,
        "failed_scenarios": [],
        "extraction_precision": 1.0,
        "retrieval_precision_at_5": 1.0,
        "retrieval_recall_at_5": 1.0,
        "core_policy_coverage": 1.0,
    }


def test_global_coverage_gate_fails_without_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured global coverage is strict: missing data fails release checks."""

    monkeypatch.setenv("AGENT_MEMORY_COVERAGE_FILE", "/tmp/agent-memory-missing-coverage-data")

    with pytest.raises(FileNotFoundError):
        reports._run_global_coverage_metric()


def test_release_gates_config_is_project_root_relative(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """release-gates.yaml is found even when current working directory changes."""

    monkeypatch.chdir(tmp_path)

    config = reports._load_release_gates_config()

    assert "release_gates" in config
    assert config["release_gates"]["global_coverage"] == 0.85


def test_global_coverage_gate_uses_existing_metric(monkeypatch: pytest.MonkeyPatch) -> None:
    """Release gate compares the measured coverage ratio to the threshold."""

    monkeypatch.setattr(reports, "_run_global_coverage_metric", lambda: 0.90)
    monkeypatch.setattr(
        reports,
        "_load_release_gates_config",
        lambda: {
            "release_gates": {
                "global_coverage": 0.85,
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
            },
            "required_files": [],
        },
    )
    monkeypatch.setattr(
        reports,
        "_run_release_evaluation_metrics",
        _passing_evaluation_metrics,
    )

    results = reports._assert_release_gates(strict=True)

    assert any("global coverage OK" in result for result in results)


def test_generate_junit_report_escapes_failures() -> None:
    """JUnit reports include pass/fail cases and XML-escaped failure messages."""

    result = reports.generate_junit_xml(
        [
            reports.EvaluationResult("ok-scenario", True),
            reports.EvaluationResult(
                "bad<&scenario",
                False,
                errors=['expected "x" & got <y>'],
            ),
        ]
    )

    assert 'tests="2"' in result
    assert 'failures="1"' in result
    assert 'name="ok-scenario"' in result
    assert "bad&lt;&amp;scenario" in result
    assert "expected &quot;x&quot; &amp; got &lt;y&gt;" in result


def test_generate_html_report_summarizes_and_escapes() -> None:
    """HTML reports render totals, status badges, metrics, and escaped text."""

    result = reports.generate_html_report(
        [
            reports.EvaluationResult("ok", True, metrics={"precision": 1.0}),
            reports.EvaluationResult("bad<script>", False, errors=["boom <unsafe>"]),
        ]
    )

    assert "Evaluation Report" in result
    assert ">2<" in result
    assert "PASS" in result
    assert "FAIL" in result
    assert "precision: 1.0" in result
    assert "bad&lt;script&gt;" in result
    assert "boom &lt;unsafe&gt;" in result


def test_generate_report_dispatches_formats_and_rejects_unknown() -> None:
    """High-level report dispatcher supports JSON/JUnit/HTML and rejects invalid formats."""

    suite = EvaluationSuite(
        name="suite",
        scenarios=[
            ScenarioResult(
                scenario_name="scenario",
                passed=True,
                duration_ms=12.5,
                candidates_found=1,
            )
        ],
    )

    assert '"scenario": "scenario"' in reports.generate_report(suite, fmt="json")
    assert "<testsuites" in reports.generate_report(suite, fmt="junit")
    assert "Evaluation Report" in reports.generate_report(suite, fmt="html")
    with pytest.raises(ValueError, match="Unsupported report format"):
        reports.generate_report(suite, fmt="xml")


def test_release_gates_fail_when_datasets_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Strict release gates reject missing evaluation datasets."""

    import agent_memory.config as config_module

    monkeypatch.setattr(config_module, "load_config", lambda: _Config("missing-datasets"))
    monkeypatch.setattr(reports, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(reports, "_load_release_gates_config", lambda: {"required_files": []})

    with pytest.raises(FileNotFoundError, match="No datasets found"):
        reports._assert_release_gates(strict=True)


def test_release_gates_fail_when_required_files_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Strict release gates reject missing required release files."""

    import agent_memory.config as config_module

    datasets = tmp_path / "datasets"
    datasets.mkdir()
    (datasets / "scenario.yaml").write_text("name: scenario\n", encoding="utf-8")
    (tmp_path / "present.py").write_text("# present\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "load_config", lambda: _Config("datasets"))
    monkeypatch.setattr(reports, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        reports,
        "_load_release_gates_config",
        lambda: {"required_files": ["missing.py"], "release_gates": {}},
    )

    with pytest.raises(FileNotFoundError, match="Missing required files"):
        reports._assert_release_gates(strict=True)


def test_release_gates_fail_on_non_zero_security_counters(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Strict release gates require security counters to be explicitly zero."""

    import agent_memory.config as config_module

    datasets = tmp_path / "datasets"
    datasets.mkdir()
    (datasets / "scenario.yaml").write_text("name: scenario\n", encoding="utf-8")
    (tmp_path / "present.py").write_text("# present\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "load_config", lambda: _Config("datasets"))
    monkeypatch.setattr(reports, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        reports,
        "_load_release_gates_config",
        lambda: {
            "required_files": ["present.py"],
            "release_gates": {
                "cross_tenant_leakage": 1,
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
            },
        },
    )

    with pytest.raises(RuntimeError, match="release gate counters must be zero"):
        reports._assert_release_gates(strict=True)


def test_release_gates_fail_on_quality_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strict release gates reject quality metrics below configured thresholds."""

    async def failing_evaluation_metrics(_):
        return {
            "passed_scenarios": 0,
            "total_scenarios": 1,
            "pass_rate": 0.0,
            "failed_scenarios": ["bad-scenario"],
            "extraction_precision": 0.5,
            "evidence_exact_match": 1.0,
            "retrieval_precision_at_5": 1.0,
            "retrieval_recall_at_5": 1.0,
            "core_policy_coverage": 1.0,
        }

    monkeypatch.setattr(reports, "_run_global_coverage_metric", lambda: 0.90)
    monkeypatch.setattr(
        reports,
        "_load_release_gates_config",
        lambda: {
            "required_files": [],
            "release_gates": {
                "global_coverage": 0.85,
                "extraction_precision": 0.95,
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
            },
        },
    )
    monkeypatch.setattr(
        reports,
        "_run_release_evaluation_metrics",
        failing_evaluation_metrics,
    )

    with pytest.raises(RuntimeError, match="evaluation gates failed"):
        reports._assert_release_gates(strict=True)
