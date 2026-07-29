from __future__ import annotations

from pathlib import Path

import pytest
from agent_eval import (
    CriterionObservation,
    CriterionState,
    RealModelEvaluationRunner,
    RealModelExecutorRequired,
    RealModelOptInRequired,
    RealModelRunOptions,
    ScenarioObservation,
    default_catalog_path,
    default_fixture_root,
    load_scenario_catalog,
)
from agent_eval.models import (
    EvaluationReport,
    LiveExecutionBudget,
    LiveExecutionResult,
    RealModelRunPlan,
    RunnerKind,
    ScenarioCatalog,
)

FIXTURES = default_fixture_root()
CATALOG = default_catalog_path()


class RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Path, str]] = []

    async def execute(
        self,
        scenario,
        fixture_path: Path,
        *,
        model_id: str,
        budget: LiveExecutionBudget,
    ) -> LiveExecutionResult:
        self.calls.append((scenario.id, fixture_path, model_id))
        target = fixture_path / scenario.validators[0].path
        additions = []
        for validator in scenario.validators:
            expected = str(validator.expected)
            additions.append(
                "if value is None:\n    pass" if expected == "if value is None" else expected
            )
        target.write_text(
            target.read_text(encoding="utf-8") + "\n" + "\n".join(additions),
            encoding="utf-8",
        )
        return LiveExecutionResult(
            observation=ScenarioObservation(scenario_id=scenario.id),
        )


def _catalog() -> ScenarioCatalog:
    loaded = load_scenario_catalog(CATALOG, FIXTURES)
    return ScenarioCatalog(
        catalog_id="live-test-v1",
        scenarios=loaded.scenarios[:1],
        catalog_checksum=loaded.catalog_checksum,
    )


@pytest.mark.asyncio
async def test_real_model_defaults_to_dry_run_and_never_calls_executor() -> None:
    executor = RecordingExecutor()
    runner = RealModelEvaluationRunner(FIXTURES, executor)

    result = await runner.run(_catalog(), RealModelRunOptions(model_id="provider/model"))

    assert isinstance(result, RealModelRunPlan)
    assert result.dry_run is True
    assert result.would_execute is False
    assert executor.calls == []


@pytest.mark.asyncio
async def test_live_run_requires_explicit_opt_in_and_executor(monkeypatch) -> None:
    options = RealModelRunOptions(model_id="provider/model", dry_run=False)
    with pytest.raises(RealModelOptInRequired):
        await RealModelEvaluationRunner(FIXTURES, RecordingExecutor()).run(_catalog(), options)

    enabled = RealModelRunOptions(
        model_id="provider/model",
        dry_run=False,
        explicit_opt_in=True,
    )
    monkeypatch.setenv("ENABLE_REAL_MODEL_EVALUATION", "true")
    with pytest.raises(RealModelExecutorRequired):
        await RealModelEvaluationRunner(FIXTURES).run(_catalog(), enabled)


@pytest.mark.asyncio
async def test_explicit_live_run_delegates_and_reports_real_model_source(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_REAL_MODEL_EVALUATION", "true")
    executor = RecordingExecutor()
    result = await RealModelEvaluationRunner(FIXTURES, executor).run(
        _catalog(),
        RealModelRunOptions(
            model_id="provider/model",
            dry_run=False,
            explicit_opt_in=True,
        ),
    )

    assert isinstance(result, EvaluationReport)
    assert result.runner.kind is RunnerKind.REAL_MODEL
    assert result.runner.model_id == "provider/model"
    assert result.summary.passed == 1
    assert len(executor.calls) == 1
