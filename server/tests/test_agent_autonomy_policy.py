from __future__ import annotations

import uuid
from pathlib import Path

from agent_runtime.actions import WorkflowActionService
from agent_runtime.repository import WorkflowRuntimeRepository
from digital_team.models import AgentOutput


def make_service(tmp_path: Path, autonomy_mode: str = "safe_auto"):
    repository = WorkflowRuntimeRepository(str(tmp_path / f"autonomy_{autonomy_mode}.db"))
    project = repository.create_project(
        {
            "title": f"autonomy {autonomy_mode}",
            "goal": "验证自主执行策略",
            "template_id": "software_delivery",
            "project_path": str(Path.cwd()),
            "provider": "mock",
            "model": None,
            "approval_mode": "manual",
        }
    )
    metadata = dict(project.get("metadata") or {})
    metadata["autonomy_mode"] = autonomy_mode
    metadata["auto_execution_policy"] = {"mode": autonomy_mode}
    repository.update_project(project["id"], metadata=metadata)
    project = repository.get_project(project["id"])
    task = repository.create_task(project["id"], "implementer", "实现", "实现任务", "running", step_key="implement")
    return WorkflowActionService(repository), repository, project, task


def patch_output(path: str, content: str = "smoke\n") -> AgentOutput:
    return AgentOutput(
        summary="生成补丁",
        artifacts=[
            {
                "type": "patch",
                "title": "安全补丁",
                "payload": {"files": [{"path": path, "content": content}]},
            }
        ],
    )


def command_output(command: list[str] | str) -> AgentOutput:
    return AgentOutput(
        summary="生成命令",
        artifacts=[
            {
                "type": "command",
                "title": "验证命令",
                "payload": {"command": command, "timeout_seconds": 120},
            }
        ],
    )


def test_safe_auto_executes_low_risk_tmp_patch(tmp_path):
    service, _, project, task = make_service(tmp_path, "safe_auto")
    path = f"tmp/autonomy-{uuid.uuid4().hex[:8]}.txt"
    target = Path.cwd() / path

    try:
        actions = service.extract_from_output(project["id"], task["id"], patch_output(path))
        action = actions[0]

        assert action["status"] == "executed"
        assert action["execution_mode"] == "auto"
        assert action["policy_decision"] == "auto"
        assert action["risk_level"] == "low"
        assert "安全自动" in action["policy_reason"]
        assert action["auto_executed_at"]
        assert action["changed_files"] == [path]
        assert target.read_text(encoding="utf-8") == "smoke\n"
    finally:
        if target.exists():
            target.unlink()


def test_safe_auto_executes_allowlisted_command(tmp_path):
    smoke = Path.cwd() / "tmp" / f"autonomy-{uuid.uuid4().hex[:8]}.py"
    smoke.parent.mkdir(parents=True, exist_ok=True)
    smoke.write_text("VALUE = 1\n", encoding="utf-8")
    service, _, project, task = make_service(tmp_path, "safe_auto")

    try:
        actions = service.extract_from_output(
            project["id"],
            task["id"],
            command_output(["python", "-m", "py_compile", smoke.relative_to(Path.cwd()).as_posix()]),
        )
        action = actions[0]

        assert action["status"] == "executed"
        assert action["execution_mode"] == "auto"
        assert action["risk_level"] == "low"
        assert action["executions"][-1]["exit_code"] == 0
    finally:
        if smoke.exists():
            smoke.unlink()


def test_confirm_all_keeps_patch_and_command_pending(tmp_path):
    service, _, project, task = make_service(tmp_path, "confirm_all")

    patch = service.extract_from_output(project["id"], task["id"], patch_output("tmp/autonomy-confirm.txt"))[0]
    command = service.extract_from_output(
        project["id"],
        task["id"],
        command_output(["python", "-m", "py_compile", "tmp/autonomy-confirm.py"]),
    )[0]

    assert patch["status"] == "pending_approval"
    assert patch["execution_mode"] == "approval_required"
    assert patch["risk_level"] == "low"
    assert "确认模式" in patch["policy_reason"]
    assert command["status"] == "pending_approval"
    assert command["execution_mode"] == "approval_required"
    assert command["risk_level"] == "low"
    assert "确认模式" in command["policy_reason"]


def test_read_only_blocks_patch_and_command(tmp_path):
    service, _, project, task = make_service(tmp_path, "read_only")

    patch = service.extract_from_output(project["id"], task["id"], patch_output("tmp/autonomy-readonly.txt"))[0]
    command = service.extract_from_output(
        project["id"],
        task["id"],
        command_output(["python", "-m", "py_compile", "tmp/autonomy-readonly.py"]),
    )[0]

    assert patch["status"] == "blocked"
    assert patch["execution_mode"] == "blocked"
    assert patch["risk_level"] == "high"
    assert "只读模式" in patch["policy_reason"]
    assert command["status"] == "blocked"
    assert command["execution_mode"] == "blocked"
    assert "只读模式" in command["policy_reason"]


def test_sensitive_files_and_shell_strings_are_blocked(tmp_path):
    service, _, project, task = make_service(tmp_path, "safe_auto")

    package_patch = service.extract_from_output(project["id"], task["id"], patch_output("package.json", "{}\n"))[0]
    shell_command = service.extract_from_output(
        project["id"],
        task["id"],
        command_output("python -m py_compile tmp/example.py"),
    )[0]

    assert package_patch["status"] == "blocked"
    assert package_patch["risk_level"] == "high"
    assert "敏感" in package_patch["policy_reason"]
    assert shell_command["status"] == "blocked"
    assert shell_command["risk_level"] == "high"
    assert "argv 数组" in shell_command["policy_reason"]
