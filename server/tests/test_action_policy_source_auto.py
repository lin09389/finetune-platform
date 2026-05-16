from __future__ import annotations

from pathlib import Path

from agent_runtime_legacy.actions import WorkflowActionService
from agent_runtime_legacy.repository import WorkflowRuntimeRepository
from digital_team.models import AgentOutput


def make_policy_service(tmp_path: Path):
    repository = WorkflowRuntimeRepository(str(tmp_path / "source_policy.db"))
    project = repository.create_project(
        {
            "title": "source policy",
            "goal": "自动执行低风险源码小改",
            "template_id": "software_delivery",
            "project_path": str(Path.cwd()),
            "provider": "mock",
            "model": None,
            "approval_mode": "manual",
        }
    )
    task = repository.create_task(project["id"], "implementer", "实现", "实现任务", "running", step_key="implement")
    return WorkflowActionService(repository), repository, project, task


def mark_read(repository: WorkflowRuntimeRepository, project_id: str, task_id: str | None, path: str):
    repository.add_tool_call(
        workflow_id=project_id,
        step_id=task_id,
        agent_id="implementer",
        tool_name="read_file",
        arguments={"path": path},
        status="completed",
        result_summary=f"读取文件 {path}",
        result_payload={"path": path},
    )


def patch_output(path: str, content: str) -> AgentOutput:
    return AgentOutput(
        summary="生成源码补丁",
        artifacts=[
            {
                "type": "patch",
                "title": "source patch",
                "payload": {"files": [{"path": path, "content": content}]},
            }
        ],
    )


def test_small_read_source_patch_auto_executes(tmp_path):
    target = Path.cwd() / "tmp_source_policy_auto.py"
    original = "VALUE = 'old'\n"
    existed = target.exists()
    previous = target.read_text(encoding="utf-8") if existed else None
    target.write_text(original, encoding="utf-8")
    service, repository, project, task = make_policy_service(tmp_path)
    mark_read(repository, project["id"], task["id"], target.name)

    try:
        actions = service.extract_from_output(project["id"], task["id"], patch_output(target.name, "VALUE = 'new'\n"))
        action = actions[0]

        assert action["status"] == "executed"
        assert action["execution_mode"] == "auto"
        assert action["policy_reason"] == "低风险源码小改，已按安全自动模式执行"
        assert action["changed_files"] == [target.name]
        assert action["auto_executed_at"]
        assert action["applied_hunks"] == 1
        assert target.read_text(encoding="utf-8") == "VALUE = 'new'\n"
    finally:
        if existed and previous is not None:
            target.write_text(previous, encoding="utf-8")
        elif target.exists():
            target.unlink()


def test_unread_source_patch_requires_approval(tmp_path):
    service, _, project, task = make_policy_service(tmp_path)

    actions = service.extract_from_output(project["id"], task["id"], patch_output("tmp_source_policy_unread.py", "VALUE = 1\n"))

    assert actions[0]["status"] == "pending_approval"
    assert actions[0]["execution_mode"] == "approval_required"
    assert "未在同一轮被读取或搜索命中" in actions[0]["policy_reason"]


def test_sensitive_source_patch_is_blocked(tmp_path):
    service, repository, project, task = make_policy_service(tmp_path)
    mark_read(repository, project["id"], task["id"], "package.json")

    actions = service.extract_from_output(project["id"], task["id"], patch_output("package.json", "{}\n"))

    assert actions[0]["status"] == "blocked"
    assert actions[0]["execution_mode"] == "blocked"
    assert actions[0]["risk_level"] == "high"
    assert "敏感" in actions[0]["policy_reason"]


def test_large_source_patch_requires_approval(tmp_path):
    service, repository, project, task = make_policy_service(tmp_path)
    mark_read(repository, project["id"], task["id"], "tmp_source_policy_large.py")

    content = "\n".join(f"VALUE_{index} = {index}" for index in range(121))
    actions = service.extract_from_output(project["id"], task["id"], patch_output("tmp_source_policy_large.py", content))

    assert actions[0]["status"] == "pending_approval"
    assert actions[0]["execution_mode"] == "approval_required"
    assert "超过 120 行" in actions[0]["policy_reason"]


def test_three_small_read_source_patches_auto_execute(tmp_path):
    service, repository, project, task = make_policy_service(tmp_path)
    targets = [Path.cwd() / f"tmp_source_policy_multi_{index}.py" for index in range(3)]
    previous: list[str | None] = []
    for target in targets:
        previous.append(target.read_text(encoding="utf-8") if target.exists() else None)
        mark_read(repository, project["id"], task["id"], target.name)

    output = AgentOutput(
        summary="生成多文件源码补丁",
        artifacts=[
            {
                "type": "patch",
                "title": "source patch",
                "payload": {
                    "files": [{"path": target.name, "content": f"VALUE_{index} = {index}\n"} for index, target in enumerate(targets)]
                },
            }
        ],
    )

    try:
        actions = service.extract_from_output(project["id"], task["id"], output)

        assert actions[0]["status"] == "executed"
        assert actions[0]["execution_mode"] == "auto"
    finally:
        for target, content in zip(targets, previous):
            if content is None and target.exists():
                target.unlink()
            elif content is not None:
                target.write_text(content, encoding="utf-8")

