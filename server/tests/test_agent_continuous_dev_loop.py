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


def _make_project(repository: WorkflowRuntimeRepository, project_path: Path) -> dict:
    return repository.create_project(
        {
            "title": "continuous dev loop",
            "goal": "修改 smoke 文件并运行验证",
            "template_id": "software_delivery",
            "project_path": str(project_path),
            "provider": "mock",
            "model": None,
            "approval_mode": "manual",
        }
    )


def test_continuous_dev_loop_applies_patch_runs_command_and_finalizes(tmp_path: Path):
    repository = WorkflowRuntimeRepository(str(tmp_path / "continuous_loop.db"))
    action_service = WorkflowActionService(repository)
    executor = AgentToolExecutor(repository, action_service)
    workspace = Path.cwd()
    smoke_dir = workspace / "tmp" / f"agent-loop-{uuid.uuid4().hex[:8]}"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    smoke_file = smoke_dir / "smoke_module.py"
    smoke_file.write_text("VALUE = 1\n", encoding="utf-8")
    relative_file = smoke_file.relative_to(workspace).as_posix()

    project = _make_project(repository, workspace)
    task = repository.create_task(project["id"], "implementer", "实现", "实现任务", "running", step_key="implement")
    responses = iter(
        [
            {"thought": "先检查项目", "tool": "inspect_project", "arguments": {}},
            {"thought": "识别验证命令", "tool": "detect_project_commands", "arguments": {}},
            {"thought": "读取目标文件", "tool": "read_file", "arguments": {"path": relative_file}},
            {
                "thought": "生成安全小补丁",
                "tool": "propose_patch",
                "arguments": {
                    "title": "更新 smoke 文件",
                    "description": "把 smoke 文件内容改为新值",
                    "payload": {"files": [{"path": relative_file, "content": "VALUE = 2\n"}]},
                },
            },
            {
                "thought": "运行验证命令",
                "tool": "propose_command",
                "arguments": {
                    "title": "编译 smoke 文件",
                    "description": "验证 Python 文件语法",
                    "payload": {"command": ["python", "-m", "py_compile", relative_file], "timeout_seconds": 120},
                },
            },
            {
                "thought": "完成交付",
                "tool": "finalize",
                "arguments": {
                    "summary": "已完成 smoke 文件修改并通过 py_compile 验证",
                    "tasks": ["检查项目", "识别验证命令", "读取文件", "应用补丁", "运行验证"],
                    "changed_files": [relative_file],
                    "commands": [f"python -m py_compile {relative_file}"],
                    "verification": "通过",
                    "risks": [],
                    "next_action": "无需进一步操作",
                },
            },
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    try:
        response = asyncio.run(
            AgentToolLoop(repository, executor).run(
                agent_id="implementer",
                context=RuntimeExecutionContext(
                    workflow_id=project["id"],
                    goal=project["goal"],
                    project_path=str(workspace),
                    provider="mock",
                ),
                step_input={"agent": {"system_prompt": "实现"}, "step": {"step_key": "implement"}},
                project=project,
                task=task,
                model_call=model_call,
            )
        )

        actions = repository.list_action_proposals(project["id"])
        patch_action = next(action for action in actions if action["action_type"] == "patch")
        command_action = next(action for action in actions if action["action_type"] == "command")

        assert response.output.summary == "已完成 smoke 文件修改并通过 py_compile 验证"
        assert smoke_file.read_text(encoding="utf-8") == "VALUE = 2\n"
        assert patch_action["status"] == "executed"
        assert patch_action["changed_files"] == [relative_file]
        assert patch_action["applied_hunks"] == 1
        assert patch_action["patch_summaries"][0]["path"] == relative_file
        assert command_action["status"] == "executed"
        assert command_action["executions"][-1]["exit_code"] == 0
        assert repository.get_project(project["id"])["metadata"]["execution_state"] == "completed"
        assert [call["tool_name"] for call in repository.list_tool_calls(project["id"])] == [
            "inspect_project",
            "detect_project_commands",
            "read_file",
            "propose_patch",
            "propose_command",
            "finalize",
        ]
    finally:
        shutil.rmtree(smoke_dir, ignore_errors=True)


def test_propose_command_guides_model_to_detect_project_commands_first(tmp_path: Path):
    repository = WorkflowRuntimeRepository(str(tmp_path / "command_order.db"))
    action_service = WorkflowActionService(repository)
    executor = AgentToolExecutor(repository, action_service)
    workspace = Path.cwd()
    project = _make_project(repository, workspace)
    task = repository.create_task(project["id"], "implementer", "实现", "实现任务", "running", step_key="implement")
    responses = iter(
        [
            {
                "thought": "先尝试验证",
                "tool": "propose_command",
                "arguments": {
                    "title": "运行验证",
                    "payload": {"command": ["python", "-m", "py_compile", "missing.py"]},
                },
            },
            {"thought": "按系统要求先识别命令", "tool": "detect_project_commands", "arguments": {}},
            {
                "thought": "结束",
                "tool": "finalize",
                "arguments": {
                    "summary": "已识别需要先探测验证命令",
                    "risks": [],
                    "next_action": "重新生成验证命令",
                },
            },
        ]
    )

    async def model_call(_messages):
        return json.dumps(next(responses), ensure_ascii=False)

    response = asyncio.run(
        AgentToolLoop(repository, executor).run(
            agent_id="implementer",
            context=RuntimeExecutionContext(
                workflow_id=project["id"],
                goal=project["goal"],
                project_path=str(workspace),
                provider="mock",
            ),
            step_input={"agent": {"system_prompt": "实现"}, "step": {"step_key": "implement"}},
            project=project,
            task=task,
            model_call=model_call,
        )
    )

    calls = repository.list_tool_calls(project["id"])
    assert response.output.summary == "已识别需要先探测验证命令"
    assert calls[0]["tool_name"] == "propose_command"
    assert calls[0]["status"] == "failed"
    assert calls[0]["result_payload"]["required_tool"] == "detect_project_commands"
    assert [call["tool_name"] for call in calls] == ["propose_command", "detect_project_commands", "finalize"]

