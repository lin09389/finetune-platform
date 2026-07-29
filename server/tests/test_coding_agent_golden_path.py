"""Deterministic coding-agent golden-path contract audit."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from agent_session.agent_registry import AgentRegistry
from agent_session.artifact_extractor import AgentArtifactExtractor
from agent_session.deepagents_runtime import deepagents_thread_id
from agent_session.repository import AgentSessionRepository
from agent_session.state import ensure_session_state, record_diff
from agent_session.trajectory import (
    is_verification_command,
    score_trajectory,
    trajectory_policy_for_agent,
)

from workspace.path_policy import validate_agent_project_path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "coding_agent_golden_path.json"
REQUIRED_SCENARIO_KINDS = {
    "python_bug_fix",
    "react_change",
    "cross_stack_feature",
    "multi_file_refactor",
    "verification_failure_repair",
    "refresh_resume",
}
REQUIRED_FIELDS = {
    "id",
    "title",
    "kind",
    "initial_files",
    "required_reads",
    "allowed_writes",
    "commands",
    "expected_verification",
    "expected_changed_files",
    "forbidden_paths",
    "invariants",
}


def test_golden_path_fixture_has_complete_engineering_contracts():
    scenarios = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert isinstance(scenarios, list)
    assert {scenario["kind"] for scenario in scenarios} == REQUIRED_SCENARIO_KINDS
    for scenario in scenarios:
        assert REQUIRED_FIELDS <= scenario.keys(), scenario.get("id", "unknown")
        assert scenario["required_reads"]
        assert scenario["allowed_writes"]
        assert scenario["commands"]
        assert scenario["expected_changed_files"]
        assert scenario["forbidden_paths"]
        assert {"build_mode_available", "hybrid_coding_training_coexists"} <= set(
            scenario["invariants"]
        )


def test_build_contract_has_coding_tools_and_guarded_trajectory_policy():
    build = AgentRegistry().require("build")
    policy = trajectory_policy_for_agent(build)

    assert {"read_file", "write_file", "edit_file", "execute"} <= set(build.tools)
    assert policy == {
        "enabled": True,
        "require_read_before_write": True,
        "require_context_before_create": True,
        "validate_after_write": True,
        "rollback_on_validation_failure": True,
        "require_verification_after_write": True,
        "max_auto_corrections": 2,
    }


def test_workspace_policy_accepts_only_explicitly_allowed_project_roots(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path.parent / "outside-project"
    outside.mkdir(exist_ok=True)

    allowed = validate_agent_project_path(str(project), extra_roots=[tmp_path], include_registered=False)
    blocked = validate_agent_project_path(str(outside), extra_roots=[tmp_path], include_registered=False)

    assert allowed.ok is True
    assert allowed.resolved_path == str(project.resolve())
    assert blocked.ok is False
    assert blocked.error_code == "path_not_allowed"


def test_trajectory_requires_reread_after_failed_verification_and_recognizes_real_checks():
    result = score_trajectory(
        [
            {"sequence": 1, "kind": "read", "path": "/workspace/app.py", "success": True},
            {"sequence": 2, "kind": "write", "path": "/workspace/app.py", "success": True},
            {"sequence": 3, "kind": "verification", "command": "python -m pytest -q", "success": False},
            {"sequence": 4, "kind": "write", "path": "/workspace/app.py", "success": True},
            {"sequence": 5, "kind": "verification", "command": "python -m pytest -q", "success": True},
        ]
    )

    assert result["failure_recovery"] is False
    assert any(item["reason_code"] == "write_without_reread_after_failure" for item in result["violations"])
    assert is_verification_command("python -m pytest server/tests/test_price.py -q")
    assert is_verification_command("npx vitest run src/test/StatusCard.test.tsx")
    assert is_verification_command("npm run typecheck")
    assert not is_verification_command("echo looks good")


def test_session_identity_and_changed_file_projection_are_stable(tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    session = repository.create_session(
        {"id": "audit-session", "agent_id": "build", "project_path": str(tmp_path), "metadata": {}}
    )
    metadata = record_diff(ensure_session_state(session["metadata"]), "diff-1", ["server/app.py"])
    repository.update_session(session["id"], metadata=metadata)
    restored = repository.get_session(session["id"])
    extractor = AgentArtifactExtractor()
    artifacts, changed_files = extractor.extract(
        [],
        [],
        [SimpleNamespace(path="server/app.py", status="modified", summary="Fix boundary", source_part_id="diff-1", preview="- old\n+ new")],
    )

    assert deepagents_thread_id(session["id"]) == "agent_session:audit-session:deepagents"
    assert restored and restored["id"] == session["id"]
    assert restored["metadata"]["state"]["changed_files"] == ["server/app.py"]
    assert [item.path for item in changed_files] == ["server/app.py"]
    assert artifacts[0].artifact_type == "file_change"
