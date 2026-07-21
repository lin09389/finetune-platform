from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_session.execution_context import AgentDefinition
from agent_session.execution_plan import (
    PLAN_SCHEMA_VERSION,
    build_initial_execution_plan,
    normalize_execution_plan,
    validate_execution_plan,
)
from agent_session.goal_plan import (
    GOAL_PLAN_SCHEMA_VERSION,
    GoalPlanValidationError,
    goal_planning_enabled_for_session,
    parse_goal_plan,
    serialize_goal_plan,
)
from agent_session.goal_planner import run_build_goal_planner
from agent_session.runtime_policy import build_agent_runtime_policy
from agent_session.services.model_call_coordinator import ModelCallCoordinatorService


def _policy(*, agent_id: str = "build"):
    agent = AgentDefinition(
        id=agent_id,
        name=agent_id.title(),
        mode="all",
        max_iterations=3,
        tools=["read_file", "edit_file", "execute"],
        output_requirements="返回 JSON 摘要。",
    )
    return build_agent_runtime_policy(
        agent=agent,
        agent_id=agent_id,
        project_path=".",
        metadata={},
        provider="openai",
        model="gpt-4.1",
        runtime_kind="agent_session",
        thread_id="agent_session:s1:deepagents",
        checkpointer=True,
    )


def _valid_goal_plan_payload(*, goal: str = "实现 Goal Plan") -> dict[str, Any]:
    return {
        "schema_version": GOAL_PLAN_SCHEMA_VERSION,
        "goal": goal,
        "constraints": ["仅修改 server/agent_session/", "保持 Build-only"],
        "phases": [
            {"id": "inspect", "title": "Inspect", "summary": "理解现有结构", "order": 0},
            {"id": "implement", "title": "Implement", "summary": "实现类型化计划", "order": 1},
        ],
        "work_unit_candidates": [
            {"id": "wu_inspect", "phase_id": "inspect", "title": "阅读 execution_plan", "summary": "确认持久化边界"},
            {"id": "wu_impl", "phase_id": "implement", "title": "编写 schema", "summary": "严格 Pydantic 模型"},
        ],
        "dependencies": [{"from": "wu_inspect", "to": "wu_impl", "kind": "depends_on"}],
        "file_scopes": [{"path": "server/agent_session/", "mode": "read_write"}],
        "verification_requirements": [
            {"id": "tests", "description": "运行 goal plan 测试", "command": "pytest server/tests/test_agent_goal_plan.py -q", "required": True}
        ],
        "risk_summaries": [{"id": "scope", "summary": "可能触及 execution_plan 归一化", "severity": "medium"}],
        "retry_policy": {"max_replan_attempts": 1, "max_phase_retries": 2},
    }


def test_goal_plan_schema_rejects_unknown_fields():
    payload = _valid_goal_plan_payload()
    payload["hidden_extra"] = "nope"

    with pytest.raises(GoalPlanValidationError, match="unknown|extra|forbidden"):
        parse_goal_plan(payload)


def test_goal_plan_schema_rejects_hidden_reasoning_fields():
    payload = _valid_goal_plan_payload()
    payload["chain_of_thought"] = "must not persist"

    with pytest.raises(GoalPlanValidationError, match="forbidden|chain_of_thought|reasoning"):
        parse_goal_plan(payload)


def test_goal_plan_schema_rejects_invalid_dependencies():
    payload = _valid_goal_plan_payload()
    payload["dependencies"] = [{"from": "missing", "to": "wu_impl", "kind": "depends_on"}]

    with pytest.raises(GoalPlanValidationError, match="dependency"):
        parse_goal_plan(payload)


def test_goal_plan_roundtrip_serialization():
    plan = parse_goal_plan(_valid_goal_plan_payload())
    document = serialize_goal_plan(plan)

    assert document["schema_version"] == GOAL_PLAN_SCHEMA_VERSION
    assert document["goal"] == "实现 Goal Plan"
    assert parse_goal_plan(document).goal == plan.goal


def test_build_only_guard_for_goal_planning():
    assert goal_planning_enabled_for_session({"agent_id": "build", "metadata": {"task_mode": "build"}}) is True
    assert goal_planning_enabled_for_session({"agent_id": "build", "metadata": {}}) is True
    assert goal_planning_enabled_for_session({"agent_id": "build", "metadata": {"task_mode": "train"}}) is False
    assert goal_planning_enabled_for_session({"agent_id": "build", "metadata": {"task_mode": "hybrid"}}) is False
    assert goal_planning_enabled_for_session({"agent_id": "explore", "metadata": {"task_mode": "build"}}) is False


