from __future__ import annotations

from pathlib import Path
import asyncio

from agent_runtime.actions import WorkflowActionService
from agent_runtime.repository import WorkflowRuntimeRepository
from agent_runtime.tool_loop import AgentToolLoop
from agent_runtime.tool_models import AgentToolRequest, AgentToolResult
from agent_runtime.tools import AgentToolExecutor
from agent_runtime.definitions import RuntimeExecutionContext


def _workspace_root() -> Path:
    cwd = Path.cwd().resolve()
    return cwd.parent if cwd.name == "server" else cwd


def make_runtime(tmp_path: Path):
    repository = WorkflowRuntimeRepository(str(tmp_path / "agent_tools.db"))
    action_service = WorkflowActionService(repository)
    executor = AgentToolExecutor(repository, action_service)
    project = repository.create_project(
        {
            "title": "tools",
            "goal": "使用工具修改代码",
            "template_id": "software_delivery",
            "project_path": str(_workspace_root()),
            "provider": "minimax",
            "model": None,
            "approval_mode": "manual",
        }
    )
    task = repository.create_task(
        project["id"],
        "implementer",
        "实现",
        "实现任务",
        "running",
        step_key="implement",
    )
    return repository, action_service, executor, project, task


def test_search_code_and_read_file_are_scoped_to_workspace(tmp_path):
    repository, _, executor, project, _ = make_runtime(tmp_path)
    workspace = _workspace_root()
    target = workspace / "tmp_agent_tool_runtime_test.txt"
    target.write_text("AgentRunCard tool call smoke", encoding="utf-8")
    try:
        search = executor.execute(
            AgentToolRequest(tool="search_code", arguments={"query": "tool call smoke", "path_glob": "tmp_agent_tool_runtime_test.txt"}),
            workflow_id=project["id"],
            step_id=None,
            agent_id="implementer",
            project=project,
        )
        read = executor.execute(
            AgentToolRequest(tool="read_file", arguments={"path": "tmp_agent_tool_runtime_test.txt"}),
            workflow_id=project["id"],
            step_id=None,
            agent_id="implementer",
            project=project,
        )
        blocked = executor.execute(
            AgentToolRequest(tool="read_file", arguments={"path": "../outside.txt"}),
            workflow_id=project["id"],
            step_id=None,
            agent_id="implementer",
            project=project,
        )
    finally:
        target.unlink(missing_ok=True)

    assert search.status == "completed"
    assert search.payload["matches"]
    assert read.status == "completed"
    assert "tool call smoke" in read.payload["content"]
    assert blocked.status == "failed"


def test_tool_call_list_self_heals_missing_table(tmp_path):
    repository, _, _, project, _ = make_runtime(tmp_path)
    with __import__("sqlite3").connect(repository.db_path) as conn:
        conn.execute("DROP TABLE workflow_tool_calls")

    calls = repository.list_tool_calls(project["id"])
    inserted = repository.add_tool_call(
        workflow_id=project["id"],
        step_id=None,
        agent_id="implementer",
        tool_name="inspect_project",
        arguments={},
        status="completed",
        result_summary="ok",
    )

    assert calls == []
    assert inserted["tool_name"] == "inspect_project"
    assert repository.list_tool_calls(project["id"])[0]["result_summary"] == "ok"


def test_read_file_truncates_long_content(tmp_path):
    _, _, executor, project, _ = make_runtime(tmp_path)
    workspace = _workspace_root()
    target = workspace / "tmp_agent_tool_runtime_long.txt"
    target.write_text("x" * 21000, encoding="utf-8")
    try:
        result = executor.execute(
            AgentToolRequest(tool="read_file", arguments={"path": target.name}),
            workflow_id=project["id"],
            step_id=None,
            agent_id="implementer",
            project=project,
        )
    finally:
        target.unlink(missing_ok=True)

    assert result.status == "completed"
    assert result.payload["truncated"] is True
    assert len(result.payload["content"]) == 20000


