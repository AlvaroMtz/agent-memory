"""Tests for the scenario runner."""

import tempfile
from pathlib import Path

import pytest
import yaml

from agent_memory.evaluation.runner import load_scenario, run_scenario
from agent_memory.evaluation.schema import EvaluationScenario, ScenarioMessage


class TestLoadScenario:
    """Test loading scenarios from files."""

    def test_load_yaml(self):
        data = {
            "name": "test-scenario",
            "description": "A test scenario",
            "context": {"tenant_id": "t1", "subject_id": "s1"},
            "messages": [{"id": "m1", "role": "user", "content": "Prefiero TypeScript"}],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()
            scenario = load_scenario(f.name)
        Path(f.name).unlink()

        assert scenario.name == "test-scenario"
        assert scenario.context["tenant_id"] == "t1"
        assert len(scenario.messages) == 1
        assert scenario.messages[0].content == "Prefiero TypeScript"

    def test_load_json(self):
        import json
        data = {
            "name": "json-scenario",
            "context": {"tenant_id": "t1"},
            "messages": [{"id": "m1", "role": "user", "content": "Hola"}],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            scenario = load_scenario(f.name)
        Path(f.name).unlink()

        assert scenario.name == "json-scenario"


class TestRunScenario:
    """Test running scenarios with the RuleBasedExtractor."""

    @pytest.mark.asyncio
    async def test_extraction_pass(self):
        from agent_memory.providers.rule_based_extractor import RuleBasedExtractor
        extractor = RuleBasedExtractor()

        scenario = EvaluationScenario(
            name="preference-test",
            context={"tenant_id": "t1", "subject_id": "s1"},
            messages=[
                ScenarioMessage(id="m1", role="user", content="Prefiero TypeScript"),
            ],
            expected_candidates=[{"predicate": "response_language", "value": "TypeScript"}],
        )

        result = await run_scenario(scenario, extractor)
        assert result.passed, f"Scenario failed: {result.errors}"
        assert result.candidates_found >= 1

    @pytest.mark.asyncio
    async def test_extraction_no_match(self):
        from agent_memory.providers.rule_based_extractor import RuleBasedExtractor
        extractor = RuleBasedExtractor()

        scenario = EvaluationScenario(
            name="no-preference-test",
            context={"tenant_id": "t1", "subject_id": "s1"},
            messages=[
                ScenarioMessage(id="m1", role="user", content="La capital de Francia es París"),
            ],
            expected_candidates=[{"predicate": "code_language", "value": "Python"}],
        )

        result = await run_scenario(scenario, extractor)
        assert not result.passed  # Should fail — no match
        assert len(result.errors) >= 1

    @pytest.mark.asyncio
    async def test_empty_messages(self):
        from agent_memory.providers.rule_based_extractor import RuleBasedExtractor
        extractor = RuleBasedExtractor()

        scenario = EvaluationScenario(
            name="empty-test",
            context={"tenant_id": "t1", "subject_id": "s1"},
            messages=[],
        )

        result = await run_scenario(scenario, extractor)
        assert result.passed