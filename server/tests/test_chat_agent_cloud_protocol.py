from __future__ import annotations

import asyncio
from pathlib import Path

from agent_runtime.actions import WorkflowActionService
from agent_runtime.definitions import RuntimeExecutionContext
from agent_runtime.repository import WorkflowRuntimeRepository
from agent_runtime.tool_loop import AgentToolLoop
from agent_runtime.tools import AgentToolExecutor


def make_loop(tmp_path: Path):
    repository = WorkflowRuntimeRepository(str(tmp_path / "cloud_protocol.db"))
    action_service = WorkflowActionService(repository)
    project = repository.create_project(
        {
            "title": "cloud protocol",
            "goal": "稳定解析真实模型输出",
            "template_id": "software_delivery",
            "project_path": str(Path.cwd()),
            "provider": "mock",
            "model": None,
            "approval_mode": "manual",
        }
    )
    task = repository.create_task(project["id"], "implementer", "实现", "实现任务", "running", step_key="implement")
    return repository, action_service, project, task


def run_loop(tmp_path: Path, responses: list[str], max_iterations: int = 4):
    repository, action_service, project, task = make_loop(tmp_path)
    iterator = iter(responses)

    async def model_call(_messages):
        return next(iterator)

    response = asyncio.run(
        AgentToolLoop(repository, AgentToolExecutor(repository, action_service), max_iterations=max_iterations).run(
            agent_id="implementer",
            context=RuntimeExecutionContext(
                workflow_id=project["id"],
                goal=project["goal"],
                project_path=str(Path.cwd()),
                provider="mock",
            ),
            step_input={"agent": {"system_prompt": "实现", "max_iterations": max_iterations}, "step": {"step_key": "implement"}},
            project=project,
            task=task,
            model_call=model_call,
        )
    )
    return response, repository, project


def test_markdown_json_and_prefixed_json_parse(tmp_path):
    response, repository, project = run_loop(
        tmp_path,
        [
            '```json\n{"thought":"先看项目","tool":"inspect_project","arguments":{}}\n```',
            '好的，下一步：{"tool_name":"finalize","args":{"summary":"已完成检查","next_action":"无"}}',
        ],
    )

    assert response.output.summary == "已完成检查"
    calls = repository.list_tool_calls(project["id"])
    assert calls[0]["raw_model_output"].startswith("```json")
    assert calls[0]["sanitized_model_output"].startswith("{")


def test_missing_tool_field_repairs_once(tmp_path):
    response, repository, project = run_loop(
        tmp_path,
        [
            '{"thought":"缺少工具"}',
            '{"name":"finalize","parameters":{"summary":"修复后完成","next_action":"无"}}',
        ],
    )

    metadata = repository.get_project(project["id"])["metadata"]
    assert response.output.summary == "修复后完成"
    assert metadata["model_protocol_status"] == "repaired"
    assert metadata["parse_repair_count"] == 1


def test_plain_final_text_requires_manual_review(tmp_path):
    response, repository, project = run_loop(
        tmp_path,
        [
            "最终结果：已经完成检查，没有需要执行的补丁。",
            "仍然是普通文本，没有按协议输出 JSON。",
        ],
    )

    metadata = repository.get_project(project["id"])["metadata"]
    assert response.needs_manual_review is True
    assert "不是可解析的工具 JSON" in response.output.summary
    assert metadata["model_protocol_status"] == "needs_manual_review"
    assert metadata["fallback_summary_used"] is False


def test_missing_finalize_generates_backend_fallback_summary(tmp_path):
    target = Path.cwd() / "tmp" / "cloud_protocol_fallback.txt"
    if target.exists():
        target.unlink()
    try:
        response, repository, project = run_loop(
            tmp_path,
            [
                '{"tool":"inspect_project","arguments":{}}',
                '{"tool":"propose_patch","arguments":{"title":"fallback patch","payload":{"files":[{"path":"tmp/cloud_protocol_fallback.txt","content":"ok"}]}}}',
            ],
            max_iterations=2,
        )
        metadata = repository.get_project(project["id"])["metadata"]
        assert response.needs_manual_review is False
        assert "兜底总结" in response.output.summary
        assert target.read_text(encoding="utf-8") == "ok"
        assert metadata["model_protocol_status"] == "fallback_summary"
    finally:
        if target.exists():
            target.unlink()


def test_consecutive_parse_failures_need_manual_review(tmp_path):
    response, repository, project = run_loop(tmp_path, ["不是 JSON", "仍然不是 JSON"])

    metadata = repository.get_project(project["id"])["metadata"]
    assert response.needs_manual_review is True
    assert metadata["model_protocol_status"] == "needs_manual_review"
    assert metadata["parse_repair_count"] == 1
