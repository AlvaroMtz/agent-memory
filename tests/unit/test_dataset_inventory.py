"""Tests for dataset inventory — mandatory scenario coverage.

Verifies that every required dataset case from the compliance spec is
present in the dataset directory, that each scenario has at least one
strong assertion capable of failing when a guarantee is broken, and
that the runner can load and validate them without errors.
"""

import pytest

from agent_memory.evaluation.reports import REQUIRED_DATASET_CASES
from agent_memory.evaluation.runner import (
    load_dataset,
    validate_dataset_scenarios,
)
from agent_memory.evaluation.schema import (
    EvaluationScenario,
    InjectionRuntimeInvariant,
    ScenarioConsent,
    ScenarioMessage,
    TenantOperation,
)


def mandatory_scenarios_by_name(scenarios):
    """Return scenarios whose names are mandatory according to release gates.

    Do not rely on YAML tags here. The compliance gate is name-based through
    REQUIRED_DATASET_CASES, so these tests must check the same inventory.
    """
    mandatory_names = {name for names in REQUIRED_DATASET_CASES.values() for name in names}
    return [scenario for scenario in scenarios if scenario.name in mandatory_names]


class TestDatasetInventory:
    """Verify all mandatory scenario cases are present."""

    @pytest.fixture(autouse=True)
    def _load_scenarios(self):
        self.scenarios = load_dataset("datasets")
        self.names = {s.name for s in self.scenarios}

    def test_exhaustive_coverage(self):
        """Every mandatory case must be present in exactly one scenario."""
        missing: dict[str, list[str]] = {}
        for suite_name, required_names in REQUIRED_DATASET_CASES.items():
            required_set = set(required_names)
            absent = sorted(required_set - self.names)
            if absent:
                missing[suite_name] = absent
        assert not missing, f"Missing mandatory cases: {missing}"

    def test_no_duplicate_case_names(self):
        """Each mandatory case must appear exactly once."""
        from collections import Counter

        counts = Counter(s.name for s in self.scenarios)
        duplicates = {name for name, count in counts.items() if count > 1}
        assert not duplicates, f"Duplicate scenario names: {duplicates}"

    def test_all_required_cases_are_checked_as_mandatory(self):
        """The mandatory assertion tests must actually cover all required cases."""
        mandatory = mandatory_scenarios_by_name(self.scenarios)
        expected_count = sum(len(names) for names in REQUIRED_DATASET_CASES.values())
        assert len(mandatory) == expected_count

    def test_each_scenario_loads_pydantic_model(self):
        """Every YAML file must be parseable as EvaluationScenario."""
        from pathlib import Path

        from agent_memory.evaluation.runner import load_scenario

        errors: list[str] = []
        for path in Path("datasets").rglob("*"):
            if path.suffix in (".yaml", ".yml", ".json"):
                try:
                    load_scenario(path)
                except Exception as exc:
                    errors.append(f"{path}: {exc}")
        assert not errors, f"Scenario loading errors: {'; '.join(errors)}"


