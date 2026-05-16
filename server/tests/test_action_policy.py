from pathlib import Path

from agent_runtime_legacy.actions import WorkflowActionService
from agent_runtime_legacy.repository import WorkflowRuntimeRepository
from digital_team.models import AgentOutput


def _workspace_root() -> Path:
    cwd = Path.cwd().resolve()
    return cwd.parent if cwd.name == "server" else cwd


def make_policy_service(tmp_path: Path):
    repository = WorkflowRuntimeRepository(str(tmp_path / "action_policy.db"))
    project = repository.create_project(
        {
            "title": "policy",
            "goal": "policy",
            "template_id": "software_delivery",
            "project_path": str(_workspace_root()),
            "provider": "minimax",
            "model": None,
            "approval_mode": "manual",
        }
    )
    return WorkflowActionService(repository), repository, project


def test_safe_tmp_patch_auto_executes(tmp_path):
    target = _workspace_root() / "tmp" / "policy_auto_patch.txt"
    if target.exists():
        target.unlink()
    service, _, project = make_policy_service(tmp_path)
    output = AgentOutput(
        summary="生成安全补丁",
        artifacts=[
            {
                "type": "patch",
                "title": "tmp patch",
                "payload": {"files": [{"path": "tmp/policy_auto_patch.txt", "content": "ok"}]},
            }
        ],
    )
    try:
        actions = service.extract_from_output(project["id"], None, output)
        assert actions[0]["status"] == "executed"
        assert actions[0]["execution_mode"] == "auto"
        assert actions[0]["changed_files"] == ["tmp/policy_auto_patch.txt"]
        assert target.read_text(encoding="utf-8") == "ok"
    finally:
        if target.exists():
            target.unlink()


def test_workspace_root_patch_requires_approval(tmp_path):
    service, _, project = make_policy_service(tmp_path)
    output = AgentOutput(
        summary="生成业务补丁",
        artifacts=[
            {
                "type": "patch",
                "title": "root patch",
                "payload": {"files": [{"path": "policy_root_patch.txt", "content": "ok"}]},
            }
        ],
    )
    actions = service.extract_from_output(project["id"], None, output)

    assert actions[0]["status"] == "pending_approval"
    assert actions[0]["execution_mode"] == "approval_required"


def test_allowlisted_command_auto_executes(tmp_path):
    service, _, project = make_policy_service(tmp_path)
    output = AgentOutput(
        summary="运行白名单命令",
        artifacts=[
            {
                "type": "command",
                "title": "typecheck",
                "payload": {"command": ["python", "-m", "py_compile", "server/agent_runtime/actions.py"]},
            }
        ],
    )
    actions = service.extract_from_output(project["id"], None, output)

    assert actions[0]["status"] == "executed"
    assert actions[0]["execution_mode"] == "auto"
    assert actions[0]["executions"][-1]["exit_code"] == 0

