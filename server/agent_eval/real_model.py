"""Explicitly opt-in adapter contract for real-model evaluation."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from .loader import resolve_fixture_directory
from .models import (
    DecisionSource,
    EvaluationReport,
    FailureAttribution,
    LiveExecutionBudget,
    LiveExecutionResult,
    RealModelRunOptions,
    RealModelRunPlan,
    RunnerDescriptor,
    RunnerKind,
    ScenarioCatalog,
    ScenarioDefinition,
    ScenarioObservation,
)
from .runner import DeterministicEvaluationRunner, EvaluationInputError
from .validators import validate_scenario_workspace

REAL_MODEL_ENV_GATE = "ENABLE_REAL_MODEL_EVALUATION"


class RealModelOptInRequired(PermissionError):
    """A live run was requested without explicit user opt-in."""


class RealModelExecutorRequired(RuntimeError):
    """No platform-owned execution adapter was provided for a live run."""


class RealModelServerDisabled(PermissionError):
    """The service-side live evaluation gate is not enabled."""


class RealModelExecutor(Protocol):
    """Adapter implemented by the existing Agent runtime integration layer."""

    async def execute(
        self,
        scenario: ScenarioDefinition,
        fixture_path: Path,
        *,
        model_id: str,
        budget: LiveExecutionBudget,
    ) -> LiveExecutionResult: ...


class RealModelEvaluationRunner:
    """Plan safely by default and delegate live work to an injected executor."""

    def __init__(self, fixture_root: Path, executor: RealModelExecutor | None = None) -> None:
        self._fixture_root = fixture_root
        self._executor = executor

    def plan(self, catalog: ScenarioCatalog, options: RealModelRunOptions) -> RealModelRunPlan:
        scenarios = self._select_scenarios(catalog, options.scenario_ids)
        server_enabled = self._server_enabled()
        return RealModelRunPlan(
            dry_run=options.dry_run,
            explicit_opt_in=options.explicit_opt_in,
            would_execute=not options.dry_run and options.explicit_opt_in and server_enabled,
            server_enabled=server_enabled,
            model_id=options.model_id,
            catalog_id=catalog.catalog_id,
            scenario_ids=tuple(scenario.id for scenario in scenarios),
            fixture_ids=tuple(scenario.fixture_id for scenario in scenarios),
            timeout_seconds=options.timeout_seconds,
            max_input_tokens=options.max_input_tokens,
            max_output_tokens=options.max_output_tokens,
            max_tool_calls=options.max_tool_calls,
            max_cost_usd=options.max_cost_usd,
        )

    async def run(
        self,
        catalog: ScenarioCatalog,
        options: RealModelRunOptions,
    ) -> RealModelRunPlan | EvaluationReport:
        plan = self.plan(catalog, options)
        if options.dry_run:
            return plan
        if not options.explicit_opt_in:
            raise RealModelOptInRequired(
                "live real-model evaluation requires explicit_opt_in=true"
            )
        if not self._server_enabled():
            raise RealModelServerDisabled(
                f"live real-model evaluation requires {REAL_MODEL_ENV_GATE}=true"
            )
        if self._executor is None:
            raise RealModelExecutorRequired("live real-model evaluation requires an executor")

        scenarios = self._select_scenarios(catalog, options.scenario_ids)
        observations: list[ScenarioObservation] = []
        for scenario in scenarios:
            source_fixture = resolve_fixture_directory(self._fixture_root, scenario.fixture_id)
            try:
                with tempfile.TemporaryDirectory(prefix=f"agent-eval-{scenario.id[:20]}-") as temporary:
                    workspace = Path(temporary) / "workspace"
                    shutil.copytree(source_fixture, workspace)
                    execution = await asyncio.wait_for(
                        self._executor.execute(
                            scenario,
                            workspace,
                            model_id=options.model_id,
                            budget=LiveExecutionBudget(
                                timeout_seconds=options.timeout_seconds,
                                max_input_tokens=options.max_input_tokens,
                                max_output_tokens=options.max_output_tokens,
                                max_tool_calls=options.max_tool_calls,
                                max_cost_usd=options.max_cost_usd,
                            ),
                        ),
                        timeout=options.timeout_seconds,
                    )
                    if execution.observation.scenario_id != scenario.id:
                        raise EvaluationInputError(
                            "executor observation does not match requested scenario"
                        )
                    if self._exceeds_budget(execution, options):
                        observations.append(
                            ScenarioObservation(
                                scenario_id=scenario.id,
                                blocked=True,
                                failure_attribution=FailureAttribution.ENVIRONMENT,
                                error_summary="scenario execution exceeded the declared budget",
                            )
                        )
                    elif execution.observation.blocked:
                        observations.append(execution.observation)
                    else:
                        validated = validate_scenario_workspace(scenario, workspace)
                        observations.append(
                            validated.model_copy(
                                update={
                                    "error_summary": execution.observation.error_summary,
                                    "failure_attribution": (
                                        validated.failure_attribution
                                        or execution.observation.failure_attribution
                                    ),
                                }
                            )
                        )
            except (TimeoutError, OSError) as exc:
                observations.append(
                    ScenarioObservation(
                        scenario_id=scenario.id,
                        blocked=True,
                        failure_attribution=FailureAttribution.ENVIRONMENT,
                        error_summary=f"scenario execution unavailable: {type(exc).__name__}",
                    )
                )
            except Exception as exc:
                observations.append(
                    ScenarioObservation(
                        scenario_id=scenario.id,
                        blocked=True,
                        failure_attribution=FailureAttribution.PLATFORM,
                        error_summary=f"scenario execution failed: {type(exc).__name__}",
                    )
                )

        selected_catalog = ScenarioCatalog(
            catalog_id=catalog.catalog_id,
            scenarios=tuple(scenarios),
            catalog_checksum=catalog.catalog_checksum,
        )
        return DeterministicEvaluationRunner().run(
            selected_catalog,
            observations,
            runner=RunnerDescriptor(
                kind=RunnerKind.REAL_MODEL,
                decision_source=DecisionSource.LIVE,
                model_id=options.model_id,
            ),
        )

    @staticmethod
    def _server_enabled() -> bool:
        return os.environ.get(REAL_MODEL_ENV_GATE, "").strip().lower() == "true"

    @staticmethod
    def _exceeds_budget(execution: LiveExecutionResult, options: RealModelRunOptions) -> bool:
        usage = execution.usage
        return any(
            actual is not None and actual > maximum
            for actual, maximum in (
                (usage.input_tokens, options.max_input_tokens),
                (usage.output_tokens, options.max_output_tokens),
                (usage.tool_calls, options.max_tool_calls),
                (usage.cost_usd, options.max_cost_usd),
            )
        )

    @staticmethod
    def _select_scenarios(
        catalog: ScenarioCatalog,
        scenario_ids: Sequence[str] | None,
    ) -> tuple[ScenarioDefinition, ...]:
        if scenario_ids is None:
            return catalog.scenarios
        scenarios_by_id = {scenario.id: scenario for scenario in catalog.scenarios}
        if unknown := sorted(set(scenario_ids) - set(scenarios_by_id)):
            raise EvaluationInputError(f"unknown scenario selection: {', '.join(unknown)}")
        return tuple(scenarios_by_id[scenario_id] for scenario_id in scenario_ids)