@pytest.mark.asyncio
async def test_goal_planner_success_on_first_attempt():
    calls: list[list[dict[str, str]]] = []

    async def model_call(messages: list[dict[str, str]]) -> str:
        calls.append(messages)
        return json.dumps(_valid_goal_plan_payload(), ensure_ascii=False)

    service = MagicMock()
    service.model_call = model_call
    service.deepagents_runner = MagicMock()
    coordinator = ModelCallCoordinatorService(service)

    outcome = await run_build_goal_planner(
        coordinator,
        session={"id": "s1", "agent_id": "build", "metadata": {"task_mode": "build"}},
        policy=_policy(),
        user_goal="实现 Goal Plan",
    )

    assert outcome.ok is True
    assert outcome.goal_plan is not None
    assert outcome.attempts == 1
    assert outcome.error is None
    assert len(calls) == 1
    service.deepagents_runner.run.assert_not_called()


@pytest.mark.asyncio
async def test_goal_planner_repairs_after_first_invalid_payload():
    attempts = {"count": 0}

    async def model_call(messages: list[dict[str, str]]) -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return json.dumps({"schema_version": GOAL_PLAN_SCHEMA_VERSION, "goal": "x"})
        return json.dumps(_valid_goal_plan_payload(), ensure_ascii=False)

    service = MagicMock()
    service.model_call = model_call
    service.deepagents_runner = MagicMock()
    coordinator = ModelCallCoordinatorService(service)

    outcome = await run_build_goal_planner(
        coordinator,
        session={"id": "s1", "agent_id": "build", "metadata": {}},
        policy=_policy(),
        user_goal="实现 Goal Plan",
    )

    assert outcome.ok is True
    assert outcome.attempts == 2
    assert attempts["count"] == 2


@pytest.mark.asyncio
async def test_goal_planner_fails_safely_after_two_invalid_payloads():
    async def model_call(messages: list[dict[str, str]]) -> str:
        return json.dumps({"schema_version": GOAL_PLAN_SCHEMA_VERSION, "goal": "incomplete"})

    service = MagicMock()
    service.model_call = model_call
    service.deepagents_runner = MagicMock()
    coordinator = ModelCallCoordinatorService(service)

    baseline = build_initial_execution_plan(
        session={"id": "s1", "agent_id": "build", "status": "running"},
        policy=_policy(),
        goal="baseline",
        status="running",
    )

    outcome = await run_build_goal_planner(
        coordinator,
        session={"id": "s1", "agent_id": "build", "metadata": {}},
        policy=_policy(),
        user_goal="实现 Goal Plan",
        execution_plan=baseline,
    )

    assert outcome.ok is False
    assert outcome.goal_plan is None
    assert outcome.attempts == 2
    assert outcome.error
    assert "goal_plan" not in baseline
    service.deepagents_runner.run.assert_not_called()


@pytest.mark.asyncio
async def test_goal_planner_skips_train_hybrid_sessions():
    service = MagicMock()
    service.model_call = AsyncMock()
    coordinator = ModelCallCoordinatorService(service)

    outcome = await run_build_goal_planner(
        coordinator,
        session={"id": "s1", "agent_id": "build", "metadata": {"task_mode": "train"}},
        policy=_policy(),
        user_goal="训练模型",
    )

    assert outcome.ok is False
    assert outcome.skipped is True
    service.model_call.assert_not_called()


@pytest.mark.asyncio
async def test_goal_planner_timeout_fails_without_entering_deepagents(monkeypatch: pytest.MonkeyPatch):
    import agent_session.services.model_call_coordinator as coordinator_module

    async def model_call(_messages: list[dict[str, str]]) -> str:
        await asyncio.Event().wait()
        return ""

    monkeypatch.setattr(coordinator_module, "GOAL_PLANNER_CALL_TIMEOUT_SECONDS", 0.01)
    service = MagicMock()
    service.model_call = model_call
    service.deepagents_runner = MagicMock()
    coordinator = ModelCallCoordinatorService(service)

    outcome = await run_build_goal_planner(
        coordinator,
        session={"id": "s1", "agent_id": "build", "metadata": {}},
        policy=_policy(),
        user_goal="实现 Goal Plan",
    )

    assert outcome.ok is False
    assert outcome.attempts == 1
    service.deepagents_runner.run.assert_not_called()


def test_goal_plan_diagnostics_redact_provider_secrets():
    from agent_session.goal_planner import build_goal_plan_diagnostics

    diagnostics = build_goal_plan_diagnostics(
        error="provider rejected Bearer secret-value at https://example.test/?api_key=private",
        attempts=1,
    )

    assert "secret-value" not in diagnostics["error"]
    assert "private" not in diagnostics["error"]
    assert "[REDACTED]" in diagnostics["error"]


