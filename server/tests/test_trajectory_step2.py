"""Trajectory middleware Step 2 + B3 preconditions."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_session.repository import AgentSessionRepository
from agent_session.session_progress import apply_recovery_event, reset_tool_metrics
from agent_session.trajectory import TrajectoryGuardMiddleware, TrajectoryStateStore
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

POLICY = {
    "enabled": True,
    "require_read_before_write": True,
    "require_context_before_create": True,
    "validate_after_write": True,
    "rollback_on_validation_failure": True,
    "require_verification_after_write": True,
    "max_auto_corrections": 2,
}


def _runtime_request(name: str, args: dict[str, Any], call_id: str = "call-1") -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": args, "id": call_id, "type": "tool_call"},
        tool=None,
        state={"messages": []},
        runtime=None,  # type: ignore[arg-type]
    )


async def _ok_handler(request: ToolCallRequest) -> ToolMessage:
    return ToolMessage(content="ok", tool_call_id=str(request.tool_call["id"]))


def _seed_failed_execute(repository: AgentSessionRepository, session_id: str, command: str) -> None:
    meta = dict(repository.get_session(session_id)["metadata"] or {})
    meta = apply_recovery_event(
        meta,
        {
            "event_type": "tool_call_failed",
            "payload": {
                "tool": "execute",
                "error": "boom",
                "part": {"payload": {"input": {"command": command}}},
            },
        },
    )
    repository.update_session(session_id, metadata=meta)


def test_trajectory_blocks_blind_execute_retry(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    session = repository.create_session(
        {"agent_id": "build", "title": "s2", "project_path": str(workspace), "metadata": reset_tool_metrics({})}
    )
    middleware = TrajectoryGuardMiddleware(
        repository=repository,
        notify_event=lambda *_a, **_k: None,
        session_id=session["id"],
        project_path=str(workspace),
        policy=POLICY,
    )
    TrajectoryStateStore(repository, lambda *_a, **_k: None, session["id"]).begin_run()
    _seed_failed_execute(repository, session["id"], "python app.py")

    import asyncio

    result = asyncio.get_event_loop().run_until_complete(
        middleware.awrap_tool_call(_runtime_request("execute", {"command": "python app.py"}), _ok_handler)
    )
    assert isinstance(result, ToolMessage)
    assert "阻止" in str(result.content)


def test_trajectory_blocks_different_execute_without_observation(tmp_path: Path):
    """B3: thrash with a *different* command is also blocked until observe."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    session = repository.create_session(
        {
            "agent_id": "build",
            "title": "b3",
            "project_path": str(workspace),
            "metadata": reset_tool_metrics({}),
        }
    )
    middleware = TrajectoryGuardMiddleware(
        repository=repository,
        notify_event=lambda *_a, **_k: None,
        session_id=session["id"],
        project_path=str(workspace),
        policy=POLICY,
    )
    TrajectoryStateStore(repository, lambda *_a, **_k: None, session["id"]).begin_run()
    _seed_failed_execute(repository, session["id"], "python cli.py -1")

    import asyncio

    blocked = asyncio.get_event_loop().run_until_complete(
        middleware.awrap_tool_call(
            _runtime_request("execute", {"command": "python cli.py 1"}, call_id="call-diff"),
            _ok_handler,
        )
    )
    assert isinstance(blocked, ToolMessage)
    text = str(blocked.content)
    assert "阻止" in text
    assert "未观察" in text or "观察" in text

    meta = dict(repository.get_session(session["id"])["metadata"] or {})
    assert int((meta.get("recovery_state") or {}).get("blind_retry_blocks") or 0) >= 1

    # After read_file completes, execute is allowed again.
    meta = apply_recovery_event(
        meta,
        {"event_type": "tool_call_completed", "payload": {"tool": "read_file"}},
    )
    repository.update_session(session["id"], metadata=meta)

    allowed = asyncio.get_event_loop().run_until_complete(
        middleware.awrap_tool_call(
            _runtime_request("execute", {"command": "python cli.py 1"}, call_id="call-ok"),
            _ok_handler,
        )
    )
    assert isinstance(allowed, ToolMessage)
    assert allowed.content == "ok"
