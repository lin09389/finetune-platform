from __future__ import annotations

from pathlib import Path

from agent_runtime_legacy.actions import WorkflowActionService
from agent_runtime_legacy.repository import WorkflowRuntimeRepository
from digital_team.models import AgentOutput


def make_policy_service(tmp_path: Path):
    repository = WorkflowRuntimeRepository(str(tmp_path / "source_diff_policy.db"))
    project = repository.create_project(
        {
            "title": "source diff policy",
            "goal": "自动执行低风险源码 diff 小改",
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


def diff_output(diff: str) -> AgentOutput:
    return AgentOutput(
        summary="生成源码 diff 补丁",
        artifacts=[
            {
                "type": "patch",
                "title": "source diff patch",
                "payload": {"format": "unified_diff", "diff": diff},
            }
        ],
    )


def one_line_diff(path: str, old: str = "VALUE = 'old'", new: str = "VALUE = 'new'") -> str:
    return f"""--- a/{path}
+++ b/{path}
@@ -1 +1 @@
-{old}
+{new}
"""


def test_small_read_source_diff_auto_executes(tmp_path):
    target = Path.cwd() / "tmp_source_diff_policy_auto.py"
    original = "VALUE = 'old'\n"
    existed = target.exists()
    previous = target.read_text(encoding="utf-8") if existed else None
    target.write_text(original, encoding="utf-8")
    service, repository, project, task = make_policy_service(tmp_path)
    mark_read(repository, project["id"], task["id"], target.name)

    try:
        actions = service.extract_from_output(project["id"], task["id"], diff_output(one_line_diff(target.name)))
        action = actions[0]

        assert action["status"] == "executed"
        assert action["execution_mode"] == "auto"
        assert action["policy_reason"] == "低风险源码 diff 小改，已按安全自动模式执行"
        assert action["changed_files"] == [target.name]
        assert action["applied_hunks"] == 1
        assert target.read_text(encoding="utf-8") == "VALUE = 'new'\n"
    finally:
        if existed and previous is not None:
            target.write_text(previous, encoding="utf-8")
        elif target.exists():
            target.unlink()


def test_unread_source_diff_requires_approval(tmp_path):
    service, _, project, task = make_policy_service(tmp_path)

    actions = service.extract_from_output(project["id"], task["id"], diff_output(one_line_diff("tmp_source_diff_unread.py")))

    assert actions[0]["status"] == "pending_approval"
    assert actions[0]["execution_mode"] == "approval_required"
    assert "未在同一轮被读取或搜索命中" in actions[0]["policy_reason"]


def test_large_source_diff_requires_approval(tmp_path):
    service, repository, project, task = make_policy_service(tmp_path)
    path = "tmp_source_diff_large.py"
    mark_read(repository, project["id"], task["id"], path)
    removed = "\n".join(f"-VALUE_{index} = {index}" for index in range(121))
    added = "\n".join(f"+VALUE_{index} = {index + 1}" for index in range(121))
    diff = f"--- a/{path}\n+++ b/{path}\n@@ -1,121 +1,121 @@\n{removed}\n{added}\n"

    actions = service.extract_from_output(project["id"], task["id"], diff_output(diff))

    assert actions[0]["status"] == "pending_approval"
    assert actions[0]["execution_mode"] == "approval_required"
    assert "超过 120 行" in actions[0]["policy_reason"]


def test_sensitive_source_diff_is_blocked(tmp_path):
    service, repository, project, task = make_policy_service(tmp_path)
    mark_read(repository, project["id"], task["id"], "package.json")

    actions = service.extract_from_output(project["id"], task["id"], diff_output(one_line_diff("package.json", "{}", "{\"scripts\":{}}")))

    assert actions[0]["status"] == "blocked"
    assert actions[0]["execution_mode"] == "blocked"
    assert actions[0]["risk_level"] == "high"
    assert "敏感" in actions[0]["policy_reason"]


def test_delete_or_rename_diff_is_blocked(tmp_path):
    service, repository, project, task = make_policy_service(tmp_path)
    mark_read(repository, project["id"], task["id"], "tmp_source_diff_delete.py")
    diff = """--- a/tmp_source_diff_delete.py
+++ /dev/null
@@ -1 +0,0 @@
-VALUE = 1
"""

    actions = service.extract_from_output(project["id"], task["id"], diff_output(diff))

    assert actions[0]["status"] == "blocked"
    assert actions[0]["execution_mode"] == "blocked"
    assert "删除" in actions[0]["policy_reason"]


def test_three_small_read_source_diffs_auto_execute(tmp_path):
    targets = [Path.cwd() / f"tmp_source_diff_multi_{index}.py" for index in range(3)]
    previous: list[str | None] = []
    for target in targets:
        previous.append(target.read_text(encoding="utf-8") if target.exists() else None)
        target.write_text("VALUE = 1\n", encoding="utf-8")
    service, repository, project, task = make_policy_service(tmp_path)
    for target in targets:
        mark_read(repository, project["id"], task["id"], target.name)
    diff = "".join(one_line_diff(target.name, "VALUE = 1", f"VALUE = {index + 2}") for index, target in enumerate(targets))

    try:
        actions = service.extract_from_output(project["id"], task["id"], diff_output(diff))

        assert actions[0]["status"] == "executed"
        assert actions[0]["execution_mode"] == "auto"
    finally:
        for target, content in zip(targets, previous):
            if content is None and target.exists():
                target.unlink()
            elif content is not None:
                target.write_text(content, encoding="utf-8")

