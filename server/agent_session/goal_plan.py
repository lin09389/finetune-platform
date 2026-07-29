from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

GOAL_PLAN_SCHEMA_VERSION = "agent.goal.plan.v1"
MAX_GOAL_PLAN_WORK_UNITS = 12

_FORBIDDEN_FIELD_PATTERN = re.compile(
    r"(^|_)(reasoning|chain_of_thought|chainofthought|thinking|scratchpad|internal_monologue|hidden_thoughts|cot)(_|$)",
    re.IGNORECASE,
)
_WINDOWS_ABSOLUTE_PATTERN = re.compile(r"^[a-zA-Z]:[/\\]")


class GoalPlanValidationError(ValueError):
    """Raised when a goal plan payload is structurally or semantically invalid."""


class BoundedRetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    max_replan_attempts: int = Field(ge=0, le=2)
    max_phase_retries: int = Field(ge=0, le=5)


class GoalPlanPhase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=5_000)
    order: int = Field(ge=0)

    @field_validator("id", "title", "summary")
    @classmethod
    def _normalized_text(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("phase fields must be normalized printable text")
        return value


class WorkUnitCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(min_length=1, max_length=200)
    phase_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=10_000)

    @field_validator("id", "phase_id", "title", "summary")
    @classmethod
    def _normalized_text(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("WorkUnit candidate fields must be normalized printable text")
        return value


class GoalPlanDependency(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    from_id: str = Field(min_length=1, max_length=200, alias="from")
    to_id: str = Field(min_length=1, max_length=200, alias="to")
    kind: Literal["depends_on", "blocks"] = "depends_on"

    @field_validator("from_id", "to_id")
    @classmethod
    def _normalized_id(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("dependency IDs must be normalized printable text")
        return value


class FileScope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str = Field(min_length=1)
    mode: Literal["read", "write", "read_write"] = "read_write"

    @field_validator("path")
    @classmethod
    def _workspace_relative_path(cls, value: str) -> str:
        normalized = value.strip().replace("\\", "/")
        if normalized.rstrip("/") == ".":
            return "."
        if (
            not normalized
            or normalized.startswith(("/", "//", "~"))
            or _WINDOWS_ABSOLUTE_PATTERN.match(normalized)
            or ".." in normalized.split("/")
            or ":" in normalized
            or any(ord(character) < 32 for character in normalized)
        ):
            raise ValueError("file scope path must be workspace-relative")
        parts = tuple(part for part in normalized.split("/") if part not in {"", "."})
        if not parts:
            raise ValueError("file scope path must be workspace-relative")
        return "/".join(parts)


class VerificationRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    command: str | None = None
    required: bool = True


class RiskSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    severity: Literal["low", "medium", "high"] = "medium"


class GoalPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["agent.goal.plan.v1"]
    goal: str = Field(min_length=1)
    constraints: list[str]
    phases: list[GoalPlanPhase]
    work_unit_candidates: list[WorkUnitCandidate] = Field(
        max_length=MAX_GOAL_PLAN_WORK_UNITS
    )
    dependencies: list[GoalPlanDependency]
    file_scopes: list[FileScope]
    verification_requirements: list[VerificationRequirement]
    risk_summaries: list[RiskSummary]
    retry_policy: BoundedRetryPolicy

    @field_validator("constraints")
    @classmethod
    def _non_empty_constraints(cls, value: list[str]) -> list[str]:
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if not cleaned:
            raise ValueError("constraints must contain at least one non-empty entry")
        return cleaned

    @model_validator(mode="after")
    def _validate_graph(self) -> GoalPlan:
        phase_ids = {phase.id for phase in self.phases}
        if len(phase_ids) != len(self.phases):
            raise ValueError("phase ids must be unique")
        orders = [phase.order for phase in self.phases]
        if len(set(orders)) != len(orders):
            raise ValueError("phase order values must be unique")

        work_unit_ids = {unit.id for unit in self.work_unit_candidates}
        if len(work_unit_ids) != len(self.work_unit_candidates):
            raise ValueError("work unit ids must be unique")
        for unit in self.work_unit_candidates:
            if unit.phase_id not in phase_ids:
                raise ValueError(f"work unit {unit.id} references unknown phase {unit.phase_id}")

        allowed = phase_ids | work_unit_ids
        for dependency in self.dependencies:
            if dependency.from_id not in allowed:
                raise ValueError(f"dependency source missing node: {dependency.from_id}")
            if dependency.to_id not in allowed:
                raise ValueError(f"dependency target missing node: {dependency.to_id}")
            if dependency.from_id == dependency.to_id:
                raise ValueError("dependency cannot reference the same node twice")
        adjacency: dict[str, set[str]] = {node_id: set() for node_id in allowed}
        for dependency in self.dependencies:
            adjacency[dependency.from_id].add(dependency.to_id)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("dependency graph contains a cycle")
            if node_id in visited:
                return
            visiting.add(node_id)
            for target_id in adjacency[node_id]:
                visit(target_id)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in adjacency:
            visit(node_id)
        return self


def goal_planning_enabled_for_session(session: dict[str, Any]) -> bool:
    agent_id = str(session.get("agent_id") or "build")
    if agent_id != "build":
        return False
    metadata = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
    task_mode = metadata.get("task_mode") or session.get("task_mode")
    return task_mode not in {"train", "hybrid"}


def find_forbidden_goal_plan_keys(raw: Any, *, prefix: str = "") -> list[str]:
    if not isinstance(raw, dict):
        return []
    hits: list[str] = []
    for key, value in raw.items():
        key_text = str(key)
        path = f"{prefix}.{key_text}" if prefix else key_text
        if _FORBIDDEN_FIELD_PATTERN.search(key_text):
            hits.append(path)
        hits.extend(find_forbidden_goal_plan_keys(value, prefix=path))
    return hits


def parse_goal_plan(raw: Any) -> GoalPlan:
    if not isinstance(raw, dict):
        raise GoalPlanValidationError("goal plan must be an object")
    forbidden = find_forbidden_goal_plan_keys(raw)
    if forbidden:
        raise GoalPlanValidationError(f"forbidden goal plan fields: {', '.join(forbidden)}")
    try:
        return GoalPlan.model_validate(raw)
    except ValidationError as exc:
        message = exc.errors()[0]["msg"] if exc.errors() else str(exc)
        if "Extra inputs are not permitted" in message:
            raise GoalPlanValidationError("unknown goal plan fields are not permitted") from exc
        raise GoalPlanValidationError(message) from exc


def serialize_goal_plan(plan: GoalPlan) -> dict[str, Any]:
    return plan.model_dump(mode="json", by_alias=True)


def normalize_goal_plan_document(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        return serialize_goal_plan(parse_goal_plan(raw))
    except GoalPlanValidationError:
        return None


__all__ = [
    "GOAL_PLAN_SCHEMA_VERSION",
    "MAX_GOAL_PLAN_WORK_UNITS",
    "BoundedRetryPolicy",
    "GoalPlan",
    "GoalPlanValidationError",
    "find_forbidden_goal_plan_keys",
    "goal_planning_enabled_for_session",
    "normalize_goal_plan_document",
    "parse_goal_plan",
    "serialize_goal_plan",
]
