from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_serializer,
    field_validator,
    model_validator,
)
from tool_platform.models import (
    FrozenJsonObject,
    freeze_json_object,
    jsonable,
    redact_json,
)

WORK_UNIT_SCHEMA_VERSION = "agent.work_unit.v1"
WORK_UNIT_RESULT_SCHEMA_VERSION = "agent.work_unit.result.v1"
WORK_UNIT_RUN_SCOPE_SCHEMA_VERSION = "agent.work_unit.run_scope.v1"

WorkUnitPhase = Literal["inspect", "plan", "implement", "verify", "review", "deliver"]
WorkUnitOwner = Literal["parent_build", "explore_child", "review_child"]
WorkUnitStatus = Literal[
    "planned",
    "blocked",
    "ready",
    "running",
    "retrying",
    "completed",
    "degraded",
    "cancelled",
]
WorkUnitVerdict = Literal["pass", "changes_required", "completed", "degraded"]
WorkUnitConcurrencyClass = Literal["parent_serial", "readonly_parallel"]

WORK_UNIT_TERMINAL_STATUSES: frozenset[WorkUnitStatus] = frozenset(
    {"completed", "degraded", "cancelled"}
)
MAX_WORK_UNIT_ATTEMPTS = 6
MAX_WORK_UNITS_PER_PLAN = 12

_FORBIDDEN_FIELD_PATTERN = re.compile(
    r"(chain[_-]?of[_-]?thought|reasoning|scratchpad|thoughts?)",
    re.IGNORECASE,
)
_WINDOWS_ABSOLUTE_PATTERN = re.compile(r"^[a-zA-Z]:[/\\]")
_WORK_UNIT_ID_PATTERN = re.compile(r"^wu_[A-Za-z0-9_-]{8,200}$")
_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _find_forbidden_keys(raw: object, *, prefix: str = "") -> list[str]:
    if isinstance(raw, Mapping):
        hits: list[str] = []
        for key, value in raw.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            if _FORBIDDEN_FIELD_PATTERN.search(key_text):
                hits.append(path)
            hits.extend(_find_forbidden_keys(value, prefix=path))
        return hits
    if isinstance(raw, list | tuple):
        hits = []
        for index, value in enumerate(raw):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            hits.extend(_find_forbidden_keys(value, prefix=path))
        return hits
    return []


def _tuple_from_json(value: object) -> object:
    return tuple(value) if isinstance(value, list) else value


def _safe_relative_reference(value: str, *, label: str) -> str:
    normalized = value.strip().replace("\\", "/")
    if (
        not normalized
        or normalized.startswith(("/", "//", "~"))
        or _WINDOWS_ABSOLUTE_PATTERN.match(normalized)
        or ".." in normalized.split("/")
    ):
        raise ValueError(f"{label} must be a workspace-relative logical reference")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized:
        raise ValueError(f"{label} must be a workspace-relative logical reference")
    return normalized.rstrip("/")


def _redact_text(value: str) -> str:
    redacted = redact_json(value)
    return redacted if isinstance(redacted, str) else value


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        validate_default=True,
    )

    @model_validator(mode="before")
    @classmethod
    def reject_hidden_reasoning(cls, value: object) -> object:
        forbidden = _find_forbidden_keys(value)
        if forbidden:
            raise ValueError(f"forbidden WorkUnit fields: {', '.join(forbidden)}")
        return value


class WorkUnitEvidenceRef(_StrictFrozenModel):
    ref_type: Literal["source", "test", "artifact", "event", "tool"]
    ref_id: str = Field(min_length=1, max_length=500)
    label: str = Field(min_length=1, max_length=500)

    @field_validator("ref_id")
    @classmethod
    def validate_ref_id(cls, value: str) -> str:
        if value.startswith(("/", "\\")) or _WINDOWS_ABSOLUTE_PATTERN.match(value):
            raise ValueError("evidence ref_id must be a logical reference")
        return _redact_text(value.strip())

    @field_validator("label")
    @classmethod
    def redact_label(cls, value: str) -> str:
        return _redact_text(value.strip())


