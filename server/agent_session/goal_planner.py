from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from tool_platform.models import redact_json

from agent_session.execution_plan import build_initial_execution_plan
from agent_session.goal_plan import (
    GOAL_PLAN_SCHEMA_VERSION,
    GoalPlan,
    GoalPlanValidationError,
    goal_planning_enabled_for_session,
    parse_goal_plan,
    serialize_goal_plan,
)
from agent_session.runtime_policy import AgentRuntimePolicy

if TYPE_CHECKING:
    from agent_session.services.model_call_coordinator import ModelCallCoordinatorService

logger = logging.getLogger(__name__)

GOAL_PLAN_STATUS_ATTACHED = "attached"
GOAL_PLAN_STATUS_FAILED = "failed"
GOAL_PLAN_STATUS_SKIPPED = "skipped"

GOAL_PLAN_FAILURE_SUMMARY = "未能生成结构化 Goal Plan，将继续按现有 Build 流程执行。"


@dataclass(frozen=True)
class GoalPlanningOutcome:
    ok: bool
    goal_plan: GoalPlan | None = None
    error: str | None = None
    attempts: int = 0
    skipped: bool = False


def _planner_system_prompt() -> str:
    return (
        "You are a Build Goal Planner. Return one JSON object only. "
        "Do not call tools. Do not include hidden reasoning, chain-of-thought, or scratchpad fields. "
        f"Use schema_version {json.dumps('agent.goal.plan.v1')} and include: goal, constraints, phases, "
        "work_unit_candidates, dependencies, file_scopes, verification_requirements, risk_summaries, retry_policy. "
        "Use canonical phase IDs and titles where applicable: Inspect, Plan, Implement, Verify, Review, Deliver. "
        "Include at least one WorkUnit candidate for Implement, Verify, Review, and Deliver. "
        "Do not choose an executor or subagent type; platform ownership is fixed and phases are not permissions."
    )


def _planner_user_prompt(*, user_goal: str, policy: AgentRuntimePolicy) -> str:
    return json.dumps(
        {
            "user_goal": user_goal,
            "agent_id": policy.agent_id,
            "provider": policy.provider,
            "model": policy.model,
            "output_contract": policy.output_contract,
            "constraints_hint": "Only user-visible planning fields are allowed.",
        },
        ensure_ascii=False,
    )


def _repair_user_prompt(*, prior_error: str, invalid_payload: str) -> str:
    return json.dumps(
        {
            "repair": True,
            "validation_error": prior_error,
            "invalid_payload": invalid_payload,
            "instruction": "Return a corrected JSON goal plan object with the same visible schema. No tools. No hidden reasoning.",
        },
        ensure_ascii=False,
    )


def _extract_json_object(raw: str) -> Any:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    return json.loads(cleaned)


async def run_build_goal_planner(
    coordinator: ModelCallCoordinatorService,
    *,
    session: dict[str, Any],
    policy: AgentRuntimePolicy,
    user_goal: str,
    execution_plan: dict[str, Any] | None = None,
) -> GoalPlanningOutcome:
    if not goal_planning_enabled_for_session(session):
        return GoalPlanningOutcome(ok=False, skipped=True, error="goal planning is limited to Build sessions")

    attempts = 0
    last_error = "unknown validation failure"
    last_payload = ""
    for repair in (False, True):
        attempts += 1
        try:
            raw = await coordinator.invoke_bounded_goal_planner_call(
                user_goal=user_goal,
                policy=policy,
                session=session,
                repair=repair,
                prior_error=last_error if repair else None,
                invalid_payload=last_payload if repair else None,
            )
        except Exception as exc:
            return GoalPlanningOutcome(ok=False, error=str(exc) or type(exc).__name__, attempts=attempts)
        last_payload = raw
        try:
            parsed = parse_goal_plan(_extract_json_object(raw))
        except (GoalPlanValidationError, json.JSONDecodeError, TypeError, ValueError) as exc:
            last_error = str(exc)
            if repair:
                return GoalPlanningOutcome(ok=False, error=last_error, attempts=attempts)
            continue
        if execution_plan is not None:
            execution_plan["goal_plan"] = serialize_goal_plan(parsed)
        return GoalPlanningOutcome(ok=True, goal_plan=parsed, attempts=attempts)

    return GoalPlanningOutcome(ok=False, error=last_error, attempts=attempts)


