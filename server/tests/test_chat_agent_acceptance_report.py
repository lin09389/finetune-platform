from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from agent_runtime.repository import WorkflowRuntimeRepository
from agent_runtime.service import AgentRuntimeService
from api.chat_agent import get_chat_agent_service
from chat_agent.acceptance import AcceptanceReportGenerator
from chat_agent.service import ChatAgentService
from digital_team.models import AgentOutput
from main import app


class AcceptanceRunner:
    async def execute(self, agent_id, context, step_input):
        return AgentOutput(
            summary="已完成验收测试任务",
            tasks=[],
            risks=[],
            artifacts=[
                {
                    "type": "patch",
                    "title": "写入验收 smoke 文件",
                    "payload": {"files": [{"path": "tmp/chat-agent-acceptance.txt", "content": "accepted"}]},
                }
            ],
            next_action="查看验收报告",
            requires_approval=False,
        )


def make_client(tmp_path: Path, model_call=None):
    repository = WorkflowRuntimeRepository(str(tmp_path / "chat_agent_acceptance.db"))
    runtime = AgentRuntimeService(repository=repository, runner=AcceptanceRunner())
    generator = AcceptanceReportGenerator(model_call=model_call)
    service = ChatAgentService(runtime, acceptance_generator=generator)
    app.dependency_overrides[get_chat_agent_service] = lambda: service
    return TestClient(app), repository


def clear_overrides():
    app.dependency_overrides.clear()


def test_model_acceptance_report_is_generated_and_restored_once(tmp_path):
    calls = {"count": 0}

    async def model_call(messages, provider, model):
        calls["count"] += 1
        return json.dumps(
            {
                "result": "passed",
                "summary": "模型判断任务可用。",
                "completed_items": ["写入 smoke 文件"],
                "changed_files": ["tmp/chat-agent-acceptance.txt"],
                "commands_run": [],
                "verification_result": "未运行验证命令",
                "blocking_reason": "",
                "next_action": "查看文件内容。",
            },
            ensure_ascii=False,
        )

    target = Path.cwd() / "tmp" / "chat-agent-acceptance.txt"
    if target.exists():
        target.unlink()
    client, _repository = make_client(tmp_path, model_call=model_call)
    run = client.post(
        "/chat-agent/runs",
        json={"content": "新增验收 smoke 文件", "project_path": str(Path.cwd()), "force_agent": True},
    ).json()

    started = client.post(f"/chat-agent/runs/{run['id']}/run").json()
    restored = client.get(f"/chat-agent/runs/{run['id']}").json()
    restored_again = client.get(f"/chat-agent/runs/{run['id']}").json()
    clear_overrides()

    try:
        assert started["acceptance_report"]["result"] == "passed"
        assert started["acceptance_report"]["summary"] == "模型判断任务可用。"
        assert started["acceptance_report_source"] == "model"
        assert restored["acceptance_report"]["summary"] == "模型判断任务可用。"
        assert restored_again["acceptance_report_source"] == "model"
        assert calls["count"] == 1
    finally:
        if target.exists():
            target.unlink()


def test_invalid_model_report_falls_back_to_readable_report(tmp_path):
    async def bad_model_call(messages, provider, model):
        return "这不是 JSON"

    target = Path.cwd() / "tmp" / "chat-agent-acceptance.txt"
    if target.exists():
        target.unlink()
    client, _repository = make_client(tmp_path, model_call=bad_model_call)
    run = client.post(
        "/chat-agent/runs",
        json={"content": "新增验收 smoke 文件", "project_path": str(Path.cwd()), "force_agent": True},
    ).json()

    started = client.post(f"/chat-agent/runs/{run['id']}/run").json()
    clear_overrides()

    try:
        assert started["acceptance_report_source"] == "fallback"
        assert started["acceptance_report"]["summary"]
        assert started["acceptance_report"]["changed_files"] == ["tmp/chat-agent-acceptance.txt"]
    finally:
        if target.exists():
            target.unlink()


def test_manual_review_generates_blocked_report_on_get(tmp_path):
    client, repository = make_client(tmp_path)
    run = client.post(
        "/chat-agent/runs",
        json={"content": "触发人工确认", "project_path": str(Path.cwd()), "force_agent": True},
    ).json()
    repository.update_project(
        run["workflow_id"],
        status="needs_manual_review",
        metadata={"execution_state": "needs_manual_review", "blocked_state": {"reason": "权限需要人工确认"}},
    )

    restored = client.get(f"/chat-agent/runs/{run['id']}").json()
    clear_overrides()

    assert restored["acceptance_report_source"] == "fallback"
    assert restored["acceptance_report"]["result"] == "blocked"
    assert "权限需要人工确认" in restored["acceptance_report"]["blocking_reason"]


def test_running_run_does_not_generate_acceptance_report(tmp_path):
    client, _repository = make_client(tmp_path)
    run = client.post(
        "/chat-agent/runs",
        json={"content": "只创建不运行", "project_path": str(Path.cwd()), "force_agent": True},
    ).json()
    clear_overrides()

    assert run["acceptance_report"] is None
    assert run["acceptance_report_source"] is None