class WorkUnitArtifactRef(_StrictFrozenModel):
    kind: Literal["analysis", "diff", "test_report", "log", "summary", "other"]
    logical_ref: str = Field(min_length=1, max_length=500)

    @field_validator("logical_ref")
    @classmethod
    def validate_logical_ref(cls, value: str) -> str:
        return _safe_relative_reference(value, label="artifact logical_ref")


class WorkUnitFinding(_StrictFrozenModel):
    finding_id: str = Field(min_length=1, max_length=200)
    severity: Literal["low", "medium", "high"]
    summary: str = Field(min_length=1, max_length=10_000)
    evidence_refs: tuple[WorkUnitEvidenceRef, ...] = ()

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def tuple_evidence_refs(cls, value: object) -> object:
        return _tuple_from_json(value)

    @field_validator("summary")
    @classmethod
    def redact_summary(cls, value: str) -> str:
        return _redact_text(value.strip())

    @model_validator(mode="after")
    def high_severity_requires_evidence(self) -> WorkUnitFinding:
        if self.severity == "high" and not self.evidence_refs:
            raise ValueError("high-severity findings require evidence")
        return self


class WorkUnitFileScope(_StrictFrozenModel):
    path: str = Field(min_length=1, max_length=1_000)
    mode: Literal["read", "write", "read_write"]

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _safe_relative_reference(value, label="file scope path")


class WorkUnitDependency(_StrictFrozenModel):
    work_unit_id: str = Field(min_length=1, max_length=203)
    kind: Literal["depends_on", "blocks"] = "depends_on"


class WorkUnitToolProjection(_StrictFrozenModel):
    catalog_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    allowed_tools: tuple[str, ...]
    facts: FrozenJsonObject = Field(default_factory=dict, repr=False)

    @field_validator("allowed_tools", mode="before")
    @classmethod
    def tuple_allowed_tools(cls, value: object) -> object:
        return _tuple_from_json(value)

    @field_validator("allowed_tools")
    @classmethod
    def validate_allowed_tools(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("allowed_tools must be unique")
        if any(not item or item != item.strip() for item in value):
            raise ValueError("allowed_tools must contain normalized names")
        return value

    @field_serializer("facts")
    def serialize_facts(self, value: FrozenJsonObject) -> JsonValue:
        return jsonable(value)


class WorkUnitBudget(_StrictFrozenModel):
    max_attempts: int = Field(ge=1, le=MAX_WORK_UNIT_ATTEMPTS)
    max_model_calls: int = Field(ge=1, le=100)
    timeout_seconds: int = Field(ge=1, le=3_600)
    concurrency_class: WorkUnitConcurrencyClass


class WorkUnitVerificationRequirement(_StrictFrozenModel):
    requirement_id: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5_000)
    command: str | None = Field(default=None, max_length=5_000)
    required: bool = True

    @field_validator("description")
    @classmethod
    def redact_description(cls, value: str) -> str:
        return _redact_text(value.strip())

    @field_validator("command")
    @classmethod
    def redact_command(cls, value: str | None) -> str | None:
        return _redact_text(value.strip()) if value is not None else None


class WorkUnitRetryPolicy(_StrictFrozenModel):
    max_retries: int = Field(ge=0, le=5)
    retry_all_failures: Literal[True] = True


class WorkUnitCancellation(_StrictFrozenModel):
    cascade_on_parent_cancel: Literal[True] = True
    cancel_on_stale_plan: Literal[True] = True


