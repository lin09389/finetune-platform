from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_eval import (
    CriterionObservation,
    CriterionState,
    DeterministicEvaluationRunner,
    EvaluationInputError,
    FailureAttribution,
    RunOutcome,
    ScenarioObservation,
    default_catalog_path,
    default_fixture_root,
    load_scenario_catalog,
)
from agent_eval.models import ScenarioCatalog

FIXTURES = default_fixture_root()
CATALOG = default_catalog_path()


def _catalog(count: int = 4) -> ScenarioCatalog:
    loaded = load_scenario_catalog(CATALOG, FIXTURES)
    return ScenarioCatalog(
        catalog_id="test-suite-v1",
        scenarios=loaded.scenarios[:count],
        catalog_checksum=loaded.catalog_checksum,
    )


def _criterion_results(scenario, *states: CriterionState) -> tuple[CriterionObservation, ...]:
    return tuple(
        CriterionObservation(criterion_id=criterion.id, state=state, summary="validator result")
        for criterion, state in zip(scenario.criteria, states, strict=True)
    )


def test_deterministic_runner_scores_all_outcomes_and_modes() -> None:
    catalog = _catalog()
    first, second, third, fourth = catalog.scenarios
    observations = (
        ScenarioObservation(
            scenario_id=first.id,
            criteria=_criterion_results(first, CriterionState.PASSED, CriterionState.PASSED),
        ),
        ScenarioObservation(
            scenario_id=second.id,
            criteria=_criterion_results(second, CriterionState.PASSED, CriterionState.FAILED),
            failure_attribution=FailureAttribution.MODEL,
        ),
        ScenarioObservation(
            scenario_id=third.id,
            criteria=_criterion_results(third, CriterionState.FAILED, CriterionState.FAILED),
            failure_attribution=FailureAttribution.PLATFORM,
        ),
        ScenarioObservation(
            scenario_id=fourth.id,
            blocked=True,
            failure_attribution=FailureAttribution.ENVIRONMENT,
            error_summary="required runtime is unavailable",
        ),
    )

    report = DeterministicEvaluationRunner().run(catalog, observations)

    assert [result.outcome for result in report.scenarios] == [
        RunOutcome.PASSED,
        RunOutcome.PARTIAL,
        RunOutcome.FAILED,
        RunOutcome.BLOCKED,
    ]
    assert report.summary.total == 4
    assert report.summary.passed == report.summary.partial == 1
    assert report.summary.failed == report.summary.blocked == 1
    assert report.scenarios[0].failure_attribution is None
    assert report.scenarios[3].failure_attribution is FailureAttribution.ENVIRONMENT


def test_report_is_stable_and_privacy_safe() -> None:
    catalog = _catalog(1)
    scenario = catalog.scenarios[0]
    sensitive = (
        f"{scenario.task} C:\\Users\\alice\\secret.py "
        "Authorization: Bearer token-value api_key=top-secret "
        "```python\nprint('private source')\n```"
    )
    observation = ScenarioObservation(
        scenario_id=scenario.id,
        criteria=(
            CriterionObservation(
                criterion_id=scenario.criteria[0].id,
                state=CriterionState.FAILED,
                summary=sensitive,
            ),
            CriterionObservation(
                criterion_id=scenario.criteria[1].id,
                state=CriterionState.FAILED,
            ),
        ),
        failure_attribution=FailureAttribution.MODEL,
        error_summary=sensitive,
    )
    runner = DeterministicEvaluationRunner()

    first = runner.run(catalog, (observation,))
    second = runner.run(catalog, (observation,))
    serialized = json.dumps(first.model_dump(mode="json"), sort_keys=True)

    assert first == second
    assert first.report_id == second.report_id
    assert scenario.task not in serialized
    assert "C:\\\\Users" not in serialized
    assert "token-value" not in serialized
    assert "top-secret" not in serialized
    assert "private source" not in serialized
    assert "Diagnose and fix the null input failure" not in serialized
    assert first.privacy.contains_absolute_paths is False


def test_runner_fails_closed_for_missing_or_unknown_results() -> None:
    catalog = _catalog(1)

    with pytest.raises(EvaluationInputError, match="missing observations"):
        DeterministicEvaluationRunner().run(catalog, ())

    scenario = catalog.scenarios[0]
    incomplete = ScenarioObservation(
        scenario_id=scenario.id,
        criteria=(
            CriterionObservation(
                criterion_id=scenario.criteria[0].id,
                state=CriterionState.PASSED,
            ),
        ),
    )
    with pytest.raises(EvaluationInputError, match="missing criteria"):
        DeterministicEvaluationRunner().run(catalog, (incomplete,))


def test_blocked_observation_requires_failure_attribution() -> None:
    with pytest.raises(ValueError, match="require failure_attribution"):
        ScenarioObservation(scenario_id="valid-scenario", blocked=True)
