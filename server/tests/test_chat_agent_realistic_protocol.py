from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path

from agent_runtime_legacy.actions import WorkflowActionService
from agent_runtime_legacy.definitions import RuntimeExecutionContext
from agent_runtime_legacy.repository import WorkflowRuntimeRepository
from agent_runtime_legacy.tool_loop import AgentToolLoop
from agent_runtime_legacy.tools import AgentToolExecutor


def _make_loop(tmp_path: Path, project_path: Path | None = None):
    repository = WorkflowRuntimeRepository(str(tmp_path / f"realistic_{uuid.uuid4().hex[:8]}.db"))
    action_service = WorkflowActionService(repository)
    project = repository.create_project(
        {
            "title": "realistic protocol",
            "goal": "稳定处理真实云端模型乱序输出",
            "template_id": "software_delivery",
            "project_path": str(project_path or Path.cwd()),
            "provider": "mock",
            "model": None,
            "approval_mode": "manual",
        }
    )
    task = repository.create_task(project["id"], "implementer", "实现", "实现任务", "running", step_key="implement")
    return repository, action_service, project, task


def _run_loop(tmp_path: Path, responses: list[dict | str], max_iterations: int = 6, project_path: Path | None = None):
    repository, action_service, project, task = _make_loop(tmp_path, project_path)
    iterator = iter(responses)

    async def model_call(_messages):
        item = next(iterator)
        return item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)

    response = asyncio.run(
        AgentToolLoop(repository, AgentToolExecutor(repository, action_service), max_iterations=max_iterations).run(
            agent_id="implementer",
            context=RuntimeExecutionContext(
                workflow_id=project["id"],
                goal=project["goal"],
                project_path=str(project_path or Path.cwd()),
                provider="mock",
            ),
            step_input={"agent": {"system_prompt": "实现", "max_iterations": max_iterations}, "step": {"step_key": "implement"}},
            project=project,
            task=task,
            model_call=model_call,
        )
    )
    return response, repository, project


def test_explained_json_is_sanitized_and_executed(tmp_path: Path):
    response, repository, project = _run_loop(
        tmp_path,
        [
            '我先检查项目。\n```json\n{"tool":"inspect_project","arguments":{}}\n```',
            '检查完成后收口：{"tool_name":"finalize","args":{"summary":"已完成项目检查","next_action":"无"}}',
        ],
    )

    calls = repository.list_tool_calls(project["id"])
    assert response.output.summary == "已完成项目检查"
    assert calls[0]["tool_name"] == "inspect_project"
    assert calls[0]["sanitized_model_output"].startswith("{")


def test_out_of_order_patch_is_guided_to_read_context_first(tmp_path: Path):
    response, repository, project = _run_loop(
        tmp_path,
        [
            {
                "tool": "propose_patch",
                "arguments": {
                    "title": "跳步补丁",
                    "payload": {"files": [{"path": "tmp/realistic_jump.txt", "content": "jump"}]},
                },
            },
            {"tool": "inspect_project", "arguments": {}},
            {"tool": "finalize", "arguments": {"summary": "已按纠偏要求先读取项目上下文", "next_action": "重新生成补丁"}},
        ],
    )

    calls = repository.list_tool_calls(project["id"])
    assert response.output.summary == "已按纠偏要求先读取项目上下文"
    assert calls[0]["tool_name"] == "propose_patch"
    assert calls[0]["status"] == "failed"
    assert calls[0]["result_payload"]["required_tools"] == ["inspect_project", "search_code", "read_file"]
    assert "先读取项目结构" in calls[0]["result_payload"]["next_action"]


def test_out_of_order_command_is_guided_to_detect_commands_first(tmp_path: Path):
    response, repository, project = _run_loop(
        tmp_path,
        [
            {
                "tool": "propose_command",
                "arguments": {
                    "title": "跳步验证",
                    "payload": {"command": ["python", "-m", "py_compile", "missing.py"]},
                },
            },
            {"tool": "detect_project_commands", "arguments": {}},
            {"tool": "finalize", "arguments": {"summary": "已按纠偏要求先识别验证命令", "next_action": "重新生成命令"}},
        ],
    )

    calls = repository.list_tool_calls(project["id"])
    assert response.output.summary == "已按纠偏要求先识别验证命令"
    assert calls[0]["tool_name"] == "propose_command"
    assert calls[0]["status"] == "failed"
    assert calls[0]["result_payload"]["required_tool"] == "detect_project_commands"


