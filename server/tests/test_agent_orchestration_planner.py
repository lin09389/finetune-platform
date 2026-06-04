from __future__ import annotations

from agent_session.models import (
    AgentSessionResponse,
    AgentWorkspaceArtifact,
    AgentWorkspaceChangedFile,
)
from agent_session.orchestration_planner import AgentOrchestrationPlanner


def _session(status: str = "running") -> AgentSessionResponse:
    return AgentSessionResponse(
        id="session_1",
        agent_id="build",
        status=status,
        title="build",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        parts=[],
    )


def _artifact(artifact_type: str, artifact_id: str, **kwargs) -> AgentWorkspaceArtifact:
    return AgentWorkspaceArtifact(
        id=artifact_id,
        artifact_type=artifact_type,
        title=kwargs.get("title", artifact_type),
        summary=kwargs.get("summary", ""),
        payload=kwargs.get("payload", {}),
        source_task_id=kwargs.get("source_task_id"),
    )


def _plan(**kwargs):
    planner = AgentOrchestrationPlanner()
    return planner.plan(
        session=kwargs.get("session") or _session(),
        artifacts=kwargs.get("artifacts") or [],
        changed_files=kwargs.get("changed_files") or [],
        tasks=kwargs.get("tasks") or [],
        pending_permission=kwargs.get("pending_permission"),
    )


def test_pending_permission_generates_high_priority_resolution():
    actions = _plan(pending_permission={"part_id": "perm_1", "actions": []})

    action = actions[0]
    assert action.action_type == "resolve_permission"
    assert action.priority == "high"
    assert action.payload["permission_part_id"] == "perm_1"


def test_child_pending_permission_generates_resolution_action():
    actions = _plan(
        tasks=[
            {
                "task_id": "task_waiting",
                "child_session_id": "child_1",
                "agent_name": "explore",
                "status": "running",
                "has_pending_permission": True,
                "pending_permission_part_id": "perm_child",
            }
        ]
    )

    action = actions[0]
    assert action.action_type == "resolve_permission"
    assert action.source_task_id == "task_waiting"
    assert action.payload["permission_part_id"] == "perm_child"


def test_conditional_or_failed_risks_generate_review_action():
    actions = _plan(
        artifacts=[
            _artifact("risks", "risks_conditional", summary="缺少测试", payload={"verdict": "conditional"}),
            _artifact("risks", "risks_fail", summary="阻塞风险", payload={"verdict": "fail"}),
        ]
    )

    review_actions = [action for action in actions if action.action_type == "review_risks"]
    assert {action.priority for action in review_actions} == {"high", "medium"}
    assert {action.source_artifact_id for action in review_actions} == {"risks_conditional", "risks_fail"}


def test_file_change_without_test_result_generates_run_tests_suggestion():
    actions = _plan(artifacts=[_artifact("file_change", "file_change_1")])

    assert any(action.action_type == "run_tests" for action in actions)


def test_file_change_with_test_result_does_not_generate_run_tests_suggestion():
    actions = _plan(
        artifacts=[
            _artifact("file_change", "file_change_1"),
            _artifact("test_result", "test_1", payload={"passed": True}),
        ]
    )

    assert all(action.action_type != "run_tests" for action in actions)


def test_findings_without_review_task_generates_start_review():
    actions = _plan(
        artifacts=[_artifact("findings", "findings_1", summary="入口在 app.py", source_task_id="task_explore")],
        tasks=[{"task_id": "task_explore", "agent_name": "explore", "status": "completed"}],
    )

    action = next(action for action in actions if action.action_type == "start_review")
    assert action.payload["subagent_type"] == "review"
    assert action.source_artifact_id == "findings_1"


def test_existing_review_task_suppresses_start_review():
    actions = _plan(
        artifacts=[_artifact("findings", "findings_1", summary="入口在 app.py")],
        tasks=[{"task_id": "task_review", "agent_name": "review", "status": "running"}],
    )

    assert all(action.action_type != "start_review" for action in actions)


def test_failed_async_task_generates_restart_failed_task():
    actions = _plan(
        tasks=[
            {
                "task_id": "task_failed",
                "agent_name": "review",
                "status": "failed",
                "error": "boom",
                "child_session_id": "child_1",
            }
        ]
    )

    action = next(action for action in actions if action.action_type == "restart_failed_task")
    assert action.source_task_id == "task_failed"
    assert action.payload["child_session_id"] == "child_1"


def test_changed_files_generate_recent_inspect_file_actions_and_clean_completed_is_quiet():
    quiet = _plan(session=_session("completed"))
    assert quiet == []

    actions = _plan(
        changed_files=[
            AgentWorkspaceChangedFile(path="a.py", summary="a"),
            AgentWorkspaceChangedFile(path="b.py", summary="b"),
            AgentWorkspaceChangedFile(path="c.py", summary="c"),
            AgentWorkspaceChangedFile(path="d.py", summary="d"),
        ]
    )

    file_actions = [action for action in actions if action.action_type == "inspect_file"]
    assert [action.payload["path"] for action in file_actions] == ["b.py", "c.py", "d.py"]
