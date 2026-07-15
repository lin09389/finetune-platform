"""Strict schema-v1 models for local Agent capability evaluation."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = 1
RUNNER_VERSION = "1.0"
REDACTION_VERSION = "1.0"

Identifier = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")]
CriterionIdentifier = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,63}$")]


class StrictModel(BaseModel):
    """Forbid silent schema drift at every persistence boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ScenarioMode(StrEnum):
    CODING = "coding"
    TRAINING = "training"
    HYBRID = "hybrid"


class TaskCategory(StrEnum):
    FEATURE = "feature"
    DEBUG = "debug"
    REFACTOR = "refactor"
    TRAINING = "training"
    HYBRID = "hybrid"


class RunOutcome(StrEnum):
    PASSED = "passed"
    PARTIAL = "partial"
    FAILED = "failed"
    BLOCKED = "blocked"


class FailureAttribution(StrEnum):
    PLATFORM = "platform"
    MODEL = "model"
    ENVIRONMENT = "environment"
    AMBIGUOUS = "ambiguous"


class CriterionState(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class ValidatorKind(StrEnum):
    FILE_CONTAINS = "file_contains"
    FILE_NOT_CONTAINS = "file_not_contains"
    JSON_EQUALS = "json_equals"
    PYTHON_SYNTAX = "python_syntax"


class DecisionSource(StrEnum):
    DETERMINISTIC = "deterministic"
    LIVE = "live"


class RunnerKind(StrEnum):
    DETERMINISTIC = "deterministic"
    REAL_MODEL = "real_model"


def _validate_portable_path(value: str) -> str:
    if "\\" in value or value.startswith("/") or ":" in value:
        raise ValueError("path must be a portable relative POSIX path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("path contains an unsafe segment")
    return value


class ValidatorDefinition(StrictModel):
    criterion_id: CriterionIdentifier
    kind: ValidatorKind
    path: str = Field(min_length=1, max_length=180)
    expected: str | int | float | bool | None = None
    json_pointer: str | None = Field(default=None, max_length=180)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_portable_path(value)

    @model_validator(mode="after")
    def validate_kind_arguments(self) -> "ValidatorDefinition":
        if self.kind in {ValidatorKind.FILE_CONTAINS, ValidatorKind.FILE_NOT_CONTAINS}:
            if not isinstance(self.expected, str) or not self.expected:
                raise ValueError(f"{self.kind.value} requires a non-empty string expected value")
            if self.json_pointer is not None:
                raise ValueError(f"{self.kind.value} does not accept json_pointer")
        elif self.kind is ValidatorKind.JSON_EQUALS:
            if not self.json_pointer or not self.json_pointer.startswith("/"):
                raise ValueError("json_equals requires an RFC 6901-style json_pointer")
        elif self.kind is ValidatorKind.PYTHON_SYNTAX:
            if self.expected is not None or self.json_pointer is not None:
                raise ValueError("python_syntax does not accept expected or json_pointer")
        return self


class CriterionDefinition(StrictModel):
    id: CriterionIdentifier
    description: str = Field(min_length=3, max_length=300)
    weight: float = Field(default=1.0, gt=0, le=100)
    required: bool = True


class ScenarioDefinition(StrictModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    id: Identifier
    revision: int = Field(default=1, ge=1)
    title: str = Field(min_length=3, max_length=120)
    mode: ScenarioMode
    category: TaskCategory
    stacks: tuple[str, ...] = Field(min_length=1, max_length=8)
    fixture_id: str = Field(min_length=3, max_length=180)
    task: str = Field(min_length=10, max_length=2000)
    pass_threshold: float = Field(default=1.0, gt=0, le=1)
    criteria: tuple[CriterionDefinition, ...] = Field(min_length=1, max_length=20)
    tags: tuple[str, ...] = Field(default=(), max_length=12)
    validators: tuple[ValidatorDefinition, ...] = ()
    fixture_checksum: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")
    validator_checksum: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")

    @field_validator("schema_version", "revision", mode="before")
    @classmethod
    def reject_boolean_integers(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("boolean values are not valid integer versions")
        return value

    @field_validator("fixture_id")
    @classmethod
    def validate_relative_fixture_id(cls, value: str) -> str:
        if "\\" in value or value.startswith("/") or ":" in value:
            raise ValueError("fixture_id must be a portable relative POSIX path")
        parts = value.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("fixture_id contains an unsafe path segment")
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789._-/")
        if any(character not in allowed for character in value):
            raise ValueError("fixture_id contains a non-portable character")
        return value

    @field_validator("stacks", "tags")
    @classmethod
    def validate_labels(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip().lower() for value in values)
        if any(not value or len(value) > 40 for value in normalized):
            raise ValueError("labels must contain 1 to 40 characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("labels must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_unique_criteria(self) -> "ScenarioDefinition":
        criterion_ids = [criterion.id for criterion in self.criteria]
        if len(set(criterion_ids)) != len(criterion_ids):
            raise ValueError(f"scenario {self.id!r} contains duplicate criterion ids")
        return self


class ScenarioCatalog(StrictModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    catalog_id: Identifier
    scenarios: tuple[ScenarioDefinition, ...] = Field(min_length=1)
    catalog_checksum: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")

    @field_validator("schema_version", mode="before")
    @classmethod
    def reject_boolean_version(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("boolean values are not valid schema versions")
        return value

    @model_validator(mode="after")
    def validate_catalog(self) -> "ScenarioCatalog":
        scenario_ids = [scenario.id for scenario in self.scenarios]
        if len(set(scenario_ids)) != len(scenario_ids):
            raise ValueError("catalog contains duplicate scenario ids")
        if any(scenario.schema_version != self.schema_version for scenario in self.scenarios):
            raise ValueError("scenario schema version does not match catalog")
        return self


class CriterionObservation(StrictModel):
    criterion_id: CriterionIdentifier
    state: CriterionState
    summary: str | None = Field(default=None, max_length=20_000)


class ScenarioObservation(StrictModel):
    scenario_id: Identifier
    criteria: tuple[CriterionObservation, ...] = ()
    blocked: bool = False
    failure_attribution: FailureAttribution | None = None
    error_summary: str | None = Field(default=None, max_length=20_000)

    @model_validator(mode="after")
    def validate_observation(self) -> "ScenarioObservation":
        criterion_ids = [criterion.criterion_id for criterion in self.criteria]
        if len(set(criterion_ids)) != len(criterion_ids):
            raise ValueError("observation contains duplicate criterion ids")
        if self.blocked and self.failure_attribution is None:
            raise ValueError("blocked observations require failure_attribution")
        return self


class CriterionReport(StrictModel):
    criterion_id: CriterionIdentifier
    state: CriterionState
    score: float = Field(ge=0, le=1)
    summary: str | None = Field(default=None, max_length=512)


class ScenarioReport(StrictModel):
    scenario_id: Identifier
    scenario_revision: int = Field(ge=1)
    fixture_id: str
    fixture_checksum: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    validator_checksum: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    mode: ScenarioMode
    outcome: RunOutcome
    score: float = Field(ge=0, le=1)
    failure_attribution: FailureAttribution | None = None
    error_summary: str | None = Field(default=None, max_length=512)
    criteria: tuple[CriterionReport, ...]

    @model_validator(mode="after")
    def validate_failure_attribution(self) -> "ScenarioReport":
        if self.outcome is RunOutcome.PASSED and self.failure_attribution is not None:
            raise ValueError("passed results cannot have failure attribution")
        if self.outcome is not RunOutcome.PASSED and self.failure_attribution is None:
            raise ValueError("non-passed results require failure attribution")
        return self


class OutcomeCounts(StrictModel):
    total: int = Field(ge=0)
    eligible_total: int = Field(ge=0)
    passed: int = Field(ge=0)
    partial: int = Field(ge=0)
    failed: int = Field(ge=0)
    blocked: int = Field(ge=0)
    weighted_score: float = Field(ge=0, le=1)
    coverage: float = Field(ge=0, le=1)


class EvaluationSummary(OutcomeCounts):
    by_mode: dict[ScenarioMode, OutcomeCounts]


class RunnerDescriptor(StrictModel):
    kind: RunnerKind
    decision_source: DecisionSource
    version: str = RUNNER_VERSION
    model_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_model_id(self) -> "RunnerDescriptor":
        if self.kind is RunnerKind.DETERMINISTIC and self.model_id is not None:
            raise ValueError("deterministic reports cannot declare model_id")
        if self.kind is RunnerKind.REAL_MODEL and self.model_id is None:
            raise ValueError("real-model reports require model_id")
        expected_source = (
            DecisionSource.DETERMINISTIC
            if self.kind is RunnerKind.DETERMINISTIC
            else DecisionSource.LIVE
        )
        if self.decision_source is not expected_source:
            raise ValueError("runner kind and decision_source disagree")
        return self


class SuiteDescriptor(StrictModel):
    catalog_id: Identifier
    scenario_count: int = Field(ge=1)
    catalog_checksum: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


class UsageSummary(StrictModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    tool_calls: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)


class LiveExecutionBudget(StrictModel):
    """Hard limits supplied to the runtime adapter for one scenario."""

    timeout_seconds: int = Field(ge=1, le=3600)
    max_input_tokens: int = Field(ge=1, le=2_000_000)
    max_output_tokens: int = Field(ge=1, le=200_000)
    max_tool_calls: int = Field(ge=1, le=1000)
    max_cost_usd: float = Field(gt=0, le=100)


class LiveExecutionResult(StrictModel):
    """Sanitized result returned by an existing AgentSessionService adapter."""

    observation: ScenarioObservation
    usage: UsageSummary = UsageSummary()


class ReportProvenance(StrictModel):
    app_revision: str | None = Field(default=None, max_length=100)
    git_revision: str | None = Field(default=None, max_length=100)
    provider: str | None = Field(default=None, max_length=100)
    parameters_digest: str | None = Field(default=None, max_length=100)
    seed: int | None = None


class PrivacyDescriptor(StrictModel):
    redaction_version: str = REDACTION_VERSION
    contains_prompts: Literal[False] = False
    contains_source: Literal[False] = False
    contains_absolute_paths: Literal[False] = False
    contains_secrets: Literal[False] = False


class EvaluationReport(StrictModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    report_id: str = Field(pattern=r"^eval-[a-f0-9]{16}$")
    runner: RunnerDescriptor
    suite: SuiteDescriptor
    summary: EvaluationSummary
    scenarios: tuple[ScenarioReport, ...]
    usage: UsageSummary = UsageSummary()
    provenance: ReportProvenance = ReportProvenance()
    privacy: PrivacyDescriptor = PrivacyDescriptor()


class RealModelRunOptions(StrictModel):
    """A dry run is the safe default; live execution needs two explicit gates."""

    dry_run: bool = True
    explicit_opt_in: bool = False
    model_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    scenario_ids: tuple[Identifier, ...] | None = None
    timeout_seconds: int = Field(default=900, ge=1, le=3600)
    max_input_tokens: int = Field(default=200_000, ge=1, le=2_000_000)
    max_output_tokens: int = Field(default=20_000, ge=1, le=200_000)
    max_tool_calls: int = Field(default=100, ge=1, le=1000)
    max_cost_usd: float = Field(default=5.0, gt=0, le=100)

    @model_validator(mode="after")
    def validate_scenario_ids(self) -> "RealModelRunOptions":
        if self.scenario_ids is not None and len(set(self.scenario_ids)) != len(self.scenario_ids):
            raise ValueError("scenario_ids must be unique")
        return self


class RealModelRunPlan(StrictModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    runner: Literal["real_model"] = "real_model"
    dry_run: bool
    explicit_opt_in: bool
    would_execute: bool
    server_enabled: bool
    model_id: str
    catalog_id: Identifier
    scenario_ids: tuple[Identifier, ...]
    fixture_ids: tuple[str, ...]
    timeout_seconds: int
    max_input_tokens: int
    max_output_tokens: int
    max_tool_calls: int
    max_cost_usd: float


class ScenarioOracle(StrictModel):
    scenario_id: Identifier
    validators: tuple[ValidatorDefinition, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_unique_criteria(self) -> "ScenarioOracle":
        ids = [validator.criterion_id for validator in self.validators]
        if len(set(ids)) != len(ids):
            raise ValueError("oracle contains duplicate criterion ids")
        return self


class OracleCatalog(StrictModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    scenarios: tuple[ScenarioOracle, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_scenarios(self) -> "OracleCatalog":
        ids = [scenario.scenario_id for scenario in self.scenarios]
        if len(set(ids)) != len(ids):
            raise ValueError("oracle catalog contains duplicate scenario ids")
        return self