def test_auto_patch_then_command_without_finalize_gets_fallback_summary(tmp_path: Path):
    workspace = Path.cwd()
    smoke_dir = workspace / "tmp" / f"realistic-{uuid.uuid4().hex[:8]}"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    target = smoke_dir / "smoke_module.py"
    relative_target = target.relative_to(workspace).as_posix()
    try:
        response, repository, project = _run_loop(
            tmp_path,
            [
                {"tool": "inspect_project", "arguments": {}},
                {"tool": "detect_project_commands", "arguments": {}},
                {
                    "tool": "propose_patch",
                    "arguments": {
                        "title": "新增 smoke 文件",
                        "payload": {"files": [{"path": relative_target, "content": "VALUE = 1\n"}]},
                    },
                },
                {
                    "tool": "propose_command",
                    "arguments": {
                        "title": "编译 smoke 文件",
                        "payload": {"command": ["python", "-m", "py_compile", relative_target]},
                    },
                },
            ],
            max_iterations=4,
        )

        actions = repository.list_action_proposals(project["id"])
        metadata = repository.get_project(project["id"])["metadata"]
        assert response.needs_manual_review is False
        assert response.fallback_summary_used is True
        assert "兜底总结" in response.output.summary
        assert metadata["model_protocol_status"] == "fallback_summary"
        assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
        assert any(action["action_type"] == "patch" and action["status"] == "executed" for action in actions)
        assert any(action["action_type"] == "command" and action["status"] == "executed" for action in actions)
    finally:
        shutil.rmtree(smoke_dir, ignore_errors=True)


def test_command_failure_can_be_read_before_finalize(tmp_path: Path):
    response, repository, project = _run_loop(
        tmp_path,
        [
            {"tool": "inspect_project", "arguments": {}},
            {"tool": "detect_project_commands", "arguments": {}},
            {
                "tool": "propose_command",
                "arguments": {
                    "title": "故意失败的编译",
                    "payload": {"command": ["python", "-m", "py_compile", "tmp/not_found_for_repair.py"]},
                },
            },
            {"tool": "read_test_failures", "arguments": {}},
            {"tool": "finalize", "arguments": {"summary": "已读取验证失败摘要，需要人工或下一轮修复", "next_action": "根据失败摘要修复"}},
        ],
    )

    calls = repository.list_tool_calls(project["id"])
    failure_call = next(call for call in calls if call["tool_name"] == "read_test_failures")
    command_action = next(action for action in repository.list_action_proposals(project["id"]) if action["action_type"] == "command")
    assert response.output.summary == "已读取验证失败摘要，需要人工或下一轮修复"
    assert command_action["status"] == "failed"
    assert failure_call["result_payload"]["failures"]


def test_repeated_tool_call_enters_manual_review_with_blocked_state(tmp_path: Path):
    response, repository, project = _run_loop(
        tmp_path,
        [
            {"tool": "inspect_project", "arguments": {}},
            {"tool": "inspect_project", "arguments": {}},
            {"tool": "inspect_project", "arguments": {}},
        ],
        max_iterations=4,
    )

    metadata = repository.get_project(project["id"])["metadata"]
    assert response.needs_manual_review is True
    assert metadata["execution_state"] == "needs_manual_review"
    assert metadata["blocked_state"]["reason"] == "repeated_tool_call"


def test_unparseable_model_output_has_blocked_state(tmp_path: Path):
    response, repository, project = _run_loop(tmp_path, ["不是 JSON", "仍然不是 JSON"])

    metadata = repository.get_project(project["id"])["metadata"]
    assert response.needs_manual_review is True
    assert metadata["model_protocol_status"] == "needs_manual_review"
    assert metadata["blocked_state"]["reason"] == "unparseable_model_output"

