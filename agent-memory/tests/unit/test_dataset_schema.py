"""Tests for the dataset/evaluation schema models."""

import json

import pytest
import yaml

from agent_memory.evaluation.schema import (
    EvaluationScenario,
    EvaluationSuite,
    ExpectedCandidate,
    ExpectedMemory,
    ExpectedQuery,
    ScenarioAction,
    ScenarioConsent,
    ScenarioMessage,
    ScenarioResult,
)


class TestScenarioConsent:
    """Test ScenarioConsent model."""

    def test_defaults(self):
        consent = ScenarioConsent()
        assert consent.purpose == "testing"
        assert consent.allow_write is True
        assert consent.allow_read is True
        assert "preference" in consent.allowed_memory_types
        assert "public" in consent.allowed_sensitivity

    def test_custom(self):
        consent = ScenarioConsent(
            purpose="research",
            allow_write=False,
            allowed_memory_types=["semantic"],
            allowed_sensitivity=["personal"],
        )
        assert consent.purpose == "research"
        assert consent.allow_write is False
        assert consent.allowed_memory_types == ["semantic"]


class TestScenarioMessage:
    """Test ScenarioMessage model."""

    def test_minimal(self):
        msg = ScenarioMessage(id="m1", role="user", content="Hola")
        assert msg.id == "m1"
        assert msg.role == "user"
        assert msg.content == "Hola"


class TestExpectedCandidate:
    """Test ExpectedCandidate model."""

    def test_partial(self):
        ec = ExpectedCandidate(memory_type="preference", predicate="code_language")
        assert ec.memory_type == "preference"
        assert ec.subject_key is None

    def test_full(self):
        ec = ExpectedCandidate(
            memory_type="preference",
            subject_key="code",
            predicate="code_language",
            value="TypeScript",
            source_message_id="msg-1",
            explicitly_stated=True,
        )
        assert ec.value == "TypeScript"


class TestEvaluationScenario:
    """Test EvaluationScenario model."""

    def test_defaults(self):
        scenario = EvaluationScenario(name="test-scenario")
        assert scenario.name == "test-scenario"
        assert scenario.context == {}
        assert scenario.messages == []
        assert scenario.expected_candidates == []
        assert scenario.expected_to_fail is False

    def test_with_messages(self):
        scenario = EvaluationScenario(
            name="preference-extraction",
            messages=[
                ScenarioMessage(id="m1", role="user", content="Prefiero TypeScript"),
            ],
            expected_candidates=[
                ExpectedCandidate(predicate="code_language", value="TypeScript"),
            ],
        )
        assert len(scenario.messages) == 1
        assert len(scenario.expected_candidates) == 1
        assert scenario.expected_candidates[0].value == "TypeScript"

    def test_yaml_roundtrip(self):
        scenario = EvaluationScenario(
            name="yaml-test",
            description="Test YAML serialization",
            context={"tenant_id": "t1", "subject_id": "s1"},
            messages=[ScenarioMessage(id="m1", role="user", content="Hola")],
        )
        yaml_str = yaml.dump(scenario.model_dump(mode="python"), default_flow_style=False)
        loaded = yaml.safe_load(yaml_str)
        restored = EvaluationScenario(**loaded)
        assert restored.name == "yaml-test"
        assert restored.context["tenant_id"] == "t1"
        assert restored.messages[0].content == "Hola"

    def test_json_roundtrip(self):
        scenario = EvaluationScenario(
            name="json-test",
            messages=[ScenarioMessage(id="m1", role="user", content="Prefiero Python")],
            expected_candidates=[ExpectedCandidate(predicate="code_language", value="Python")],
        )
        json_str = scenario.model_dump_json()
        restored = EvaluationScenario(**json.loads(json_str))
        assert restored.name == "json-test"
        assert restored.expected_candidates[0].value == "Python"

    def test_setup_actions(self):
        scenario = EvaluationScenario(
            name="setup-action-test",
            setup_actions=[
                ScenarioAction(
                    action="set_memory_status",
                    memory_type="preference",
                    subject_key="programming",
                    predicate="favorite_language",
                    status="revoked",
                )
            ],
        )

        assert scenario.setup_actions[0].action == "set_memory_status"
        assert scenario.setup_actions[0].status == "revoked"


class TestScenarioResult:
    """Test ScenarioResult model."""

    def test_passed(self):
        result = ScenarioResult(
            scenario_name="test", passed=True, candidates_found=1, candidates_expected=1
        )
        assert result.passed
        assert result.errors == []

    def test_failed(self):
        result = ScenarioResult(
            scenario_name="test", passed=False, errors=["Missing candidate"]
        )
        assert not result.passed
        assert "Missing candidate" in result.errors


class TestEvaluationSuite:
    """Test EvaluationSuite model."""

    def test_add_result(self):
        suite = EvaluationSuite(name="test-suite")
        suite.add_result(ScenarioResult(scenario_name="s1", passed=True, candidates_found=1, candidates_expected=1))
        suite.add_result(ScenarioResult(scenario_name="s2", passed=False, errors=["fail"]))
        assert suite.total_passed == 1
        assert suite.total_failed == 1
        assert len(suite.scenarios) == 2
