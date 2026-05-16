from __future__ import annotations

import asyncio
from pathlib import Path

from agent_runtime_legacy.actions import WorkflowActionService
from agent_runtime_legacy.definitions import RuntimeExecutionContext
from agent_runtime_legacy.repository import WorkflowRuntimeRepository
from agent_runtime_legacy.tool_loop import AgentToolLoop
from agent_runtime_legacy.tools import AgentToolExecutor


def test_developer_loop_records_execution_state_and_final_summary(tmp_path: Path):
    repository = WorkflowRuntimeRepository(str(tmp_path / "developer_loop.db"))
    action_service = WorkflowActionService(repository)
    executor = AgentToolExecutor(repository, action_service)
    project = repository.create_project(
        {
            "title": "developer loop",
            "goal": "新增 smoke 文件",
            "template_id": "software_delivery",
            "project_path": str(Path.cwd()),
            "provider": "mock",
            "model": None,
            "approval_mode": "manual",
        }
    )
    task = repository.create_task(project["id"], "implementer", "实现", "实现任务", "running", step_key="implement")
    responses = iter(
        [
            '{"thought":"先检查","tool":"inspect_project","arguments":{}}',
            '{"thought":"识别验证","tool":"detect_project_commands","arguments":{}}',
            '{"thought":"完成","tool":"finalize","arguments":{"summary":"已完成 smoke 方案","tasks":["检查项目","识别命令"],"changed_files":[],"commands":[],"verification":"未执行","risks":[],"next_action":"请查看建议"}}',
        ]
    )

    async def model_call(_messages):
        return next(responses)

    response = asyncio.run(
        AgentToolLoop(repository, executor).run(
            agent_id="implementer",
            context=RuntimeExecutionContext(workflow_id=project["id"], goal=project["goal"], project_path=str(Path.cwd()), provider="mock"),
            step_input={"agent": {"system_prompt": "实现"}, "step": {"step_key": "implement"}},
            project=project,
            task=task,
            model_call=model_call,
        )
    )

    updated = repository.get_project(project["id"])
    assert response.output.summary == "已完成 smoke 方案"
    assert updated["metadata"]["execution_state"] == "completed"
    assert any(item["event_type"] == "agent_state_changed" for item in repository.list_events(project["id"]))
    assert [item["tool_name"] for item in repository.list_tool_calls(project["id"])] == [
        "inspect_project",
        "detect_project_commands",
        "finalize",
    ]