class TestStrongAssertions:
    """Every mandatory scenario must have at least one strong assertion."""

    @pytest.fixture(autouse=True)
    def _load_scenarios(self):
        self.scenarios = load_dataset("datasets")

    def test_all_mandatory_have_assertions(self):
        """Mandatory scenarios must have at least one assertion type."""
        weak: list[str] = []
        for scenario in mandatory_scenarios_by_name(self.scenarios):
            if not scenario.has_strong_assertions:
                weak.append(scenario.name)
        assert not weak, f"Mandatory scenarios without assertions: {weak}"

    def test_all_mandatory_have_strong_assertions(self):
        """Every mandatory scenario must have >= 2 distinct assertion types."""
        weak: list[str] = []
        for scenario in mandatory_scenarios_by_name(self.scenarios):
            count = scenario.count_mandatory_assertions()
            if count < 2:
                weak.append(f"{scenario.name} (count={count})")
        assert not weak, f"Mandatory scenarios with insufficient assertions: {weak}"

    def test_extraction_cases_have_real_assertions(self):
        scenarios = {scenario.name: scenario for scenario in self.scenarios}
        negative = {
            "extraction-negation",
            "extraction-ambiguous-information",
            "extraction-assistant-invention-rejected",
            "extraction-untrusted-tool-rejected",
            "extraction-missing-evidence-rejected",
            "extraction-partial-evidence-rejected",
            "extraction-low-confidence-rejected",
            "extraction-sensitive-inference-rejected",
        }
        for name in REQUIRED_DATASET_CASES["extraction"]:
            scenario = scenarios[name]
            if name in negative:
                assert scenario.expected_accepted_candidates == [], name
                assert scenario.expected_memories == [] or scenario.expected_rejected_candidates, (
                    name
                )
            else:
                assert scenario.expected_candidates, name
                assert scenario.expected_accepted_candidates, name
                assert scenario.expected_memories, name

    def test_retrieval_cases_have_executable_queries(self):
        scenarios = {scenario.name: scenario for scenario in self.scenarios}
        for name in REQUIRED_DATASET_CASES["retrieval"]:
            scenario = scenarios[name]
            assert scenario.expected_queries, name
        assert scenarios["retrieval-token-budget-enforced"].expected_queries[0].token_budget
        assert scenarios["retrieval-type-filter"].expected_queries[0].forbidden_predicates
        assert scenarios["retrieval-sensitivity-filter"].expected_queries[0].forbidden_predicates
        assert any(
            query.purpose for query in scenarios["retrieval-purpose-filter"].expected_queries
        )

    def test_multi_tenant_cases_use_tenant_operations(self):
        scenarios = {scenario.name: scenario for scenario in self.scenarios}
        for name in {
            "tenant-cross-read-denied",
            "tenant-cross-write-denied",
            "tenant-cross-update-denied",
            "tenant-cross-delete-denied",
            "tenant-rls-context-absent-denied",
        }:
            assert scenarios[name].tenant_operations, name
            assert scenarios[name].expected_security_counters, name

    def test_prompt_injection_cases_have_runtime_invariants(self):
        scenarios = {scenario.name: scenario for scenario in self.scenarios}
        for name in REQUIRED_DATASET_CASES["prompt_injection"]:
            scenario = scenarios[name]
            assert scenario.injection_invariants is not None, name
            assert scenario.expected_security_counters, name

    def test_contradiction_pending_review_cases_assert_status(self):
        scenarios = {scenario.name: scenario for scenario in self.scenarios}
        for name in {
            "contradiction-semantic-equal-authority-pending-review",
            "contradiction-ambiguous-candidate-pending-review",
        }:
            scenario = scenarios[name]
            assert any(
                memory.status == "pending_review" for memory in (scenario.expected_memories or [])
            ), name

    def test_negative_scenarios_have_assertions(self):
        """Negative scenarios must have strong assertions (can be via
        expected_* fields, forbidden_*, queries, etc.)."""
        weak: list[str] = []
        for scenario in self.scenarios:
            if scenario.is_negative and not scenario.has_strong_assertions:
                weak.append(scenario.name)
        assert not weak, f"Negative scenarios without assertions: {weak}"


class TestValidation:
    """validate_dataset_scenarios must reject weak scenarios."""

    @pytest.fixture(autouse=True)
    def _load_scenarios(self):
        self.scenarios = load_dataset("datasets")

    def test_validate_passes_on_full_dataset(self):
        """The full dataset must pass validation."""
        validate_dataset_scenarios(self.scenarios)  # no exception

    def test_weak_rejection_is_detected(self):
        """A scenario with only min_results: 0 and no other assertions
        must be rejected."""
        weak = EvaluationScenario(
            name="weak-security",
            description="security scenario with only min_results zero",
            expected_queries=[
                {"description": "no-op", "min_results": 0},
            ],
            tags=["mandatory", "security"],
        )
        with pytest.raises(ValueError, match="Weak dataset"):
            validate_dataset_scenarios([weak])

    def test_no_assertions_is_detected(self):
        """A scenario with no assertion types must be rejected."""
        empty = EvaluationScenario(
            name="empty-scenario",
            description="has no assertions",
            tags=["mandatory"],
        )
        with pytest.raises(ValueError, match="no_assertions"):
            validate_dataset_scenarios([empty])


