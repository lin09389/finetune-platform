"""Deterministic scoring and versioned report generation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path

from .models import (
    CriterionReport,
    CriterionState,
    DecisionSource,
    EvaluationReport,
    EvaluationSummary,
    FailureAttribution,
    OutcomeCounts,
    PrivacyDescriptor,
    RunOutcome,
    RunnerDescriptor,
    RunnerKind,
    ScenarioCatalog,
    ScenarioDefinition,
    ScenarioMode,
    ScenarioObservation,
    ScenarioReport,
    SuiteDescriptor,
)
from .privacy import sanitize_summary
from .validators import validate_scenario_workspace


class EvaluationInputError(ValueError):
    """Raised when evaluation observations do not match the frozen catalog."""


class DeterministicEvaluationRunner:
    """Score externally produced observations without executing an Agent loop."""

    def run(
        self,
        catalog: ScenarioCatalog,
        observations: Mapping[str, ScenarioObservation] | Iterable[ScenarioObservation],
        *,
        runner: RunnerDescriptor | None = None,
    ) -> EvaluationReport:
        if not catalog.catalog_checksum:
            raise EvaluationInputError("catalog must be loaded with checksum verification")
        if any(
            not scenario.fixture_checksum or not scenario.validator_checksum
            for scenario in catalog.scenarios
        ):
            raise EvaluationInputError("scenarios must be loaded with fixture and validator checksums")
        observation_map = self._normalize_observations(observations)
        expected_ids = {scenario.id for scenario in catalog.scenarios}
        received_ids = set(observation_map)
        if missing := sorted(expected_ids - received_ids):
            raise EvaluationInputError(f"missing observations: {', '.join(missing)}")
        if unknown := sorted(received_ids - expected_ids):
            raise EvaluationInputError(f"unknown observations: {', '.join(unknown)}")

        scenario_reports = tuple(
            self._score_scenario(scenario, observation_map[scenario.id])
            for scenario in catalog.scenarios
        )
        runner_descriptor = runner or RunnerDescriptor(
            kind=RunnerKind.DETERMINISTIC,
            decision_source=DecisionSource.DETERMINISTIC,
        )
        summary = self._build_summary(scenario_reports)
        report_id = self._build_report_id(catalog, runner_descriptor, scenario_reports)
        return EvaluationReport(
            report_id=report_id,
            runner=runner_descriptor,
            suite=SuiteDescriptor(
                catalog_id=catalog.catalog_id,
                scenario_count=len(scenario_reports),
                catalog_checksum=catalog.catalog_checksum,
            ),
            summary=summary,
            scenarios=scenario_reports,
            privacy=PrivacyDescriptor(),
        )

    def run_workspaces(
        self,
        catalog: ScenarioCatalog,
        workspaces: Mapping[str, Path],
        *,
        runner: RunnerDescriptor | None = None,
    ) -> EvaluationReport:
        """Run hidden objective validators over isolated scenario workspaces."""

        expected_ids = {scenario.id for scenario in catalog.scenarios}
        if set(workspaces) != expected_ids:
            missing = sorted(expected_ids - set(workspaces))
            unknown = sorted(set(workspaces) - expected_ids)
            raise EvaluationInputError(f"workspace coverage mismatch; missing={missing}, unknown={unknown}")
        observations = tuple(
            validate_scenario_workspace(scenario, workspaces[scenario.id])
            for scenario in catalog.scenarios
        )
        return self.run(catalog, observations, runner=runner)

    @staticmethod
    def _normalize_observations(
        observations: Mapping[str, ScenarioObservation] | Iterable[ScenarioObservation],
    ) -> dict[str, ScenarioObservation]:
        if isinstance(observations, Mapping):
            normalized = dict(observations)
            for key, observation in normalized.items():
                if key != observation.scenario_id:
                    raise EvaluationInputError("observation mapping key does not match scenario_id")
            return normalized
        normalized: dict[str, ScenarioObservation] = {}
        for observation in observations:
            if observation.scenario_id in normalized:
                raise EvaluationInputError(f"duplicate observation: {observation.scenario_id}")
            normalized[observation.scenario_id] = observation
        return normalized

    def _score_scenario(
        self,
        scenario: ScenarioDefinition,
        observation: ScenarioObservation,
    ) -> ScenarioReport:
        sensitive_values = (scenario.task,)
        fixture_checksum = scenario.fixture_checksum
        validator_checksum = scenario.validator_checksum
        if fixture_checksum is None or validator_checksum is None:
            raise EvaluationInputError(f"scenario {scenario.id!r} has no verified checksums")
        if observation.blocked:
            return ScenarioReport(
                scenario_id=scenario.id,
                scenario_revision=scenario.revision,
                fixture_id=scenario.fixture_id,
                fixture_checksum=fixture_checksum,
                validator_checksum=validator_checksum,
                mode=scenario.mode,
                outcome=RunOutcome.BLOCKED,
                score=0,
                failure_attribution=observation.failure_attribution,
                error_summary=sanitize_summary(
                    observation.error_summary, sensitive_values=sensitive_values
                ),
                criteria=(),
            )

        expected_criteria = {criterion.id: criterion for criterion in scenario.criteria}
        observed_criteria = {criterion.criterion_id: criterion for criterion in observation.criteria}
        if missing := sorted(set(expected_criteria) - set(observed_criteria)):
            raise EvaluationInputError(
                f"scenario {scenario.id!r} is missing criteria: {', '.join(missing)}"
            )
        if unknown := sorted(set(observed_criteria) - set(expected_criteria)):
            raise EvaluationInputError(
                f"scenario {scenario.id!r} has unknown criteria: {', '.join(unknown)}"
            )

        total_weight = sum(criterion.weight for criterion in scenario.criteria)
        passed_weight = 0.0
        required_passed = True
        criterion_reports: list[CriterionReport] = []
        for definition in scenario.criteria:
            result = observed_criteria[definition.id]
            is_passed = result.state is CriterionState.PASSED
            if is_passed:
                passed_weight += definition.weight
            elif definition.required:
                required_passed = False
            criterion_reports.append(
                CriterionReport(
                    criterion_id=definition.id,
                    state=result.state,
                    score=1.0 if is_passed else 0.0,
                    summary=sanitize_summary(result.summary, sensitive_values=sensitive_values),
                )
            )
        score = round(passed_weight / total_weight, 6)
        if required_passed and score >= scenario.pass_threshold:
            outcome = RunOutcome.PASSED
            attribution = None
        elif score > 0:
            outcome = RunOutcome.PARTIAL
            attribution = observation.failure_attribution or FailureAttribution.AMBIGUOUS
        else:
            outcome = RunOutcome.FAILED
            attribution = observation.failure_attribution or FailureAttribution.AMBIGUOUS
        return ScenarioReport(
            scenario_id=scenario.id,
            scenario_revision=scenario.revision,
            fixture_id=scenario.fixture_id,
            fixture_checksum=fixture_checksum,
            validator_checksum=validator_checksum,
            mode=scenario.mode,
            outcome=outcome,
            score=score,
            failure_attribution=attribution,
            error_summary=sanitize_summary(observation.error_summary, sensitive_values=sensitive_values),
            criteria=tuple(criterion_reports),
        )

    @classmethod
    def _build_summary(cls, reports: tuple[ScenarioReport, ...]) -> EvaluationSummary:
        by_mode = {
            mode: cls._counts(tuple(report for report in reports if report.mode is mode))
            for mode in ScenarioMode
        }
        totals = cls._counts(reports)
        return EvaluationSummary(**totals.model_dump(), by_mode=by_mode)

    @staticmethod
    def _counts(reports: tuple[ScenarioReport, ...]) -> OutcomeCounts:
        total = len(reports)
        eligible = tuple(report for report in reports if report.outcome is not RunOutcome.BLOCKED)
        eligible_total = len(eligible)
        return OutcomeCounts(
            total=total,
            eligible_total=eligible_total,
            passed=sum(report.outcome is RunOutcome.PASSED for report in reports),
            partial=sum(report.outcome is RunOutcome.PARTIAL for report in reports),
            failed=sum(report.outcome is RunOutcome.FAILED for report in reports),
            blocked=sum(report.outcome is RunOutcome.BLOCKED for report in reports),
            weighted_score=(
                round(sum(report.score for report in eligible) / eligible_total, 6)
                if eligible_total
                else 0
            ),
            coverage=round(eligible_total / total, 6) if total else 0,
        )

    @staticmethod
    def _build_report_id(
        catalog: ScenarioCatalog,
        runner: RunnerDescriptor,
        reports: tuple[ScenarioReport, ...],
    ) -> str:
        identity = {
            "catalog_id": catalog.catalog_id,
            "runner": runner.model_dump(mode="json"),
            "scenarios": [report.model_dump(mode="json") for report in reports],
        }
        serialized = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
        return f"eval-{digest}"
