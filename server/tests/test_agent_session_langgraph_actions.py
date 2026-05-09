from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path

from agent_session.models import AgentPromptRequest, AgentSessionCreate
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService
from core.config import settings


def test_agent_session_langgraph_patch_requires_execute_then_resumes(tmp_path: Path, monkeypatch):
    workspace = Path.cwd()
    run_dir = workspace / "tmp" / f"agent-session-langgraph-action-{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    target_a = run_dir / "feature_a.py"
    target_b = run_dir / "feature_b.py"
    target_a.write_text("VALUE_A = 1\n", encoding="utf-8")
    target_b.write_text("VALUE_B = 1\n", encoding="utf-8")
    monkeypatch.setattr(settings, "agent_session_langgraph_enabled", True)
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_session_langgraph_action.db")))
    session = service.create_session(
        AgentSessionCreate(
            title="langgraph action",
            project_path=str(workspace),
            autonomy_mode="confirm_all",
        )
    )
    rel_a = target_a.relative_to(workspace).as_posix()
    rel_b = target_b.relative_to(workspace).as_posix()
    responses = iter(
        [
            json.dumps(
                [
                    {"tool": "collect_context", "arguments": {"read": [rel_a, rel_b]}},
                    {
                        "tool": "patch",
                        "arguments": {
                            "title": "更新 feature",
                            "payload": {
                                "files": [
                                    {"path": rel_a, "content": "VALUE_A = 2\n"},
                                    {"path": rel_b, "content": "VALUE_B = 2\n"},
                                ]
                            },
                        },
                    },
                ],
                ensure_ascii=False,
            ),
            json.dumps({"tool": "finalize", "arguments": {"summary": "补丁已执行并完成。"}}, ensure_ascii=False),
        ]
    )

    async def model_call(_messages):
        return next(responses)

    service.model_call = model_call
    try:
        first = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="修改 feature.py 并总结")))
        diff = next(part for part in first.parts if part.type == "diff")

        assert first.status == "waiting_approval"
        assert diff.status == "pending"
        assert target_a.read_text(encoding="utf-8") == "VALUE_A = 1\n"
        assert target_b.read_text(encoding="utf-8") == "VALUE_B = 1\n"

        rebuild_service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_session_langgraph_action.db")))
        rebuild_service.model_call = model_call

        approved = asyncio.run(rebuild_service.approve_action_async(diff.id, True))
        diff_after_approve = next(part for part in approved.parts if part.id == diff.id)
        assert approved.status == "waiting_approval"
        assert diff_after_approve.status == "approved"
        assert target_a.read_text(encoding="utf-8") == "VALUE_A = 1\n"
        assert target_b.read_text(encoding="utf-8") == "VALUE_B = 1\n"

        execute_service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agent_session_langgraph_action.db")))
        execute_service.model_call = model_call
        executed = asyncio.run(execute_service.execute_action_async(diff.id))
        final_diff = next(part for part in executed.parts if part.id == diff.id)
        assert executed.status == "completed"
        assert final_diff.status == "executed"
        assert executed.parts[-1].type == "summary"
        assert executed.parts[-1].content == "补丁已执行并完成。"
        assert target_a.read_text(encoding="utf-8") == "VALUE_A = 2\n"
        assert target_b.read_text(encoding="utf-8") == "VALUE_B = 2\n"
        assert executed.metadata["last_resume_decision"]["decision"] == "executed"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