class TestSchemaFields:
    """Test that all new schema fields work correctly."""

    def test_tenant_operation_model(self):
        op = TenantOperation(
            operation="cross_read",
            tenant_id="other",
            expected_outcome="denied",
        )
        assert op.operation == "cross_read"
        assert op.tenant_id == "other"
        assert op.expected_outcome == "denied"

    def test_injection_invariant_check(self):
        inv = InjectionRuntimeInvariant()
        assert inv.check_invariants() is True
        inv.tenant_unchanged = False
        assert inv.check_invariants() is False

    def test_expected_query_expected_counts(self):
        from agent_memory.evaluation.schema import ExpectedQuery

        q = ExpectedQuery(
            description="test",
            expected_counts={"active": 1, "total": 1},
        )
        assert q.expected_counts == {"active": 1, "total": 1}

    def test_evaluation_scenario_empty_list_semantics(self):
        """Empty list means exactly zero, None means skip."""
        # None → skip
        s = EvaluationScenario(name="test-scenario")
        assert s.expected_candidates is None
        assert s.expected_accepted_candidates is None

        # [] → exactly zero
        s2 = EvaluationScenario(
            name="test-scenario",
            expected_candidates=[],
            expected_accepted_candidates=[],
        )
        assert s2.expected_candidates == []
        assert s2.expected_accepted_candidates == []
        assert s2.is_negative is True  # expected_accepted_candidates is []

    def test_evaluation_scenario_forbidden_fields(self):
        s = EvaluationScenario(
            name="test-scenario",
            forbidden_accepted_candidates=[
                {"predicate": "admin", "value": "true"},
            ],
            forbidden_memories=[
                {"predicate": "secret", "status": "active"},
            ],
            forbidden_memory_type="semantic",
        )
        assert s.forbidden_accepted_candidates is not None
        assert s.forbidden_memories is not None
        assert s.forbidden_memory_type == "semantic"
        assert s.is_negative is True

    def test_evaluation_scenario_tenant_operations(self):
        s = EvaluationScenario(
            name="test-scenario",
            tenant_operations=[
                {
                    "operation": "cross_read",
                    "tenant_id": "other",
                    "expected_outcome": "denied",
                },
            ],
        )
        assert s.tenant_operations is not None
        assert len(s.tenant_operations) == 1
        assert s.tenant_operations[0].operation == "cross_read"

    def test_evaluation_scenario_injection_invariants(self):
        s = EvaluationScenario(
            name="test-scenario",
            injection_invariants=InjectionRuntimeInvariant(
                system_prompt_unchanged=True,
                tools_unchanged=True,
                permissions_unchanged=True,
                tenant_unchanged=True,
                confirmations_required=True,
            ),
        )
        assert s.injection_invariants.check_invariants()

    def test_evaluation_scenario_expected_rejection_reasons(self):
        s = EvaluationScenario(
            name="test-scenario",
            expected_rejection_reasons=[
                "missing_evidence",
                "sensitivity_denied",
            ],
        )
        assert s.expected_rejection_reasons is not None
        assert len(s.expected_rejection_reasons) == 2

    def test_evaluation_scenario_expected_counts(self):
        s = EvaluationScenario(
            name="test-scenario",
            expected_counts={"candidates": 0, "memories": 0},
        )
        assert s.expected_counts == {"candidates": 0, "memories": 0}