def build_goal_plan_diagnostics(*, error: str, attempts: int) -> dict[str, Any]:
    safe_error = redact_json(str(error))
    return {
        "summary": GOAL_PLAN_FAILURE_SUMMARY,
        "error": safe_error if isinstance(safe_error, str) else "goal planner failed",
        "attempts": attempts,
        "recoverable": True,
        "schema_version": GOAL_PLAN_SCHEMA_VERSION,
    }


async def attach_goal_plan_before_build_prompt(
    coordinator: ModelCallCoordinatorService,
    *,
    metadata: dict[str, Any],
    session: dict[str, Any],
    policy: AgentRuntimePolicy,
    user_goal: str,
    plan_status: str = "running",
) -> dict[str, Any]:
    execution_plan = build_initial_execution_plan(
        session=session,
        policy=policy,
        goal=user_goal,
        status=plan_status,
    )
    metadata["execution_plan"] = execution_plan
    metadata.pop("goal_plan_diagnostics", None)

    if not goal_planning_enabled_for_session(session):
        metadata["goal_plan_status"] = GOAL_PLAN_STATUS_SKIPPED
        return metadata

    session_for_planner = {**session, "metadata": metadata, "current_goal": user_goal}
    try:
        outcome = await run_build_goal_planner(
            coordinator,
            session=session_for_planner,
            policy=policy,
            user_goal=user_goal,
            execution_plan=execution_plan,
        )
    except Exception as exc:
        logger.warning("Goal planner failed before Build prompt start: %s", exc)
        metadata["goal_plan_status"] = GOAL_PLAN_STATUS_FAILED
        metadata["goal_plan_diagnostics"] = build_goal_plan_diagnostics(error=str(exc), attempts=0)
        execution_plan.pop("goal_plan", None)
        return metadata

    if outcome.ok and outcome.goal_plan is not None:
        metadata["goal_plan_status"] = GOAL_PLAN_STATUS_ATTACHED
        return metadata

    metadata["goal_plan_status"] = GOAL_PLAN_STATUS_FAILED
    metadata["goal_plan_diagnostics"] = build_goal_plan_diagnostics(
        error=str(outcome.error or GOAL_PLAN_FAILURE_SUMMARY),
        attempts=outcome.attempts,
    )
    execution_plan.pop("goal_plan", None)
    return metadata


def attach_goal_plan_before_build_prompt_sync(
    coordinator: ModelCallCoordinatorService,
    *,
    metadata: dict[str, Any],
    session: dict[str, Any],
    policy: AgentRuntimePolicy,
    user_goal: str,
    plan_status: str = "running",
) -> dict[str, Any]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            attach_goal_plan_before_build_prompt(
                coordinator,
                metadata=metadata,
                session=session,
                policy=policy,
                user_goal=user_goal,
                plan_status=plan_status,
            )
        )
    raise RuntimeError("attach_goal_plan_before_build_prompt_sync cannot run inside a running event loop")


__all__ = [
    "GOAL_PLAN_FAILURE_SUMMARY",
    "GOAL_PLAN_STATUS_ATTACHED",
    "GOAL_PLAN_STATUS_FAILED",
    "GOAL_PLAN_STATUS_SKIPPED",
    "GoalPlanningOutcome",
    "attach_goal_plan_before_build_prompt",
    "attach_goal_plan_before_build_prompt_sync",
    "build_goal_plan_diagnostics",
    "run_build_goal_planner",
]
