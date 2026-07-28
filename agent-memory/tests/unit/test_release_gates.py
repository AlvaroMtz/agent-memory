"""Tests for release gate enforcement."""

from __future__ import annotations

import pytest

from agent_memory.evaluation import reports


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


def test_release_gates_config_is_project_root_relative(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
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