def test_execution_plan_persists_and_normalizes_goal_plan():
    policy = _policy()
    goal_document = serialize_goal_plan(parse_goal_plan(_valid_goal_plan_payload()))
    plan = build_initial_execution_plan(
        session={"id": "s1", "agent_id": "build", "status": "running"},
        policy=policy,
        goal="实现 Goal Plan",
        status="running",
        goal_plan=goal_document,
    )

    assert plan["goal_plan"]["schema_version"] == GOAL_PLAN_SCHEMA_VERSION
    warnings = validate_execution_plan(plan)
    assert not warnings

    restored = normalize_execution_plan(
        plan,
        session={"id": "s1", "agent_id": "build"},
        policy=policy,
        goal="实现 Goal Plan",
    )
    assert restored["schema_version"] == PLAN_SCHEMA_VERSION
    assert restored["goal_plan"]["goal"] == "实现 Goal Plan"


def test_execution_plan_without_goal_plan_stays_compatible():
    policy = _policy()
    plan = build_initial_execution_plan(
        session={"id": "s1", "agent_id": "build", "status": "running"},
        policy=policy,
        goal="旧行为",
        status="running",
    )

    restored = normalize_execution_plan(plan, session={"id": "s1", "agent_id": "build"}, policy=policy)
    assert "goal_plan" not in restored or restored.get("goal_plan") is None


def test_build_prompt_start_persists_goal_plan_on_success(tmp_path):
    from pathlib import Path

    from agent_session.models import AgentPromptRequest, AgentSessionCreate
    from agent_session.repository import AgentSessionRepository
    from agent_session.service import AgentSessionService
    from fastapi import BackgroundTasks

    async def model_call(_messages: list[dict[str, str]]) -> str:
        return json.dumps(_valid_goal_plan_payload(goal="ship feature"), ensure_ascii=False)

    service = AgentSessionService(
        AgentSessionRepository(str(tmp_path / "agents.db")),
        model_call=model_call,
    )
    session = service.create_session(
        AgentSessionCreate(title="build", project_path=str(Path.cwd()), task_mode="build"),
    )

    response = service.start_prompt_background(
        session.id,
        AgentPromptRequest(content="ship feature"),
        BackgroundTasks(),
    )

    assert response.status == "running"
    assert response.metadata["goal_plan_status"] == "attached"
    assert response.metadata["execution_plan"]["goal_plan"]["goal"] == "ship feature"
    events = [event["event_type"] for event in service.repository.list_events(session.id)]
    assert "goal_plan_attached" in events


def test_build_prompt_start_records_diagnostics_and_continues_on_failure(tmp_path):
    from pathlib import Path

    from agent_session.models import AgentPromptRequest, AgentSessionCreate
    from agent_session.repository import AgentSessionRepository
    from agent_session.service import AgentSessionService
    from fastapi import BackgroundTasks

    async def model_call(_messages: list[dict[str, str]]) -> str:
        return json.dumps({"schema_version": GOAL_PLAN_SCHEMA_VERSION, "goal": "incomplete"})

    service = AgentSessionService(
        AgentSessionRepository(str(tmp_path / "agents.db")),
        model_call=model_call,
    )
    session = service.create_session(AgentSessionCreate(title="build", project_path=str(Path.cwd())))

    response = service.start_prompt_background(
        session.id,
        AgentPromptRequest(content="still run build"),
        BackgroundTasks(),
    )

    assert response.status == "running"
    assert response.metadata["goal_plan_status"] == "failed"
    assert "goal_plan" not in response.metadata["execution_plan"]
    assert response.metadata["goal_plan_diagnostics"]["recoverable"] is True
    events = [event["event_type"] for event in service.repository.list_events(session.id)]
    assert "goal_plan_failed" in events
    assert "prompt_queued" in events


def test_train_prompt_start_skips_goal_planner(tmp_path):
    from pathlib import Path

    from agent_session.models import AgentPromptRequest, AgentSessionCreate
    from agent_session.repository import AgentSessionRepository
    from agent_session.service import AgentSessionService
    from fastapi import BackgroundTasks

    calls = {"count": 0}

    async def model_call(_messages: list[dict[str, str]]) -> str:
        calls["count"] += 1
        return json.dumps(_valid_goal_plan_payload(), ensure_ascii=False)

    service = AgentSessionService(
        AgentSessionRepository(str(tmp_path / "agents.db")),
        model_call=model_call,
    )
    session = service.create_session(
        AgentSessionCreate(title="train", project_path=str(Path.cwd()), task_mode="train"),
    )

    response = service.start_prompt_background(
        session.id,
        AgentPromptRequest(content="start training"),
        BackgroundTasks(),
    )

    assert response.status == "running"
    assert response.metadata["goal_plan_status"] == "skipped"
    assert "goal_plan" not in response.metadata["execution_plan"]
    assert calls["count"] == 0
