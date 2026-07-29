from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
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
    CanonicalToolMeta,
    FrozenJsonObject,
    freeze_json_object,
    jsonable,
    redact_json,
)
from tool_platform.taxonomy import SideEffect

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
WorkUnitCompilationMode = Literal["compiled", "parent_only"]

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
_CANONICAL_PHASE_OWNERS: dict[WorkUnitPhase, WorkUnitOwner] = {
    "inspect": "explore_child",
    "plan": "explore_child",
    "implement": "parent_build",
    "verify": "parent_build",
    "review": "review_child",
    "deliver": "parent_build",
}
_ARTIFACT_KIND_BY_PHASE: dict[
    WorkUnitPhase,
    Literal["analysis", "diff", "test_report", "summary"],
] = {
    "inspect": "analysis",
    "plan": "analysis",
    "implement": "diff",
    "verify": "test_report",
    "review": "analysis",
    "deliver": "summary",
}
_CANONICAL_PHASE_ORDER: tuple[WorkUnitPhase, ...] = (
    "inspect",
    "plan",
    "implement",
    "verify",
    "review",
    "deliver",
)
_REQUIRED_LIFECYCLE_PHASES: frozenset[WorkUnitPhase] = frozenset(
    {"implement", "verify", "review", "deliver"}
)


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


def _safe_relative_reference(
    value: str,
    *,
    label: str,
    allow_workspace_root: bool = False,
) -> str:
    normalized = value.strip().replace("\\", "/")
    if allow_workspace_root and normalized.rstrip("/") == ".":
        return "."
    if (
        not normalized
        or normalized.startswith(("/", "//", "~"))
        or _WINDOWS_ABSOLUTE_PATTERN.match(normalized)
        or ".." in normalized.split("/")
        or ":" in normalized
        or any(ord(character) < 32 for character in normalized)
    ):
        raise ValueError(f"{label} must be a workspace-relative logical reference")
    parts = tuple(part for part in normalized.split("/") if part not in {"", "."})
    if not parts:
        raise ValueError(f"{label} must be a workspace-relative logical reference")
    return "/".join(parts)


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
        return _safe_relative_reference(
            value,
            label="file scope path",
            allow_workspace_root=True,
        )


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

    @field_validator("facts")
    @classmethod
    def redact_facts(cls, value: FrozenJsonObject) -> FrozenJsonObject:
        if not isinstance(value, Mapping):
            raise ValueError("projection facts must be a JSON object")
        return freeze_json_object(cast(Mapping[str, JsonValue], redact_json(value)))

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


class WorkUnitCompilationOutcome(_StrictFrozenModel):
    mode: WorkUnitCompilationMode
    plan_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    work_units: tuple[WorkUnit, ...] = ()
    diagnostics: FrozenJsonObject = Field(default_factory=dict, repr=False)

    @field_validator("work_units", mode="before")
    @classmethod
    def tuple_work_units(cls, value: object) -> object:
        return _tuple_from_json(value)

    @field_validator("diagnostics")
    @classmethod
    def redact_diagnostics(cls, value: FrozenJsonObject) -> FrozenJsonObject:
        if not isinstance(value, Mapping):
            raise ValueError("diagnostics must be a JSON object")
        return freeze_json_object(cast(Mapping[str, JsonValue], redact_json(value)))

    @field_serializer("diagnostics")
    def serialize_diagnostics(self, value: FrozenJsonObject) -> JsonValue:
        return jsonable(value)

    @model_validator(mode="after")
    def validate_mode(self) -> WorkUnitCompilationOutcome:
        if self.mode == "compiled":
            if self.plan_fingerprint is None or not self.work_units:
                raise ValueError("compiled WorkUnit outcomes require a plan and units")
        elif self.work_units:
            raise ValueError("parent-only outcomes cannot contain WorkUnits")
        return self


class WorkUnitCompilationError(ValueError):
    def __init__(self, reason_code: str, summary: str) -> None:
        super().__init__(summary)
        self.reason_code = reason_code
        self.summary = summary


