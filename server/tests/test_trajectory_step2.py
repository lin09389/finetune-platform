"""Trajectory middleware Step 2 preconditions."""
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

    # Seed failed execute recovery latch.
    meta = dict(repository.get_session(session["id"])["metadata"] or {})
    meta = apply_recovery_event(
        meta,
        {
            "event_type": "tool_call_failed",
            "payload": {
                "tool": "execute",
                "error": "boom",
                "part": {"payload": {"input": {"command": "python app.py"}}},
            },
        },
    )
    repository.update_session(session["id"], metadata=meta)

    import asyncio

    result = asyncio.get_event_loop().run_until_complete(
        middleware.awrap_tool_call(_runtime_request("execute", {"command": "python app.py"}), _ok_handler)
    )
    assert isinstance(result, ToolMessage)
    assert "盲目重试" in str(result.content) or "blind" in str(result.content).lower() or "阻止" in str(result.content)