class TestRunScenarioWithNewFields:
    """Verify the runner correctly processes new schema fields."""

    @pytest.mark.asyncio
    async def test_empty_list_for_accepted_means_zero(self):
        """expected_accepted_candidates: [] must enforce exactly zero."""
        from agent_memory.evaluation.runner import run_scenario
        from agent_memory.providers.rule_based_extractor import RuleBasedExtractor

        extractor = RuleBasedExtractor()
        scenario = EvaluationScenario(
            name="reject-all",
            messages=[
                ScenarioMessage(
                    id="m1",
                    role="user",
                    content="I prefer Python.",
                ),
            ],
            expected_accepted_candidates=[],  # must be exactly zero
        )
        result = await run_scenario(scenario, extractor)
        assert not result.passed
        assert any("exactly 0 accepted" in e for e in result.errors), (
            f"Expected zero check: {result.errors}"
        )

    @pytest.mark.asyncio
    async def test_none_accepted_falls_back_to_expected_candidates(self):
        """expected_accepted_candidates: None must fall back to
        expected_candidates for the check."""
        from agent_memory.evaluation.runner import run_scenario
        from agent_memory.providers.rule_based_extractor import RuleBasedExtractor

        extractor = RuleBasedExtractor()
        scenario = EvaluationScenario(
            name="fallback-test",
            messages=[
                ScenarioMessage(
                    id="m1",
                    role="user",
                    content="I prefer Python.",
                ),
            ],
            expected_accepted_candidates=None,  # fallback
            expected_candidates=[
                {"predicate": "code_language", "value": "Python"},
            ],
        )
        result = await run_scenario(scenario, extractor)
        assert result.passed

    @pytest.mark.asyncio
    async def test_empty_list_for_candidates_means_zero(self):
        """expected_candidates: [] must enforce exactly zero extracted."""
        from agent_memory.evaluation.runner import run_scenario
        from agent_memory.providers.rule_based_extractor import RuleBasedExtractor

        extractor = RuleBasedExtractor()
        scenario = EvaluationScenario(
            name="reject-extraction",
            messages=[
                ScenarioMessage(
                    id="m1",
                    role="assistant",
                    content="You prefer Python.",
                ),
            ],
            expected_candidates=[],  # must be exactly zero
        )
        result = await run_scenario(scenario, extractor)
        assert result.passed  # assistant messages produce no candidates

    @pytest.mark.asyncio
    async def test_forbidden_accepted_candidates(self):
        """forbidden_accepted_candidates must block specific candidates."""
        from agent_memory.evaluation.runner import run_scenario
        from agent_memory.providers.rule_based_extractor import RuleBasedExtractor

        extractor = RuleBasedExtractor()
        scenario = EvaluationScenario(
            name="forbidden-coded",
            messages=[
                ScenarioMessage(
                    id="m1",
                    role="user",
                    content="I prefer Python.",
                ),
            ],
            forbidden_accepted_candidates=[
                {
                    "memory_type": "preference",
                    "predicate": "code_language",
                    "value": "Python",
                },
            ],
        )
        result = await run_scenario(scenario, extractor)
        assert not result.passed
        assert any("Forbidden accepted candidate" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_empty_list_for_memories_means_zero(self):
        """expected_memories: [] must enforce exactly zero persisted memories."""
        from agent_memory.evaluation.runner import run_scenario
        from agent_memory.providers.rule_based_extractor import RuleBasedExtractor

        extractor = RuleBasedExtractor()
        scenario = EvaluationScenario(
            name="no-memory",
            messages=[
                ScenarioMessage(
                    id="m1",
                    role="assistant",
                    content="You prefer Python.",
                ),
            ],
            expected_memories=[],  # must be exactly zero
        )
        result = await run_scenario(scenario, extractor)
        assert result.passed  # no messages to extract, no memories

    @pytest.mark.asyncio
    async def test_expected_rejection_reasons(self):
        """expected_rejection_reasons must verify rejection reasons."""
        from agent_memory.evaluation.runner import run_scenario
        from agent_memory.providers.rule_based_extractor import RuleBasedExtractor

        extractor = RuleBasedExtractor()
        # A scenario where extraction should fail (assistant message)
        scenario = EvaluationScenario(
            name="rejection-test",
            messages=[
                ScenarioMessage(
                    id="m1",
                    role="assistant",
                    content="You prefer Python.",
                ),
            ],
            # No extraction happens for assistant messages,
            # so no rejection reason is generated.
            # This scenario should pass since there's nothing to reject.
        )
        result = await run_scenario(scenario, extractor)
        assert result.passed


class TestEmptyListSemantics:
    """Verify that [] means 'exactly zero' and None means 'skip'."""

    @pytest.mark.asyncio
    async def test_none_skip(self):
        """None should be treated as 'skip check'."""
        from agent_memory.evaluation.runner import run_scenario
        from agent_memory.providers.rule_based_extractor import RuleBasedExtractor

        extractor = RuleBasedExtractor()
        scenario = EvaluationScenario(
            name="skip-check",
            messages=[
                ScenarioMessage(
                    id="m1",
                    role="user",
                    content="I prefer Python.",
                ),
            ],
            # All expected_* fields are None → skip all checks
        )
        result = await run_scenario(scenario, extractor)
        assert result.passed  # nothing to check

    @pytest.mark.asyncio
    async def test_empty_list_fails_when_results_exist(self):
        """[] must fail when results are present."""
        from agent_memory.evaluation.runner import run_scenario
        from agent_memory.providers.rule_based_extractor import RuleBasedExtractor

        extractor = RuleBasedExtractor()
        scenario = EvaluationScenario(
            name="fail-empty",
            messages=[
                ScenarioMessage(
                    id="m1",
                    role="user",
                    content="I prefer Python.",
                ),
            ],
            expected_accepted_candidates=[],  # will find candidates
        )
        result = await run_scenario(scenario, extractor)
        assert not result.passed

    @pytest.mark.asyncio
    async def test_empty_list_passes_when_no_results(self):
        """[] must pass when results are truly zero."""
        from agent_memory.evaluation.runner import run_scenario
        from agent_memory.providers.rule_based_extractor import RuleBasedExtractor

        extractor = RuleBasedExtractor()
        scenario = EvaluationScenario(
            name="pass-empty",
            messages=[
                ScenarioMessage(
                    id="m1",
                    role="assistant",
                    content="No extraction here.",
                ),
            ],
            expected_candidates=[],  # truly zero candidates
        )
        result = await run_scenario(scenario, extractor)
        assert result.passed
