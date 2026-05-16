from __future__ import annotations

import asyncio
from pathlib import Path

from agent_runtime.repository import WorkflowRuntimeRepository
from agent_runtime.service import AgentRuntimeService
from agent_runtime.models import WorkflowCreate
from digital_team.models import AgentOutput


class RepairRunner:
    async def repair_after_action_failure(self, project, action):
        return AgentOutput(
            summary="生成修复建议",
            artifacts=[
                {
                    "type": "patch",
                    "title": "修复 smoke 文件",
                    "payload": {"files": [{"path": "tmp_repair_patch.txt", "content": "repair"}]},
                }
            ],
            next_action="请审批修复补丁",
            requires_approval=True,
        )


def test_failed_action_triggers_one_repair_proposal(tmp_path):
    repository = WorkflowRuntimeRepository(str(tmp_path / "repair.db"))
    service = AgentRuntimeService(repository=repository, runner=RepairRunner())
    workflow = service.create_workflow(
        WorkflowCreate(
            title="repair",
            goal="失败后修复",
            template_id="software_delivery",
            project_path=str(Path.cwd()),
        )
    )
    action = repository.add_action_proposal(
        workflow.workflow_id,
        None,
        "command",
        "失败命令",
        payload={"command": ["python", "-m", "py_compile", "missing_file_for_repair.py"]},
    )
    asyncio.run(service.approve_action(action["id"]))
    failed = asyncio.run(service.execute_action(action["id"]))

    repair = asyncio.run(service.repair_after_failed_action(failed.id))
    project = repository.get_project(workflow.workflow_id)
    actions = repository.list_action_proposals(workflow.workflow_id)

    assert failed.status == "failed"
    assert repair is not None
    assert project["metadata"]["repair_attempts"] == 1
    assert any(item["action_type"] == "patch" and item["status"] == "pending_approval" for item in actions)


def test_second_failure_enters_manual_review_without_auto_execution(tmp_path):
    repository = WorkflowRuntimeRepository(str(tmp_path / "repair_limit.db"))
    service = AgentRuntimeService(repository=repository, runner=RepairRunner())
    workflow = service.create_workflow(
        WorkflowCreate(
            title="repair-limit",
            goal="失败后限制",
            template_id="software_delivery",
            project_path=str(Path.cwd()),
        )
    )
    repository.update_project(workflow.workflow_id, metadata={"repair_attempts": 1, "max_repair_attempts": 1})
    action = repository.add_action_proposal(
        workflow.workflow_id,
        None,
        "command",
        "失败命令",
        payload={"command": ["python", "-m", "py_compile", "missing_file_for_repair.py"]},
    )
    asyncio.run(service.approve_action(action["id"]))
    failed = asyncio.run(service.execute_action(action["id"]))
    repair = asyncio.run(service.repair_after_failed_action(failed.id))
    project = repository.get_project(workflow.workflow_id)

    assert repair is None
    assert project["status"] == "needs_manual_review"
    assert project["metadata"]["repair_attempts"] == 1