def test_propose_tools_create_action_proposals_without_execution(tmp_path):
    repository, _, executor, project, task = make_runtime(tmp_path)

    context = executor.execute(
        AgentToolRequest(tool="inspect_project", arguments={}),
        workflow_id=project["id"],
        step_id=task["id"],
        agent_id="implementer",
        project=project,
    )
    assert context.status == "completed"
    repository.add_tool_call(
        project["id"],
        task["id"],
        "implementer",
        "inspect_project",
        {},
        status="completed",
        result_summary=context.summary,
        result_payload=context.payload,
    )

    detect = executor.execute(
        AgentToolRequest(tool="detect_project_commands", arguments={}),
        workflow_id=project["id"],
        step_id=task["id"],
        agent_id="implementer",
        project=project,
    )
    assert detect.status == "completed"
    repository.add_tool_call(
        project["id"],
        task["id"],
        "implementer",
        "detect_project_commands",
        {},
        status="completed",
        result_summary=detect.summary,
        result_payload=detect.payload,
    )

    patch = executor.execute(
        AgentToolRequest(
            tool="propose_patch",
            arguments={
                "title": "写 smoke 文件",
                "payload": {"files": [{"path": "tmp_agent_tool_runtime_patch.txt", "content": "not executed"}]},
            },
        ),
        workflow_id=project["id"],
        step_id=task["id"],
        agent_id="implementer",
        project=project,
    )
    command = executor.execute(
        AgentToolRequest(
            tool="propose_command",
            arguments={"title": "类型检查", "payload": {"command": ["npm", "run", "agent-tool-runtime-test"]}},
        ),
        workflow_id=project["id"],
        step_id=task["id"],
        agent_id="implementer",
        project=project,
    )

    actions = repository.list_action_proposals(project["id"])
    assert patch.status == "completed"
    assert command.status == "completed"
    assert patch.permission_decision == "allow"
    assert command.permission_decision == "allow"
    assert {action["action_type"] for action in actions} == {"patch", "command"}
    assert {action["status"] for action in actions} == {"pending_approval"}
    assert not (_workspace_root() / "tmp_agent_tool_runtime_patch.txt").exists()


def test_reviewer_cannot_propose_patch(tmp_path):
    _, _, executor, project, task = make_runtime(tmp_path)

    result = executor.execute(
        AgentToolRequest(tool="propose_patch", arguments={"payload": {"files": []}}),
        workflow_id=project["id"],
        step_id=task["id"],
        agent_id="reviewer",
        project=project,
    )

    assert result.status == "blocked"
    assert result.permission_decision == "deny"
    assert "拒绝" in (result.blocked_reason or "")


def test_tool_loop_runs_until_finalize_and_records_calls(tmp_path):
    repository, action_service, executor, project, task = make_runtime(tmp_path)
    responses = iter(
        [
            '{"thought":"先检查项目","tool":"inspect_project","arguments":{}}',
            '{"thought":"完成","tool":"finalize","arguments":{"summary":"已完成检查","risks":[],"next_action":"请审批后继续"}}',
        ]
    )

    async def model_call(_messages):
        return next(responses)

    loop = AgentToolLoop(repository, executor)
    response = asyncio.run(loop.run(
        agent_id="implementer",
        context=RuntimeExecutionContext(workflow_id=project["id"], goal=project["goal"], project_path=str(Path.cwd()), provider="minimax"),
        step_input={"agent": {"system_prompt": "实现"}, "step": {"step_key": "implement"}},
        project=project,
        task=task,
        model_call=model_call,
    ))

    assert response.output.summary == "已完成检查"
    assert len(repository.list_tool_calls(project["id"])) == 2
    assert len(action_service.repository.list_action_proposals(project["id"])) == 0