class WorkUnit(_StrictFrozenModel):
    schema_version: Literal["agent.work_unit.v1"]
    work_unit_id: str = Field(pattern=r"^wu_[A-Za-z0-9_-]{8,200}$")
    parent_session_id: str = Field(min_length=1, max_length=200)
    plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_id: str = Field(min_length=1, max_length=200)
    phase: WorkUnitPhase
    owner: WorkUnitOwner
    title: str = Field(min_length=1, max_length=500)
    instruction: str = Field(min_length=1, max_length=20_000)
    dependencies: tuple[WorkUnitDependency, ...] = ()
    file_scopes: tuple[WorkUnitFileScope, ...]
    tool_projection: WorkUnitToolProjection
    budget: WorkUnitBudget
    verification_requirements: tuple[WorkUnitVerificationRequirement, ...] = ()
    expected_artifacts: tuple[WorkUnitArtifactRef, ...] = ()
    retry_policy: WorkUnitRetryPolicy
    cancellation: WorkUnitCancellation = Field(default_factory=WorkUnitCancellation)

    @field_validator(
        "dependencies",
        "file_scopes",
        "verification_requirements",
        "expected_artifacts",
        mode="before",
    )
    @classmethod
    def tuple_collections(cls, value: object) -> object:
        return _tuple_from_json(value)

    @field_validator("title", "instruction")
    @classmethod
    def redact_text_fields(cls, value: str) -> str:
        return _redact_text(value.strip())

    @model_validator(mode="after")
    def validate_authority_and_budget(self) -> WorkUnit:
        if self.budget.max_attempts != self.retry_policy.max_retries + 1:
            raise ValueError("max_attempts must equal max_retries + 1")
        if self.owner == "parent_build":
            if self.budget.concurrency_class != "parent_serial":
                raise ValueError("parent Build WorkUnits require parent_serial concurrency")
        else:
            if self.budget.concurrency_class != "readonly_parallel":
                raise ValueError("child WorkUnits require readonly_parallel concurrency")
            if any(scope.mode != "read" for scope in self.file_scopes):
                raise ValueError("child WorkUnit file scopes must be read-only")
        if self.owner == "explore_child" and self.phase not in {"inspect", "plan"}:
            raise ValueError("Explore child WorkUnits are limited to Inspect and Plan")
        if self.owner == "review_child" and self.phase != "review":
            raise ValueError("Review child WorkUnits are limited to Review")
        dependency_ids = [item.work_unit_id for item in self.dependencies]
        if len(dependency_ids) != len(set(dependency_ids)):
            raise ValueError("WorkUnit dependencies must be unique")
        if self.work_unit_id in dependency_ids:
            raise ValueError("WorkUnit cannot depend on itself")
        return self


class WorkUnitAttempt(_StrictFrozenModel):
    work_unit_id: str = Field(min_length=1, max_length=203)
    attempt: int = Field(ge=1, le=MAX_WORK_UNIT_ATTEMPTS)
    status: Literal["running", "completed", "failed", "cancelled"]
    child_session_id: str | None = Field(default=None, min_length=1, max_length=200)


class WorkUnitRunScope(_StrictFrozenModel):
    schema_version: Literal["agent.work_unit.run_scope.v1"] = (
        WORK_UNIT_RUN_SCOPE_SCHEMA_VERSION
    )
    type: Literal["work_unit"] = "work_unit"
    work_unit_id: str = Field(min_length=1, max_length=203)
    attempt: int = Field(ge=1, le=MAX_WORK_UNIT_ATTEMPTS)
    phase: WorkUnitPhase
    finalize_session: bool = False

    @model_validator(mode="after")
    def only_deliver_finalizes(self) -> WorkUnitRunScope:
        if self.finalize_session and self.phase != "deliver":
            raise ValueError("only a Deliver WorkUnit may finalize the session")
        return self


