"""Tests for the scenario runner."""

import tempfile
from pathlib import Path

import pytest
import yaml

from agent_memory.evaluation.runner import load_scenario, run_scenario, validate_dataset_scenarios
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

    def test_load_dataset_recursively(self):
        """Dataset loading walks nested suite directories."""
        from agent_memory.evaluation.runner import load_dataset

        scenarios = load_dataset("datasets")
        assert len(scenarios) >= 32
        assert any(s.name == "injection_attempt_in_memory_value" for s in scenarios)
        assert any(s.name == "injection_through_evidence" for s in scenarios)

    def test_validate_dataset_rejects_weak_security_assertion(self):
        scenario = EvaluationScenario(
            name="prompt-injection-weak",
            description="security scenario with only min_results zero",
            expected_queries=[{"description": "no-op", "min_results": 0}],
        )

        with pytest.raises(ValueError, match="Weak dataset assertions"):
            validate_dataset_scenarios([scenario])


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
        assert result.raw_candidates_found >= 1
        assert result.accepted_candidates_found >= 1
        assert "memories_activated_without_evidence" in result.security_counters

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

    @pytest.mark.asyncio
    async def test_setup_action_sets_memory_status_before_retrieval(self):
        from agent_memory.providers.rule_based_extractor import RuleBasedExtractor

        extractor = RuleBasedExtractor()

        scenario = EvaluationScenario(
            name="stale-memory-test",
            context={"tenant_id": "t1", "subject_id": "s1", "purpose": "testing"},
            messages=[
                ScenarioMessage(id="m1", role="user", content="I used to like Java"),
            ],
            setup_actions=[
                {
                    "action": "set_memory_status",
                    "memory_type": "preference",
                    "subject_key": "programming",
                    "predicate": "favorite_language",
                    "status": "revoked",
                }
            ],
            expected_candidates=[
                {"predicate": "favorite_language", "value": "Java"},
            ],
            expected_memories=[
                {
                    "memory_type": "preference",
                    "subject_key": "programming",
                    "predicate": "favorite_language",
                    "status": "revoked",
                }
            ],
            expected_queries=[
                {"memory_type": "preference", "subject_key": "programming", "max_results": 0},
            ],
        )

        result = await run_scenario(scenario, extractor)
        assert result.passed, f"Scenario failed: {result.errors}"