def test_tool_loop_caps_iterations_and_parse_fail_needs_manual_review(tmp_path):
    repository, _, executor, project, task = make_runtime(tmp_path)

    async def repeated(_messages):
        return '{"thought":"继续搜索","tool":"search_code","arguments":{"query":"unlikely-query"}}'

    capped = asyncio.run(AgentToolLoop(repository, executor, max_iterations=2).run(
        agent_id="implementer",
        context=RuntimeExecutionContext(workflow_id=project["id"], goal=project["goal"], project_path=str(Path.cwd()), provider="minimax"),
        step_input={},
        project=project,
        task=task,
        model_call=repeated,
    ))

    async def broken(_messages):
        return "not json"

    parsed = asyncio.run(AgentToolLoop(repository, executor, max_iterations=2).run(
        agent_id="implementer",
        context=RuntimeExecutionContext(workflow_id=project["id"], goal=project["goal"], project_path=str(Path.cwd()), provider="minimax"),
        step_input={},
        project=project,
        task=task,
        model_call=broken,
    ))

    assert capped.output.needs_manual_review is True
    assert len(capped.tool_calls) == 2
    assert parsed.output.needs_manual_review is True


def test_tool_loop_blocks_repeated_same_tool_calls(tmp_path):
    repository, _, executor, project, task = make_runtime(tmp_path)

    async def repeated(_messages):
        return '{"thought":"继续搜索","tool":"search_code","arguments":{"query":"same"}}'

    blocked = asyncio.run(
        AgentToolLoop(repository, executor, max_iterations=6).run(
            agent_id="implementer",
            context=RuntimeExecutionContext(
                workflow_id=project["id"],
                goal=project["goal"],
                project_path=str(Path.cwd()),
                provider="minimax",
            ),
            step_input={},
            project=project,
            task=task,
            model_call=repeated,
        )
    )

    assert blocked.output.needs_manual_review is True
    events = repository.list_events(project["id"])
    assert any(item["event_type"] == "tool_loop_blocked" for item in events)


def test_tool_loop_can_delegate_subagent(tmp_path):
    repository, _, executor, project, task = make_runtime(tmp_path)
    responses = iter(
        [
            '{"thought":"委派 explore","tool":"delegate_agent","arguments":{"agent_id":"explore","task":"定位相关文件"}}',
            '{"thought":"完成","tool":"finalize","arguments":{"summary":"已委派 explore 并收集结果","risks":[],"next_action":"继续"}}',
        ]
    )

    async def model_call(_messages):
        return next(responses)

    async def delegate_call(_parent_agent_id, arguments, _context, _step_input):
        return AgentToolResult(
            tool="delegate_agent",
            status="completed",
            summary="子 Agent explore 已完成委派任务",
            payload={"agent_id": arguments["agent_id"], "output": {"summary": "found files"}},
            permission_decision="allow",
        )

    loop = AgentToolLoop(repository, executor)
    response = asyncio.run(
        loop.run(
            agent_id="implementer",
            context=RuntimeExecutionContext(
                workflow_id=project["id"],
                goal=project["goal"],
                project_path=str(Path.cwd()),
                provider="minimax",
            ),
            step_input={
                "agent": {"system_prompt": "实现", "handoff_targets": ["explore"]},
                "available_subagents": [{"id": "explore", "name": "Explore"}],
            },
            project=project,
            task=task,
            model_call=model_call,
            delegate_call=delegate_call,
        )
    )

    assert response.output.summary == "已委派 explore 并收集结果"
    assert any(item.tool == "delegate_agent" for item in response.tool_calls)


def test_delegate_agent_executor_requires_runtime_delegate_path(tmp_path):
    _, _, executor, project, task = make_runtime(tmp_path)

    result = executor.execute(
        AgentToolRequest(tool="delegate_agent", arguments={"agent_id": "explore", "task": "定位相关文件"}),
        workflow_id=project["id"],
        step_id=task["id"],
        agent_id="implementer",
        project=project,
    )

    assert result.status == "failed"
    assert result.payload["runtime_delegate_required"] is True
    assert result.payload["agent_id"] == "explore"
    assert result.payload["task"] == "定位相关文件"