class WorkUnitResult(_StrictFrozenModel):
    schema_version: Literal["agent.work_unit.result.v1"]
    work_unit_id: str = Field(min_length=1, max_length=203)
    attempt: int = Field(ge=1, le=MAX_WORK_UNIT_ATTEMPTS)
    verdict: WorkUnitVerdict
    summary: str = Field(min_length=1, max_length=20_000)
    findings: tuple[WorkUnitFinding, ...] = ()
    evidence_refs: tuple[WorkUnitEvidenceRef, ...] = ()
    artifact_refs: tuple[WorkUnitArtifactRef, ...] = ()
    recommended_next_phase: WorkUnitPhase | None = None
    diagnostic: FrozenJsonObject = Field(default_factory=dict, repr=False)

    @field_validator(
        "findings",
        "evidence_refs",
        "artifact_refs",
        mode="before",
    )
    @classmethod
    def tuple_collections(cls, value: object) -> object:
        return _tuple_from_json(value)

    @field_validator("summary")
    @classmethod
    def redact_summary(cls, value: str) -> str:
        return _redact_text(value.strip())

    @field_validator("diagnostic")
    @classmethod
    def redact_diagnostic(cls, value: FrozenJsonObject) -> FrozenJsonObject:
        if not isinstance(value, Mapping):
            raise ValueError("diagnostic must be a JSON object")
        return freeze_json_object(cast(Mapping[str, JsonValue], redact_json(value)))

    @field_serializer("diagnostic")
    def serialize_diagnostic(self, value: FrozenJsonObject) -> JsonValue:
        return jsonable(value)


_ALLOWED_STATUS_TRANSITIONS: dict[WorkUnitStatus, frozenset[WorkUnitStatus]] = {
    "planned": frozenset({"blocked", "ready", "cancelled"}),
    "blocked": frozenset({"ready", "cancelled"}),
    "ready": frozenset({"running", "cancelled"}),
    "running": frozenset(
        {"completed", "degraded", "retrying", "cancelled"}
    ),
    "retrying": frozenset({"running", "degraded", "cancelled"}),
    "completed": frozenset(),
    "degraded": frozenset(),
    "cancelled": frozenset(),
}


def can_transition_work_unit_status(
    current: WorkUnitStatus | str,
    target: WorkUnitStatus | str,
) -> bool:
    if current == target:
        return True
    if current not in _ALLOWED_STATUS_TRANSITIONS:
        return False
    return target in _ALLOWED_STATUS_TRANSITIONS[current]  # type: ignore[operator]


def require_work_unit_status_transition(
    current: WorkUnitStatus | str,
    target: WorkUnitStatus | str,
) -> None:
    if not can_transition_work_unit_status(current, target):
        raise ValueError(f"invalid WorkUnit status transition: {current} -> {target}")


def parse_work_unit(raw: object) -> WorkUnit:
    return WorkUnit.model_validate(raw, strict=True)


def serialize_work_unit(work_unit: WorkUnit) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], work_unit.model_dump(mode="json"))


def parse_work_unit_result(raw: object) -> WorkUnitResult:
    return WorkUnitResult.model_validate(raw, strict=True)


def serialize_work_unit_result(result: WorkUnitResult) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], result.model_dump(mode="json"))


__all__ = [
    "MAX_WORK_UNIT_ATTEMPTS",
    "MAX_WORK_UNITS_PER_PLAN",
    "WORK_UNIT_RESULT_SCHEMA_VERSION",
    "WORK_UNIT_RUN_SCOPE_SCHEMA_VERSION",
    "WORK_UNIT_SCHEMA_VERSION",
    "WORK_UNIT_TERMINAL_STATUSES",
    "WorkUnit",
    "WorkUnitArtifactRef",
    "WorkUnitAttempt",
    "WorkUnitBudget",
    "WorkUnitCancellation",
    "WorkUnitConcurrencyClass",
    "WorkUnitDependency",
    "WorkUnitEvidenceRef",
    "WorkUnitFileScope",
    "WorkUnitFinding",
    "WorkUnitOwner",
    "WorkUnitPhase",
    "WorkUnitResult",
    "WorkUnitRetryPolicy",
    "WorkUnitRunScope",
    "WorkUnitStatus",
    "WorkUnitToolProjection",
    "WorkUnitVerdict",
    "WorkUnitVerificationRequirement",
    "can_transition_work_unit_status",
    "parse_work_unit",
    "parse_work_unit_result",
    "require_work_unit_status_transition",
    "serialize_work_unit",
    "serialize_work_unit_result",
]
