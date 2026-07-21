from __future__ import annotations

from server.agent_session.execution_context import AgentDefinition
from server.agent_session.execution_plan import (
    PLAN_SCHEMA_VERSION,
    build_initial_execution_plan,
    normalize_execution_plan,
    repair_execution_plan,
    sync_execution_plan_status,
    todos_from_execution_plan,
    validate_execution_plan,
)
from server.agent_session.runtime_policy import build_agent_runtime_policy


def _policy():
    agent = AgentDefinition(
        id="build",
        name="Build",
        mode="all",
        max_iterations=3,
        tools=["read_file", "edit_file", "execute", "start_subagent", "update_subagent", "cancel_subagent"],
        output_requirements="返回 JSON 摘要。",
    )
    return build_agent_runtime_policy(
        agent=agent,
        agent_id="build",
        project_path=".",
        metadata={},
        provider="openai",
        model="gpt-4.1",
        runtime_kind="agent_session",
        thread_id="agent_session:s1:deepagents",
        checkpointer=True,
    )


def test_build_initial_execution_plan_contains_runtime_contract_nodes():
    plan = build_initial_execution_plan(
        session={"id": "s1", "agent_id": "build", "status": "running"},
        policy=_policy(),
        goal="实现第一阶段",
        status="running",
    )

    assert plan["schema_version"] == PLAN_SCHEMA_VERSION
    assert plan["plan_id"] == "plan_s1"
    assert plan["session_id"] == "s1"
    assert plan["goal"] == "实现第一阶段"
    assert plan["status"] == "running"
    assert plan["current_node_id"] == "execute_primary_agent"
    assert [node["id"] for node in plan["nodes"]] == ["understand_task", "execute_primary_agent", "summarize_result"]
    assert {"from": "understand_task", "to": "execute_primary_agent", "type": "depends_on"} in plan["edges"]
    assert plan["nodes"][1]["output_contract"]["requirements"] == "返回 JSON 摘要。"


def test_normalize_ignores_legacy_task_plan_and_builds_fresh_dag():
    legacy = {
        "task_id": "task_1",
        "goal": "旧计划",
        "status": "running",
        "stages": [
            {
                "id": "stage_1",
                "title": "准备",
                "status": "completed",
                "nodes": [{"id": "read", "title": "读取文件", "status": "running"}],
            }
        ],
    }

    plan = normalize_execution_plan(legacy, session={"id": "s1", "agent_id": "build"}, policy=_policy())

    assert plan["schema_version"] == PLAN_SCHEMA_VERSION
    assert [node["id"] for node in plan["nodes"]] == ["understand_task", "execute_primary_agent", "summarize_result"]
    assert plan["current_node_id"] == "understand_task"


def test_sync_execution_plan_status_updates_nodes_and_error():
    metadata = {
        "execution_plan": build_initial_execution_plan(
            session={"id": "s1", "agent_id": "build", "status": "running"},
            policy=_policy(),
            goal="运行",
            status="running",
        )
    }

    sync_execution_plan_status(metadata, "failed", error="boom")

    plan = metadata["execution_plan"]
    assert plan["status"] == "failed"
    failed_nodes = [node for node in plan["nodes"] if node["status"] == "failed"]
    assert failed_nodes
    assert failed_nodes[0]["error"] == "boom"


def test_sync_execution_plan_status_resumes_current_blocked_node():
    metadata = {
        "execution_plan": build_initial_execution_plan(
            session={"id": "s1", "agent_id": "build", "status": "running"},
            policy=_policy(),
            goal="运行",
            status="running",
        )
    }

    sync_execution_plan_status(metadata, "waiting_approval")
    sync_execution_plan_status(metadata, "running")

    plan = metadata["execution_plan"]
    assert plan["current_node_id"] == "execute_primary_agent"
    statuses = {node["id"]: node["status"] for node in plan["nodes"]}
    assert statuses["execute_primary_agent"] == "running"
    assert statuses["summarize_result"] == "pending"


def test_todos_from_execution_plan_projects_nodes_for_workspace():
    plan = build_initial_execution_plan(
        session={"id": "s1", "agent_id": "build", "status": "running"},
        policy=_policy(),
        goal="运行",
        status="running",
    )

    todos = todos_from_execution_plan(plan)

    assert [todo["source"] for todo in todos] == ["execution_plan", "execution_plan", "execution_plan"]
    assert todos[1]["status"] == "in_progress"


def test_repair_execution_plan_fixes_bad_invariants():
    plan = build_initial_execution_plan(
        session={"id": "s1", "agent_id": "build", "status": "running"},
        policy=_policy(),
        goal="运行",
        status="running",
    )
    plan["current_node_id"] = "missing"
    plan["nodes"].append({**plan["nodes"][1], "status": "bogus", "recovery_action": "auto", "recovery_attempts": "bad"})
    plan["edges"].append({"from": "missing", "to": "also_missing", "type": "depends_on"})

    warnings = validate_execution_plan(plan)
    repaired, repair_warnings = repair_execution_plan(plan)

    assert warnings
    assert repair_warnings
    assert repaired["current_node_id"] in {node["id"] for node in repaired["nodes"]}
    assert len({node["id"] for node in repaired["nodes"]}) == len(repaired["nodes"])
    assert all(edge["from"] != "missing" for edge in repaired["edges"])
    repaired_duplicate = next(node for node in repaired["nodes"] if node["id"].startswith("execute_primary_agent_"))
    assert repaired_duplicate["status"] == "pending"
    assert repaired_duplicate["recovery_action"] is None
    assert repaired_duplicate["recovery_attempts"] == 0


def test_validate_execution_plan_warns_on_invalid_goal_plan():
    plan = build_initial_execution_plan(
        session={"id": "s1", "agent_id": "build", "status": "running"},
        policy=_policy(),
        goal="运行",
        status="running",
    )
    plan["goal_plan"] = {"schema_version": "agent.goal.plan.v1", "goal": "incomplete"}

    warnings = validate_execution_plan(plan)

    assert any("goal_plan invalid" in item for item in warnings)