def _canonical_goal_plan_document(raw_goal_plan: object) -> dict[str, JsonValue]:
    from agent_session.goal_plan import (
        GoalPlan,
        parse_goal_plan,
        serialize_goal_plan,
    )

    plan = (
        raw_goal_plan
        if isinstance(raw_goal_plan, GoalPlan)
        else parse_goal_plan(raw_goal_plan)
    )
    document = serialize_goal_plan(plan)
    document["constraints"] = sorted(set(document["constraints"]))
    document["phases"] = sorted(
        document["phases"],
        key=lambda item: (item["order"], item["id"]),
    )
    document["work_unit_candidates"] = sorted(
        document["work_unit_candidates"],
        key=lambda item: (item["phase_id"], item["id"]),
    )
    document["dependencies"] = sorted(
        {
            (item["from"], item["to"], item["kind"])
            for item in document["dependencies"]
        },
        key=lambda item: item,
    )
    document["dependencies"] = [
        {"from": source, "to": target, "kind": kind}
        for source, target, kind in document["dependencies"]
    ]
    for field in (
        "file_scopes",
        "verification_requirements",
        "risk_summaries",
    ):
        document[field] = sorted(
            document[field],
            key=lambda item: json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    return cast(dict[str, JsonValue], document)


def fingerprint_goal_plan(raw_goal_plan: object) -> str:
    encoded = json.dumps(
        _canonical_goal_plan_document(raw_goal_plan),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_work_unit_phase(
    phase_id: str,
    title: str,
) -> tuple[WorkUnitPhase, WorkUnitOwner]:
    normalized_id = phase_id.strip().casefold()
    normalized_title = title.strip().casefold()
    id_phase = next(
        (phase for phase in _CANONICAL_PHASE_ORDER if normalized_id == phase),
        None,
    )
    title_phase = next(
        (phase for phase in _CANONICAL_PHASE_ORDER if normalized_title == phase),
        None,
    )
    if id_phase is not None and title_phase is not None and id_phase != title_phase:
        return "implement", "parent_build"
    recognized = id_phase or title_phase
    if recognized is not None:
        return recognized, _CANONICAL_PHASE_OWNERS[recognized]
    return "implement", "parent_build"


def _phase_is_ambiguous(phase_id: str, title: str) -> bool:
    normalized_id = phase_id.strip().casefold()
    normalized_title = title.strip().casefold()
    id_phase = next(
        (phase for phase in _CANONICAL_PHASE_ORDER if normalized_id == phase),
        None,
    )
    title_phase = next(
        (phase for phase in _CANONICAL_PHASE_ORDER if normalized_title == phase),
        None,
    )
    return id_phase is not None and title_phase is not None and id_phase != title_phase


def build_parent_only_fallback(
    *,
    reason_code: str,
    summary: str,
    plan_fingerprint: str | None = None,
) -> WorkUnitCompilationOutcome:
    return WorkUnitCompilationOutcome(
        mode="parent_only",
        plan_fingerprint=plan_fingerprint,
        diagnostics={
            "reason_code": reason_code,
            "summary": summary,
            "recoverable": True,
        },
    )


def _parse_file_scopes(
    raw_scopes: Sequence[WorkUnitFileScope | Mapping[str, object]],
) -> tuple[WorkUnitFileScope, ...]:
    scopes = tuple(
        scope
        if isinstance(scope, WorkUnitFileScope)
        else WorkUnitFileScope.model_validate(scope, strict=True)
        for scope in raw_scopes
    )
    if not scopes:
        raise WorkUnitCompilationError(
            "parent_scope_missing",
            "The parent Build runtime has no trusted file scope.",
        )
    return scopes


def _scope_contains(parent: WorkUnitFileScope, child: WorkUnitFileScope) -> bool:
    parent_path = parent.path.rstrip("/").casefold()
    child_path = child.path.rstrip("/").casefold()
    path_allowed = (
        parent_path == "."
        or child_path == parent_path
        or child_path.startswith(f"{parent_path}/")
    )
    if not path_allowed:
        return False
    allowed_modes: dict[str, frozenset[str]] = {
        "read": frozenset({"read"}),
        "write": frozenset({"write"}),
        "read_write": frozenset({"read", "write", "read_write"}),
    }
    return child.mode in allowed_modes[parent.mode]


def _compile_goal_scopes(
    raw_scopes: Sequence[object],
    parent_scopes: tuple[WorkUnitFileScope, ...],
) -> tuple[WorkUnitFileScope, ...]:
    scopes = tuple(
        WorkUnitFileScope.model_validate(
            scope.model_dump(mode="json") if hasattr(scope, "model_dump") else scope,
            strict=True,
        )
        for scope in raw_scopes
    )
    if not scopes:
        raise WorkUnitCompilationError(
            "goal_plan_empty_scope",
            "The Goal Plan does not contain a bounded file scope.",
        )
    for scope in scopes:
        if not any(_scope_contains(parent, scope) for parent in parent_scopes):
            raise WorkUnitCompilationError(
                "file_scope_expands_parent",
                "A Goal Plan file scope exceeds the parent Workspace authority.",
            )
    return scopes


def _stable_work_unit_id(
    *,
    parent_session_id: str,
    plan_fingerprint: str,
    candidate_id: str,
) -> str:
    digest = hashlib.sha256(
        f"{parent_session_id}\x00{plan_fingerprint}\x00{candidate_id}".encode()
    ).hexdigest()
    return f"wu_{digest}"


def _projection_for_phase(
    phase: WorkUnitPhase,
    phase_tool_projections: Mapping[str, WorkUnitToolProjection | Mapping[str, object]],
) -> WorkUnitToolProjection:
    raw_projection = phase_tool_projections.get(phase)
    if raw_projection is None:
        raise WorkUnitCompilationError(
            "tool_projection_missing",
            f"The trusted tool projection for phase {phase} is missing.",
        )
    return (
        raw_projection
        if isinstance(raw_projection, WorkUnitToolProjection)
        else WorkUnitToolProjection.model_validate(raw_projection, strict=True)
    )


def _prove_child_projection_is_read_only(
    projection: WorkUnitToolProjection,
    *,
    tool_metadata_by_name: Mapping[
        str,
        CanonicalToolMeta | Mapping[str, object],
    ],
) -> None:
    for tool_name in projection.allowed_tools:
        raw_meta = tool_metadata_by_name.get(tool_name)
        if raw_meta is None:
            raise WorkUnitCompilationError(
                "child_authority_unproven",
                f"Canonical metadata is missing for child tool {tool_name}.",
            )
        meta = (
            raw_meta
            if isinstance(raw_meta, CanonicalToolMeta)
            else CanonicalToolMeta.model_validate(raw_meta, strict=True)
        )
        if meta.canonical_name != tool_name or meta.side_effects != frozenset(
            {SideEffect.NONE}
        ):
            raise WorkUnitCompilationError(
                "child_authority_unproven",
                f"Child tool {tool_name} is not proven side-effect free.",
            )


def _candidate_references(
    reference: str,
    *,
    candidate_ids: frozenset[str],
    phase_candidates: Mapping[str, tuple[str, ...]],
) -> tuple[str, ...]:
    if reference in candidate_ids:
        return (reference,)
    candidates = phase_candidates.get(reference, ())
    if not candidates:
        raise WorkUnitCompilationError(
            "dependency_reference_empty",
            f"Dependency node {reference} does not resolve to a WorkUnit.",
        )
    return candidates


def validate_work_unit_graph(
    work_units: Sequence[WorkUnit],
) -> tuple[WorkUnit, ...]:
    by_id: dict[str, WorkUnit] = {}
    for unit in work_units:
        existing = by_id.get(unit.work_unit_id)
        if existing is not None and existing != unit:
            raise ValueError(
                f"duplicate WorkUnit ID {unit.work_unit_id} has different content"
            )
        by_id[unit.work_unit_id] = unit

    if len(by_id) > MAX_WORK_UNITS_PER_PLAN:
        raise ValueError(f"WorkUnit graph exceeds {MAX_WORK_UNITS_PER_PLAN} units")

    adjacency: dict[str, set[str]] = {unit_id: set() for unit_id in by_id}
    for unit in by_id.values():
        for dependency in unit.dependencies:
            if dependency.work_unit_id not in by_id:
                raise ValueError(
                    f"WorkUnit dependency is missing: {dependency.work_unit_id}"
                )
            adjacency[dependency.work_unit_id].add(unit.work_unit_id)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(unit_id: str) -> None:
        if unit_id in visiting:
            raise ValueError("WorkUnit dependency graph contains a cycle")
        if unit_id in visited:
            return
        visiting.add(unit_id)
        for target_id in adjacency[unit_id]:
            visit(target_id)
        visiting.remove(unit_id)
        visited.add(unit_id)

    for unit_id in adjacency:
        visit(unit_id)
    return tuple(by_id.values())


def compile_work_units(
    raw_goal_plan: object,
    *,
    parent_session_id: str,
    parent_file_scopes: Sequence[WorkUnitFileScope | Mapping[str, object]],
    phase_tool_projections: Mapping[
        str,
        WorkUnitToolProjection | Mapping[str, object],
    ],
    tool_metadata_by_name: Mapping[
        str,
        CanonicalToolMeta | Mapping[str, object],
    ],
) -> WorkUnitCompilationOutcome:
    from agent_session.goal_plan import (
        GoalPlan,
        GoalPlanValidationError,
        parse_goal_plan,
    )

    if raw_goal_plan is None:
        return build_parent_only_fallback(
            reason_code="goal_plan_missing",
            summary="No Goal Plan is attached to the Build session.",
        )
    try:
        plan = (
            raw_goal_plan
            if isinstance(raw_goal_plan, GoalPlan)
            else parse_goal_plan(raw_goal_plan)
        )
    except (GoalPlanValidationError, TypeError, ValueError) as exc:
        return build_parent_only_fallback(
            reason_code="goal_plan_invalid",
            summary=f"The attached Goal Plan is invalid: {exc}",
        )
    if not plan.work_unit_candidates:
        return build_parent_only_fallback(
            reason_code="goal_plan_empty",
            summary="The attached Goal Plan contains no WorkUnit candidates.",
            plan_fingerprint=fingerprint_goal_plan(plan),
        )

    plan_fingerprint = fingerprint_goal_plan(plan)
    try:
        parent_scopes = _parse_file_scopes(parent_file_scopes)
        goal_scopes = _compile_goal_scopes(plan.file_scopes, parent_scopes)
        phase_by_id = {phase.id: phase for phase in plan.phases}
        candidate_ids = frozenset(
            candidate.id for candidate in plan.work_unit_candidates
        )
        phase_candidates = {
            phase_id: tuple(
                candidate.id
                for candidate in plan.work_unit_candidates
                if candidate.phase_id == phase_id
            )
            for phase_id in phase_by_id
        }
        stable_ids = {
            candidate.id: _stable_work_unit_id(
                parent_session_id=parent_session_id,
                plan_fingerprint=plan_fingerprint,
                candidate_id=candidate.id,
            )
            for candidate in plan.work_unit_candidates
        }
        normalized_phases = {
            candidate.id: normalize_work_unit_phase(
                phase_by_id[candidate.phase_id].id,
                phase_by_id[candidate.phase_id].title,
            )
            for candidate in plan.work_unit_candidates
        }
        lifecycle_members: dict[WorkUnitPhase, tuple[str, ...]] = {
            phase: tuple(
                candidate.id
                for candidate in plan.work_unit_candidates
                if normalized_phases[candidate.id][0] == phase
            )
            for phase in _CANONICAL_PHASE_ORDER
        }
        missing_lifecycle = sorted(
            phase
            for phase in _REQUIRED_LIFECYCLE_PHASES
            if not lifecycle_members[phase]
        )
        if missing_lifecycle:
            raise WorkUnitCompilationError(
                "canonical_lifecycle_incomplete",
                "Typed orchestration requires candidates for phases: "
                + ", ".join(missing_lifecycle),
            )
        incoming: dict[str, dict[str, Literal["depends_on", "blocks"]]] = {
            candidate.id: {} for candidate in plan.work_unit_candidates
        }
        for dependency in plan.dependencies:
            sources = _candidate_references(
                dependency.from_id,
                candidate_ids=candidate_ids,
                phase_candidates=phase_candidates,
            )
            targets = _candidate_references(
                dependency.to_id,
                candidate_ids=candidate_ids,
                phase_candidates=phase_candidates,
            )
            for target_id in targets:
                for source_id in sources:
                    if source_id == target_id:
                        raise WorkUnitCompilationError(
                            "dependency_cycle",
                            "A Goal Plan dependency resolves to the same WorkUnit.",
                        )
                    incoming[target_id][source_id] = dependency.kind

        previous_phase_members: tuple[str, ...] = ()
        for phase in _CANONICAL_PHASE_ORDER:
            current_phase_members = lifecycle_members[phase]
            if not current_phase_members:
                continue
            if previous_phase_members:
                for target_id in current_phase_members:
                    for source_id in previous_phase_members:
                        incoming[target_id].setdefault(source_id, "depends_on")
            previous_phase_members = current_phase_members

        verification_requirements = tuple(
            WorkUnitVerificationRequirement(
                requirement_id=requirement.id,
                description=requirement.description,
                command=requirement.command,
                required=requirement.required,
            )
            for requirement in plan.verification_requirements
        )
        max_retries = plan.retry_policy.max_phase_retries
        work_units: list[WorkUnit] = []
        ordered_candidates = sorted(
            plan.work_unit_candidates,
            key=lambda candidate: (
                _CANONICAL_PHASE_ORDER.index(
                    normalized_phases[candidate.id][0]
                ),
                phase_by_id[candidate.phase_id].order,
                candidate.id,
            ),
        )
        ambiguous_phase_ids = sorted(
            phase.id
            for phase in plan.phases
            if _phase_is_ambiguous(phase.id, phase.title)
        )
        for candidate in ordered_candidates:
            source_phase = phase_by_id[candidate.phase_id]
            phase, owner = normalized_phases[candidate.id]
            unit_id = stable_ids[candidate.id]
            unit_scopes = (
                tuple(
                    WorkUnitFileScope(path=scope.path, mode="read")
                    for scope in goal_scopes
                )
                if owner != "parent_build"
                else goal_scopes
            )
            work_units.append(
                WorkUnit(
                    schema_version=WORK_UNIT_SCHEMA_VERSION,
                    work_unit_id=unit_id,
                    parent_session_id=parent_session_id,
                    plan_fingerprint=plan_fingerprint,
                    candidate_id=candidate.id,
                    phase=phase,
                    owner=owner,
                    title=candidate.title,
                    instruction=(
                        f"Goal: {plan.goal}\n"
                        f"Phase: {source_phase.title}\n"
                        f"Phase summary: {source_phase.summary}\n"
                        f"WorkUnit: {candidate.summary}\n"
                        f"Constraints: {'; '.join(plan.constraints)}"
                    ),
                    dependencies=tuple(
                        WorkUnitDependency(
                            work_unit_id=stable_ids[source_id],
                            kind=kind,
                        )
                        for source_id, kind in sorted(
                            incoming[candidate.id].items()
                        )
                    ),
                    file_scopes=unit_scopes,
                    tool_projection=(
                        projection := _projection_for_phase(
                            phase,
                            phase_tool_projections,
                        )
                    ),
                    budget=WorkUnitBudget(
                        max_attempts=max_retries + 1,
                        max_model_calls=12 if owner != "parent_build" else 24,
                        timeout_seconds=600 if owner != "parent_build" else 900,
                        concurrency_class=(
                            "readonly_parallel"
                            if owner != "parent_build"
                            else "parent_serial"
                        ),
                    ),
                    verification_requirements=(
                        verification_requirements
                        if phase in {"verify", "review"}
                        else ()
                    ),
                    expected_artifacts=(
                        WorkUnitArtifactRef(
                            kind=_ARTIFACT_KIND_BY_PHASE[phase],
                            logical_ref=(
                                f"work-units/{unit_id}/"
                                f"{_ARTIFACT_KIND_BY_PHASE[phase]}"
                            ),
                        ),
                    ),
                    retry_policy=WorkUnitRetryPolicy(
                        max_retries=max_retries,
                        retry_all_failures=True,
                    ),
                )
            )
            if owner != "parent_build":
                _prove_child_projection_is_read_only(
                    projection,
                    tool_metadata_by_name=tool_metadata_by_name,
                )

        validated = validate_work_unit_graph(work_units)
    except (WorkUnitCompilationError, ValueError) as exc:
        reason_code = (
            exc.reason_code
            if isinstance(exc, WorkUnitCompilationError)
            else "work_unit_graph_invalid"
        )
        return build_parent_only_fallback(
            reason_code=reason_code,
            summary=str(exc),
            plan_fingerprint=plan_fingerprint,
        )

    return WorkUnitCompilationOutcome(
        mode="compiled",
        plan_fingerprint=plan_fingerprint,
        work_units=validated,
        diagnostics={
            "work_unit_count": len(validated),
            "compiler": WORK_UNIT_SCHEMA_VERSION,
            "model_calls": 0,
            "ambiguous_phase_ids": ambiguous_phase_ids,
        },
    )


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
    "WorkUnitCompilationError",
    "WorkUnitCompilationMode",
    "WorkUnitCompilationOutcome",
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
    "build_parent_only_fallback",
    "can_transition_work_unit_status",
    "compile_work_units",
    "fingerprint_goal_plan",
    "normalize_work_unit_phase",
    "parse_work_unit",
    "parse_work_unit_result",
    "require_work_unit_status_transition",
    "serialize_work_unit",
    "serialize_work_unit_result",
    "validate_work_unit_graph",
]
