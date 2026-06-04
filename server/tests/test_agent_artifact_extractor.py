from __future__ import annotations

from types import SimpleNamespace

from agent_session.artifact_extractor import AgentArtifactExtractor
from agent_session.models import AgentArtifactResponse


def _part(part_type: str, part_id: str, **kwargs):
    return SimpleNamespace(
        id=part_id,
        type=part_type,
        status=kwargs.get("status", "completed"),
        title=kwargs.get("title"),
        content=kwargs.get("content", ""),
        payload=kwargs.get("payload", {}),
        created_at="2026-01-01T00:00:00",
    )


def test_artifact_extractor_derives_file_changes_and_command_results():
    extractor = AgentArtifactExtractor()
    diff = AgentArtifactResponse(
        id="diff_1",
        path="/workspace/app.py",
        status="modified",
        summary="更新入口",
        preview="@@ patch",
        source_part_id="part_diff",
    )
    command = _part(
        "command",
        "part_command",
        title="验证命令",
        content="ok",
        payload={
            "command": ["npm", "run", "typecheck"],
            "exit_code": 0,
            "stdout": "x" * 1400,
            "stderr": "",
        },
    )

    artifacts, changed_files = extractor.extract([command], [], [diff])

    artifact_types = {artifact.artifact_type for artifact in artifacts}
    assert {"file_change", "command_result", "test_result"}.issubset(artifact_types)
    assert changed_files[0].path == "/workspace/app.py"
    command_artifact = next(artifact for artifact in artifacts if artifact.artifact_type == "command_result")
    assert command_artifact.payload["stdout"].endswith("...")
    test_artifact = next(artifact for artifact in artifacts if artifact.artifact_type == "test_result")
    assert test_artifact.payload["passed"] is True


def test_artifact_extractor_derives_findings_risks_and_subtask_results():
    extractor = AgentArtifactExtractor()
    tasks = [
        {
            "task_id": "agt_explore",
            "agent_name": "explore",
            "status": "completed",
            "child_status": "completed",
            "result": {"summary": "关键发现：入口在 /workspace/src/app.py。结论：结构清晰。"},
            "updated_at": "2026-01-01T00:00:00",
        },
        {
            "task_id": "agt_review",
            "agent_name": "review",
            "status": "completed",
            "child_status": "completed",
            "result": {"summary": "有条件通过。风险列表：缺少回归测试。验证建议：运行 npm test。"},
            "updated_at": "2026-01-01T00:00:00",
        },
        {
            "task_id": "agt_other",
            "agent_name": "custom",
            "status": "completed",
            "child_status": "completed",
            "result": {"summary": "custom done"},
            "updated_at": "2026-01-01T00:00:00",
        },
    ]

    artifacts, _ = extractor.extract([], tasks, [])

    artifact_types = [artifact.artifact_type for artifact in artifacts]
    assert "findings" in artifact_types
    assert "risks" in artifact_types
    assert "subtask_result" in artifact_types
    findings = next(artifact for artifact in artifacts if artifact.artifact_type == "findings")
    assert findings.payload["items"][0]["files"] == ["/workspace/src/app.py"]
    risks = next(artifact for artifact in artifacts if artifact.artifact_type == "risks")
    assert risks.payload["verdict"] == "conditional"
    assert risks.payload["items"][0]["severity"] == "low"
