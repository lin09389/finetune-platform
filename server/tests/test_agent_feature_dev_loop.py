from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path

from agent_runtime.actions import WorkflowActionService
from agent_runtime.definitions import RuntimeExecutionContext
from agent_runtime.repository import WorkflowRuntimeRepository
from agent_runtime.tool_loop import AgentToolLoop
from agent_runtime.tools import AgentToolExecutor


def _workspace_root() -> Path:
    cwd = Path.cwd().resolve()
    return cwd.parent if cwd.name == "server" else cwd


def _make_runtime(tmp_path: Path):
    repository = WorkflowRuntimeRepository(str(tmp_path / "feature_loop.db"))
    action_service = WorkflowActionService(repository)
    executor = AgentToolExecutor(repository, action_service)
    workspace = _workspace_root()
    project = repository.create_project(
        {
            "title": "feature dev loop",
            "goal": "完成一个小功能改动并运行验证",
            "template_id": "software_delivery",
            "project_path": str(workspace),
            "provider": "mock",
            "model": None,
            "approval_mode": "manual",
        }
    )
    task = repository.create_task(project["id"], "implementer", "实现", "实现功能", "running", step_key="implement")
    return repository, executor, workspace, project, task


def _diff(path: str, old: str, new: str) -> str:
    return f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-{old}\n+{new}\n"


def _multi_diff(changes: list[tuple[str, str, str]]) -> str:
    return "".join(_diff(path, old, new) for path, old, new in changes)


def test_feature_loop_multi_file_diff_requires_approval_after_context(tmp_path: Path):
    repository, executor, workspace, project, task = _make_runtime(tmp_path)
    feature_dir = workspace / "tmp" / f"feature-loop-{uuid.uuid4().hex[:8]}"
    feature_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "feature_a.ts": "export const A = 'old';\n",
        "feature_b.ts": "export const B = 'old';\n",
        "feature_c.ts": "export const C = 'old';\n",
        "feature_d.ts": "export const D = 'old';\n",
    }
    for name, content in files.items():
        (feature_dir / name).write_text(content, encoding="utf-8")
    rels = [(feature_dir / name).relative_to(workspace).as_posix() for name in files]
    responses = iter(
        [
            {"tool": "inspect_project", "arguments": {}},
            {"tool": "detect_project_commands", "arguments": {}},
            {"tool": "read_file", "arguments": {"path": rels[0]}},
            {"tool": "read_file", "arguments": {"path": rels[1]}},
            {"tool": "read_file", "arguments": {"path": rels[2]}},
            {"tool": "read_file", "arguments": {"path": rels[3]}},
            {
                "tool": "propose_patch",
                "arguments": {
                    "title": "四文件功能改动",
                    "payload": {
                        "format": "unified_diff",
                        "diff": _multi_diff([(rel, "export const " + chr(65 + i) + " = 'old';", "export const " + chr(65 + i) + " = 'new';") for i, rel in enumerate(rels)]),
                    },
                },
            },
            {
                "tool": "finalize",
                "arguments": {
                    "summary": "已生成四文件功能补丁，等待审批后执行。",
                    "changed_files": rels,
                    "verification": "未运行，等待补丁审批。",
                    "risks": ["多文件源码改动需要人工审批。"],
                    "next_action": "请审批补丁后运行验证。",
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
                step_input={"agent": {"system_prompt": "实现", "max_iterations": 10}, "step": {"step_key": "implement"}},
                project=project,
                task=task,
                model_call=model_call,
            )
        )

        action = next(item for item in repository.list_action_proposals(project["id"]) if item["action_type"] == "patch")
        assert response.output.summary == "已生成四文件功能补丁，等待审批后执行。"
        assert action["status"] == "pending_approval"
        assert action["execution_mode"] == "approval_required"
        assert action["risk_level"] == "medium"
        assert "多文件源码 diff" in action["policy_reason"]
    finally:
        shutil.rmtree(feature_dir, ignore_errors=True)


def test_feature_patch_requires_related_context_before_action(tmp_path: Path):
    repository, executor, workspace, project, task = _make_runtime(tmp_path)
    feature_dir = workspace / "tmp" / f"feature-context-{uuid.uuid4().hex[:8]}"
    feature_dir.mkdir(parents=True, exist_ok=True)
    first = feature_dir / "FeaturePanel.tsx"
    second = feature_dir / "FeaturePanel.css"
    first.write_text("export const title = 'old';\n", encoding="utf-8")
    second.write_text(".title { color: red; }\n", encoding="utf-8")
    first_rel = first.relative_to(workspace).as_posix()
    second_rel = second.relative_to(workspace).as_posix()
    responses = iter(
        [
            {"tool": "inspect_project", "arguments": {}},
            {"tool": "read_file", "arguments": {"path": first_rel}},
            {
                "tool": "propose_patch",
                "arguments": {
                    "title": "上下文不足的功能补丁",
                    "payload": {
                        "format": "unified_diff",
                        "diff": _multi_diff(
                            [
                                (first_rel, "export const title = 'old';", "export const title = 'new';"),
                                (second_rel, ".title { color: red; }", ".title { color: blue; }"),
                            ]
                        ),
                    },
                },
            },
            {"tool": "read_file", "arguments": {"path": second_rel}},
            {
                "tool": "finalize",
                "arguments": {
                    "summary": "已按系统要求补充读取相关文件。",
                    "risks": [],
                    "next_action": "重新生成补丁。",
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
                step_input={"agent": {"system_prompt": "实现", "max_iterations": 10}, "step": {"step_key": "implement"}},
                project=project,
                task=task,
                model_call=model_call,
            )
        )

        calls = repository.list_tool_calls(project["id"])
        assert response.output.summary == "已按系统要求补充读取相关文件。"
        assert calls[2]["tool_name"] == "propose_patch"
        assert calls[2]["status"] == "failed"
        assert calls[2]["result_payload"]["required_tools"] == ["search_code", "read_file"]
        assert second_rel in calls[2]["result_payload"]["missing_related_files"]
        assert repository.list_action_proposals(project["id"]) == []
    finally:
        shutil.rmtree(feature_dir, ignore_errors=True)
