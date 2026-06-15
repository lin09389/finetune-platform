from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
import uuid
from pathlib import Path

import pytest
from fastapi import BackgroundTasks

from agent_session.models import AgentPromptRequest, AgentSessionCreate
from agent_session.async_subagents import AsyncSubagentService
from agent_session.repository import AgentSessionRepository
from agent_session.service import AgentSessionService
from agent_session.deepagents_runtime import DeepAgentsSessionRunner
from agent_session.execution_context import AgentDefinition
from agent_session.agent_registry import AgentRegistry
from agent_session.runtime_contract import AgentRuntimeContract
from agent_session.runtime_factory import DeepAgentsRuntimeFactory
from agent_session.session_state_machine import AgentSessionStateMachine
from agent_session.runtime import (
    EPHEMERAL_BACKEND_ROUTES,
    FALLBACK_STATE_BACKEND_ROUTE,
    WORKSPACE_BACKEND_ROUTE,
    build_deepagents_backend,
    resolve_interrupt_on,
)


def test_runtime_contract_enforces_agent_launch_modes(tmp_path: Path):
    registry = AgentRegistry()

    with pytest.raises(ValueError, match="cannot be started directly"):
        AgentRuntimeContract.for_agent_session(
            session={"id": "session", "project_path": str(tmp_path), "agent_id": "explore", "metadata": {}},
            goal="direct subagent",
            model=object(),
            agent_registry=registry,
            tools=[],
            middleware=[],
            subagents=[],
            checkpointer=False,
        )

    contract = AgentRuntimeContract.for_agent_session(
        session={
            "id": "session",
            "project_path": str(tmp_path),
            "agent_id": "explore",
            "metadata": {"async_subagent": True},
        },
        goal="async child",
        model=object(),
        agent_registry=registry,
        tools=[],
        middleware=[],
        subagents=[],
        checkpointer=False,
    )

    assert contract.runtime_kind == "agent_session"
    assert contract.agent_id == "explore"
    assert contract.recursion_limit is not None


def test_project_chat_contract_is_readonly(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text("# rules\n", encoding="utf-8")

    contract = AgentRuntimeContract.for_project_chat(project_path=str(tmp_path), model=object())

    assert contract.runtime_kind == "project_chat"
    assert contract.backend_mode == "project_chat_readonly"
    assert contract.tools == []
    assert contract.skills is None
    assert contract.memory == ["/workspace/AGENTS.md"]
    assert "只读项目讨论助手" in contract.system_prompt


def test_runtime_factory_is_deepagents_creation_boundary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    captured: dict[str, object] = {}

    def fake_create_deep_agent(**kwargs):
        captured.update(kwargs)
        return {"graph": True}

    class FakeFilesystemPermission:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_module = type(
        "DeepAgentsModule",
        (),
        {
            "create_deep_agent": staticmethod(fake_create_deep_agent),
            "FilesystemPermission": FakeFilesystemPermission,
        },
    )
    monkeypatch.setitem(__import__("sys").modules, "deepagents", fake_module)
    monkeypatch.setattr(DeepAgentsRuntimeFactory, "_readonly_project_backend", staticmethod(lambda _project_path: object()))

    contract = AgentRuntimeContract.for_project_chat(project_path=str(tmp_path), model=object())
    graph = DeepAgentsRuntimeFactory().build(contract)

    assert graph == {"graph": True}
    assert captured["system_prompt"] == contract.system_prompt
    assert captured["checkpointer"] is False
    assert captured["tools"] == []


def test_agent_session_state_machine_clears_latches(tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    session = repository.create_session(
        {
            "agent_id": "build",
            "title": "state",
            "metadata": {
                "active_prompt_id": "prompt-1",
                "background_run": True,
                "pending_deepagents_interrupt": {"part_id": "part"},
            },
        }
    )
    machine = AgentSessionStateMachine(repository)

    running = machine.mark_running(session["id"])
    completed = machine.mark_completed(session["id"])

    assert running["status"] == "running"
    assert completed["status"] == "completed"
    assert completed["metadata"]["current_phase"] == "completed"
    assert completed["metadata"]["active_prompt_id"] is None
    assert completed["metadata"]["background_run"] is False
    assert completed["metadata"]["pending_deepagents_interrupt"] is None


def test_agent_session_deepagents_reads_file_and_completes(tmp_path: Path):
    workspace = Path.cwd() / "tmp" / f"deepagents-runtime-{uuid.uuid4().hex[:8]}"
    workspace.mkdir()
    try:
        target = workspace / "hello.txt"
        target.write_text("hello from deepagents\n", encoding="utf-8")
        service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
        session = service.create_session(AgentSessionCreate(title="deepagents prompt", project_path=str(workspace)))
        responses = iter(
            [
                json.dumps({"tool": "read_file", "arguments": {"file_path": "/workspace/hello.txt"}}, ensure_ascii=False),
                json.dumps({"type": "final", "content": "DeepAgents 已读取 hello.txt。"}, ensure_ascii=False),
            ]
        )

        async def model_call(_messages):
            return next(responses)

        service.model_call = model_call
        service.repository.update_session(
            session.id,
            metadata={
                **session.metadata,
                "active_prompt_id": "prompt-1",
                "background_run": True,
                "pending_deepagents_interrupt": {"part_id": "pending"},
                "ui_state": {"pending_permission": {"part_id": "pending"}},
            },
        )

        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="读取 hello.txt 并总结")))
        events = service.list_events(session.id)

        assert result.status == "completed"
        assert result.metadata["runtime"] == "deepagents"
        assert result.metadata["active_prompt_id"] is None
        assert result.metadata["background_run"] is False
        assert result.metadata["pending_deepagents_interrupt"] is None
        assert result.metadata["ui_state"]["pending_permission"] is None
        assert any(part.type == "summary" and "DeepAgents" in (part.content or "") for part in result.parts)
        assert any(event["event_type"] == "session_started" for event in events)
        assert any(event["event_type"] == "tool_call_completed" for event in events)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_agent_session_deepagents_edit_file_uses_official_hitl(tmp_path: Path):
    workspace = Path.cwd() / "tmp" / f"deepagents-action-{uuid.uuid4().hex[:8]}"
    workspace.mkdir()
    try:
        target = workspace / "hello.txt"
        target.write_text("hello\n", encoding="utf-8")
        service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
        session = service.create_session(AgentSessionCreate(title="deepagents action", project_path=str(workspace)))
        responses = iter(
            [
                json.dumps(
                    {
                        "tool": "edit_file",
                        "arguments": {
                            "file_path": "/workspace/hello.txt",
                            "old_string": "hello\n",
                            "new_string": "hi\n",
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"type": "final", "content": "已写入 hello.txt。"}, ensure_ascii=False),
            ]
        )

        async def model_call(_messages):
            return next(responses)

        service.model_call = model_call

        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="把 hello 改成 hi")))

        assert result.status == "waiting_approval"
        assert target.read_text(encoding="utf-8") == "hello\n"
        assert any(part.type == "permission" and part.status == "pending" for part in result.parts)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_agent_session_deepagents_execute_uses_official_hitl_without_whitelist(tmp_path: Path):
    workspace = Path.cwd() / "tmp" / f"deepagents-exec-{uuid.uuid4().hex[:8]}"
    workspace.mkdir()
    try:
        target = workspace / "cmd.txt"
        service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
        session = service.create_session(AgentSessionCreate(title="deepagents execute", project_path=str(workspace)))
        responses = iter(
            [
                json.dumps(
                    {
                        "tool": "execute",
                        "arguments": {
                            "command": "python -c \"from pathlib import Path; Path('cmd.txt').write_text('ok', encoding='utf-8')\"",
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"type": "final", "content": "命令已执行。"}, ensure_ascii=False),
            ]
        )

        async def model_call(_messages):
            return next(responses)

        service.model_call = model_call
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="运行一个命令写入 cmd.txt")))

        assert result.status == "waiting_approval"
        assert not target.exists()
        assert any(part.type == "permission" and part.status == "pending" for part in result.parts)
        assert not any(part.type == "command" for part in result.parts)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_deepagents_runtime_registers_local_async_tools(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    def fake_build_runtime(config):
        captured["tools"] = config.tools
        captured["middleware"] = config.middleware
        captured["subagents"] = config.subagents
        captured["interrupt_on"] = config.interrupt_on
        captured["project_path"] = config.project_path
        captured["permissions"] = config.permissions
        captured["system_prompt"] = config.system_prompt
        captured["skills"] = config.skills
        return object()

    monkeypatch.setattr("agent_session.deepagents_runtime.build_deep_agent_runtime", fake_build_runtime)
    monkeypatch.setattr("agent_session.deepagents_runtime._load_create_deep_agent", lambda: object())

    async def model_call(_messages):
        return json.dumps({"type": "final", "content": "ok"}, ensure_ascii=False)

    runner = DeepAgentsSessionRunner(repository=object(), notify_event=lambda *_args: None, model_call=model_call)
    graph = asyncio.run(
        runner._build_graph(
            {
                "id": "session",
                "project_path": str(tmp_path),
                "provider": "",
                "model": None,
                "metadata": {},
            },
            "测试官方内置工具链",
        )
    )

    assert graph is not None
    assert [tool.name for tool in captured["tools"]] == [
        "start_async_task",
        "check_async_task",
        "list_async_tasks",
        "update_async_task",
        "cancel_async_task",
    ]
    subagents = captured["subagents"]
    assert [item["name"] for item in subagents] == ["explore", "review"]
    assert all(item["model"] is not None for item in subagents)
    assert all(item["permissions"] for item in subagents)
    assert all(item["tools"] == [] for item in subagents)
    assert all(item["middleware"] for item in subagents)
    assert captured["interrupt_on"] is None
    assert captured["project_path"] == str(tmp_path)
    assert captured["permissions"]
    assert "/skills/builtin/" in captured["skills"]
    assert captured["middleware"] == []


def test_deepagents_runtime_enforces_agent_definition_fields(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    def fake_build_runtime(config):
        captured["middleware"] = config.middleware
        captured["subagents"] = config.subagents
        captured["system_prompt"] = config.system_prompt
        return object()

    monkeypatch.setattr("agent_session.deepagents_runtime.build_deep_agent_runtime", fake_build_runtime)
    monkeypatch.setattr("agent_session.deepagents_runtime._load_create_deep_agent", lambda: object())

    async def model_call(_messages):
        return json.dumps({"type": "final", "content": "ok"}, ensure_ascii=False)

    runner = DeepAgentsSessionRunner(repository=object(), notify_event=lambda *_args: None, model_call=model_call)
    runner.agent_registry._agents["limited"] = AgentDefinition(
        id="limited",
        name="Limited",
        mode="primary",
        system_prompt="Base prompt.",
        output_requirements="Return a concise checklist.",
        max_iterations=3,
        tools=["read_file", "grep"],
    )
    graph = asyncio.run(
        runner._build_graph(
            {
                "id": "session",
                "project_path": str(tmp_path),
                "provider": "",
                "model": None,
                "metadata": {},
                "agent_id": "limited",
            },
            "审查",
        )
    )
    config = runner._graph_config({"id": "session", "agent_id": "limited"})

    assert graph is not None
    assert config["recursion_limit"] == 20
    assert "输出要求" in captured["system_prompt"]
    assert "Return a concise checklist." in captured["system_prompt"]
    assert captured["middleware"]
    excluded = captured["middleware"][0]._excluded
    assert "write_file" in excluded
    assert "edit_file" in excluded
    assert "execute" in excluded
    assert "read_file" not in excluded
    assert "grep" not in excluded
    assert captured["subagents"] == []


def test_handoff_subagents_inherit_interrupt_policy(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    def fake_build_runtime(config):
        captured["subagents"] = config.subagents
        captured["interrupt_on"] = config.interrupt_on
        return object()

    monkeypatch.setattr("agent_session.deepagents_runtime.build_deep_agent_runtime", fake_build_runtime)
    monkeypatch.setattr("agent_session.deepagents_runtime._load_create_deep_agent", lambda: object())

    async def model_call(_messages):
        return json.dumps({"type": "final", "content": "ok"}, ensure_ascii=False)

    interrupt_on = {"write_file": False, "edit_file": True}
    runner = DeepAgentsSessionRunner(repository=object(), notify_event=lambda *_args: None, model_call=model_call)
    graph = asyncio.run(
        runner._build_graph(
            {
                "id": "session",
                "project_path": str(tmp_path),
                "provider": "",
                "model": None,
                "metadata": {"deepagents_interrupt_on": interrupt_on},
                "agent_id": "build",
            },
            "审查",
        )
    )

    assert graph is not None
    assert captured["interrupt_on"] == interrupt_on
    assert {item["name"] for item in captured["subagents"]} == {"explore", "review"}
    assert all(item["interrupt_on"] == interrupt_on for item in captured["subagents"])


def test_handoff_targets_do_not_implicitly_expose_async_tools(tmp_path: Path):
    runner = DeepAgentsSessionRunner(repository=object(), notify_event=lambda *_args: None, model_call=lambda _messages: "ok")
    runner.agent_registry._agents["handoff_only"] = AgentDefinition(
        id="handoff_only",
        name="Handoff Only",
        mode="primary",
        tools=[
            "start_async_task",
            "check_async_task",
            "list_async_tasks",
            "update_async_task",
            "cancel_async_task",
        ],
        handoff_targets=["explore"],
    )

    tools = runner._local_async_tools_for_session(
        {"id": "session", "agent_id": "handoff_only", "project_path": str(tmp_path), "metadata": {}}
    )

    assert tools == []
    assert "start_async_task" not in runner._system_prompt("handoff_only")
    assert [item["name"] for item in runner._subagents_for_agent("handoff_only", object())] == ["explore"]


def test_deepagents_system_prompt_is_composed_from_named_sections():
    runner = DeepAgentsSessionRunner(repository=object(), notify_event=lambda *_args: None, model_call=lambda _messages: "ok")
    build = runner.agent_registry.require("build")

    sections = runner._system_prompt_sections(build)
    prompt = runner._system_prompt("build")

    assert sections[0] == runner._agent_system_prompt(build)
    assert any("Finetune Platform 的代码 Agent" in section for section in sections)
    assert any("/workspace/" in section for section in sections)
    assert any("Skills 使用 DeepAgents 官方 Skills System" in section for section in sections)
    assert sections[-1].startswith("你还可以启动本地异步子代理任务")
    assert prompt == "\n\n".join(sections)


def test_agent_session_create_rejects_subagent_mode(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))

    with pytest.raises(ValueError, match="cannot be started directly"):
        service.create_session(AgentSessionCreate(agent_id="explore", title="bad direct subagent"))


def test_deepagents_runtime_rejects_direct_subagent_session(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("agent_session.deepagents_runtime._load_create_deep_agent", lambda: object())

    async def model_call(_messages):
        return json.dumps({"type": "final", "content": "ok"}, ensure_ascii=False)

    runner = DeepAgentsSessionRunner(repository=object(), notify_event=lambda *_args: None, model_call=model_call)

    with pytest.raises(ValueError, match="cannot be started directly"):
        asyncio.run(
            runner._build_graph(
                {
                    "id": "session",
                    "project_path": str(tmp_path),
                    "provider": "",
                    "model": None,
                    "metadata": {},
                    "agent_id": "explore",
                },
                "直接运行 subagent",
            )
        )


def test_deepagents_runtime_allows_async_subagent_session(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    def fake_build_runtime(config):
        captured["subagents"] = config.subagents
        captured["tools"] = config.tools
        return object()

    monkeypatch.setattr("agent_session.deepagents_runtime.build_deep_agent_runtime", fake_build_runtime)
    monkeypatch.setattr("agent_session.deepagents_runtime._load_create_deep_agent", lambda: object())

    async def model_call(_messages):
        return json.dumps({"type": "final", "content": "ok"}, ensure_ascii=False)

    runner = DeepAgentsSessionRunner(repository=object(), notify_event=lambda *_args: None, model_call=model_call)
    graph = asyncio.run(
        runner._build_graph(
            {
                "id": "session",
                "project_path": str(tmp_path),
                "provider": "",
                "model": None,
                "metadata": {"async_subagent": True},
                "agent_id": "explore",
            },
            "作为子代理运行",
        )
    )

    assert graph is not None
    assert captured["subagents"] == []
    assert captured["tools"] == []


def test_deepagents_runtime_rejects_skill_requiring_denied_agent_tool(monkeypatch, tmp_path: Path):
    project = tmp_path / "project"
    skill_dir = project / ".deepagents" / "skills" / "shell-helper"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: shell-helper\ndescription: Needs shell access.\nallowed-tools: execute\n---\n# Shell Helper\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("agent_session.deepagents_runtime._load_create_deep_agent", lambda: object())

    async def model_call(_messages):
        return json.dumps({"type": "final", "content": "ok"}, ensure_ascii=False)

    runner = DeepAgentsSessionRunner(repository=object(), notify_event=lambda *_args: None, model_call=model_call)
    runner.agent_registry._agents["limited"] = AgentDefinition(
        id="limited",
        name="Limited",
        mode="primary",
        system_prompt="Base prompt.",
        max_iterations=3,
        tools=["read_file"],
    )

    with pytest.raises(ValueError, match="shell-helper requires execute"):
        asyncio.run(
            runner._build_graph(
                {
                    "id": "session",
                    "project_path": str(project),
                    "provider": "",
                    "model": None,
                    "metadata": {"enabled_skill_sources": ["/skills/project-deepagents/"]},
                    "agent_id": "limited",
                },
                "使用技能",
            )
        )


def test_agent_session_repository_persists_async_subtasks(tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    parent = repository.create_session({"agent_id": "build", "title": "parent"})
    child = repository.create_session({"agent_id": "explore", "title": "child"})

    task = repository.create_subtask(
        {
            "parent_session_id": parent["id"],
            "child_session_id": child["id"],
            "agent_name": "explore",
            "status": "running",
            "input_json": {"description": "inspect code"},
        }
    )
    updated = repository.update_subtask(task["id"], status="completed", result_json={"summary": "done"})
    event = repository.add_subtask_event(
        task["id"],
        parent["id"],
        "completed",
        "done",
        child_session_id=child["id"],
        status="completed",
        payload={"summary": "done"},
    )

    assert updated["input_json"]["description"] == "inspect code"
    assert updated["result_json"]["summary"] == "done"
    assert repository.get_subtask(task["id"])["status"] == "completed"
    assert [item["id"] for item in repository.list_subtasks(parent["id"])] == [task["id"]]
    assert repository.list_subtasks(parent["id"], "running") == []
    assert repository.list_subtask_events(task["id"])[0]["payload"]["summary"] == "done"
    assert repository.list_parent_subtask_events(parent["id"])[0]["id"] == event["id"]
    assert repository.summarize_subtask_metrics(parent["id"])["event_count"] == 1


def test_local_async_subtask_start_check_and_list(monkeypatch, tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    parent = repository.create_session({"agent_id": "build", "title": "parent", "project_path": str(tmp_path)})
    runner = DeepAgentsSessionRunner(
        repository=repository,
        notify_event=lambda *_args: None,
        model_call=lambda _messages: "ok",
    )
    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return object()

    monkeypatch.setattr("agent_session.deepagents_runtime.asyncio.create_task", fake_create_task)

    result = asyncio.run(runner.start_async_subtask(parent["id"], "Explore", "inspect code"))
    task = repository.get_subtask(result["task_id"])
    child = repository.get_session(result["child_session_id"])
    listed = runner.list_async_subtasks(parent["id"])

    assert result["status"] == "running"
    assert result["health_status"] == "waiting"
    assert result["diagnostics"]["last_event_type"] == "scheduled"
    assert task["agent_name"] == "explore"
    assert child["agent_id"] == "explore"
    assert scheduled
    assert listed["tasks"][0]["task_id"] == result["task_id"]
    assert runner.check_async_subtask(parent["id"], result["task_id"])["status"] == "running"
    assert runner.list_async_subtask_events(parent["id"], result["task_id"])[-1]["event_type"] == "scheduled"
    assert runner.get_async_subtask_metrics(parent["id"])["total"] == 1
    assert any(part["payload"].get("agent_role") == "async_subagent" for part in repository.list_parts(parent["id"]))


def test_local_async_subtask_rejects_non_subagent_target(tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    parent = repository.create_session({"agent_id": "build", "title": "parent", "project_path": str(tmp_path)})
    runner = DeepAgentsSessionRunner(
        repository=repository,
        notify_event=lambda *_args: None,
        model_call=lambda _messages: "ok",
    )

    with pytest.raises(ValueError, match="Unknown async subagent type"):
        asyncio.run(runner.start_async_subtask(parent["id"], "build", "bad target"))

    with pytest.raises(ValueError, match="description is required"):
        asyncio.run(runner.start_async_subtask(parent["id"], "explore", " "))


def test_local_async_subtask_refresh_keeps_waiting_permission_running(tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    parent = repository.create_session({"agent_id": "build", "title": "parent", "project_path": str(tmp_path)})
    child = repository.create_session(
        {
            "agent_id": "explore",
            "title": "child",
            "project_path": str(tmp_path),
            "status": "waiting_permission",
            "metadata": {"ui_state": {"pending_permission": {"part_id": "part_permission", "actions": []}}},
        }
    )
    task = repository.create_subtask(
        {
            "parent_session_id": parent["id"],
            "child_session_id": child["id"],
            "agent_name": "explore",
            "status": "running",
            "input_json": {"description": "inspect code"},
        }
    )
    runner = DeepAgentsSessionRunner(
        repository=repository,
        notify_event=lambda *_args: None,
        model_call=lambda _messages: "ok",
    )

    result = runner.check_async_subtask(parent["id"], task["id"])

    assert result["status"] == "running"
    assert result["result"]["child_status"] == "waiting_permission"
    parent_event = repository.list_events(parent["id"])[-1]
    assert parent_event["event_type"] == "async_subtask_waiting_permission"
    assert parent_event["payload"]["child_status"] == "waiting_permission"
    assert parent_event["payload"]["has_pending_permission"] is True
    assert parent_event["payload"]["pending_permission_part_id"] == "part_permission"


def test_local_async_subtask_completion_writes_parent_summary(monkeypatch, tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    parent = repository.create_session({"agent_id": "build", "title": "parent", "project_path": str(tmp_path)})
    child = repository.create_session(
        {"agent_id": "explore", "title": "child", "project_path": str(tmp_path), "status": "running"}
    )
    task = repository.create_subtask(
        {
            "parent_session_id": parent["id"],
            "child_session_id": child["id"],
            "agent_name": "explore",
            "status": "running",
            "input_json": {"description": "inspect code"},
        }
    )

    async def fake_run_prompt(self, session_id, prompt, *, context_files=None):
        self.repository.add_part(session_id, "summary", status="completed", title="Final", content="探索完成", payload={})
        return self.repository.update_session(session_id, status="completed", metadata={})

    monkeypatch.setattr(DeepAgentsSessionRunner, "run_prompt", fake_run_prompt)
    emitted = []
    service = AsyncSubagentService(
        repository,
        notify_event=lambda _session_id, event: emitted.append(event),
        model_call=lambda _messages: "ok",
    )

    asyncio.run(service._run_task(task["id"], child["id"], "inspect code"))
    updated = repository.get_subtask(task["id"])
    parent_parts = repository.list_parts(parent["id"])

    assert updated["status"] == "completed"
    assert updated["result_json"]["summary"] == "探索完成"
    assert service.task_events(parent["id"], task["id"])[-1]["event_type"] == "completed"
    assert parent_parts[-1]["payload"]["agent_role"] == "async_subagent"
    assert parent_parts[-1]["payload"]["async_status"] == "completed"
    assert parent_parts[-1]["payload"]["child_status"] == "completed"
    assert parent_parts[-1]["payload"]["has_pending_permission"] is False
    assert emitted[-1]["event_type"] == "async_subtask_completed"


def test_async_subagent_service_cancel_prevents_stale_child_completion(monkeypatch, tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    parent = repository.create_session({"agent_id": "build", "title": "parent", "project_path": str(tmp_path)})
    service = AsyncSubagentService(repository, notify_event=lambda *_args: None, model_call=lambda _messages: "ok")

    def fake_create_task(coro):
        coro.close()
        return object()

    monkeypatch.setattr("agent_session.async_subagents.asyncio.create_task", fake_create_task)
    result = asyncio.run(service.start_task(parent["id"], "explore", "inspect code"))
    task_id = result["task_id"]
    child_id = result["child_session_id"]

    cancelled = asyncio.run(service.cancel_task(parent["id"], task_id, "stop it"))
    asyncio.run(service._run_task(task_id, child_id, "inspect code"))
    updated = repository.get_subtask(task_id)

    assert cancelled["status"] == "cancelled"
    assert updated["status"] == "cancelled"
    assert service.task_events(parent["id"], task_id)[-1]["event_type"] == "stale_child_ignored"
    assert repository.get_session(child_id)["status"] == "interrupted"


def test_async_subagent_child_inherits_runtime_context_without_latches(monkeypatch, tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    parent = repository.create_session(
        {
            "agent_id": "build",
            "title": "parent",
            "project_path": str(tmp_path),
            "provider": "openai",
            "model": "gpt-test",
            "metadata": {
                "autonomy_mode": "manual",
                "deepagents_interrupt_on": {"write_file": False, "edit_file": True},
                "enabled_skill_sources": ["/skills/project-deepagents/"],
                "memory_user_id": "memory-alice",
                "org_id": "org-1",
                "user_id": "alice",
                "active_prompt_id": "prompt-parent",
                "background_run": True,
                "pending_deepagents_interrupt": {"tool": "edit_file"},
                "ui_state": {"pending_permission": {"part_id": "permission-parent"}},
            },
        }
    )
    service = AsyncSubagentService(repository, notify_event=lambda *_args: None, model_call=lambda _messages: "ok")

    def fake_create_task(coro):
        coro.close()
        return object()

    monkeypatch.setattr("agent_session.async_subagents.asyncio.create_task", fake_create_task)
    started = asyncio.run(service.start_task(parent["id"], "explore", "inspect code"))
    child = repository.get_session(started["child_session_id"])
    metadata = child["metadata"]

    assert child["provider"] == "openai"
    assert child["model"] == "gpt-test"
    assert metadata["autonomy_mode"] == "manual"
    assert metadata["deepagents_interrupt_on"] == {"write_file": False, "edit_file": True}
    assert metadata["enabled_skill_sources"] == ["/skills/project-deepagents/"]
    assert metadata["memory_user_id"] == "memory-alice"
    assert metadata["org_id"] == "org-1"
    assert metadata["user_id"] == "alice"
    assert metadata["parent_session_id"] == parent["id"]
    assert metadata["async_subagent"] is True
    assert "active_prompt_id" not in metadata
    assert "background_run" not in metadata
    assert "pending_deepagents_interrupt" not in metadata
    assert "ui_state" not in metadata


def test_async_subagent_service_update_restarts_same_task(monkeypatch, tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    parent = repository.create_session({"agent_id": "build", "title": "parent", "project_path": str(tmp_path)})
    service = AsyncSubagentService(repository, notify_event=lambda *_args: None, model_call=lambda _messages: "ok")

    def fake_create_task(coro):
        coro.close()
        return object()

    monkeypatch.setattr("agent_session.async_subagents.asyncio.create_task", fake_create_task)
    started = asyncio.run(service.start_task(parent["id"], "explore", "inspect code"))
    restarted = asyncio.run(service.update_task(parent["id"], started["task_id"], "inspect again"))

    assert restarted["task_id"] == started["task_id"]
    assert restarted["child_session_id"] != started["child_session_id"]
    assert restarted["restart_count"] == 1
    assert restarted["previous_child_session_ids"] == [started["child_session_id"]]
    assert restarted["input"]["description"] == "inspect again"
    assert repository.get_session(started["child_session_id"])["status"] == "interrupted"


def test_async_subagent_service_recovers_running_tasks(monkeypatch, tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    parent = repository.create_session({"agent_id": "build", "title": "parent", "project_path": str(tmp_path)})
    child = repository.create_session({"agent_id": "explore", "title": "child", "project_path": str(tmp_path), "status": "running"})
    task = repository.create_subtask(
        {
            "parent_session_id": parent["id"],
            "child_session_id": child["id"],
            "agent_name": "explore",
            "status": "running",
            "input_json": {"description": "inspect code", "subagent_type": "explore", "revision": 1},
        }
    )
    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return object()

    monkeypatch.setattr("agent_session.async_subagents.asyncio.create_task", fake_create_task)
    service = AsyncSubagentService(repository, notify_event=lambda *_args: None, model_call=lambda _messages: "ok")
    result = asyncio.run(service.recover_running_tasks())

    assert result["scheduled"] == 1
    assert scheduled
    assert repository.get_subtask(task["id"])["status"] == "running"


def test_deepagents_backend_routes_internal_files_to_state_backend(tmp_path: Path):
    from deepagents.backends import CompositeBackend, LocalShellBackend, StateBackend

    backend = build_deepagents_backend(str(tmp_path))

    assert isinstance(backend, CompositeBackend)
    assert isinstance(backend.default, LocalShellBackend)
    assert isinstance(backend.routes[WORKSPACE_BACKEND_ROUTE], LocalShellBackend)
    for route in EPHEMERAL_BACKEND_ROUTES:
        assert isinstance(backend.routes[route], StateBackend)
    assert isinstance(backend.routes[FALLBACK_STATE_BACKEND_ROUTE], StateBackend)


def test_deepagents_runtime_resolves_optional_interrupt_config():
    assert resolve_interrupt_on({}) is None
    assert resolve_interrupt_on({"deepagents_interrupt_on": True}) == {"write_file": True, "edit_file": True, "execute": True}
    custom = {"write_file": False, "edit_file": True}
    assert resolve_interrupt_on({"deepagents_interrupt_on": custom}) == custom


def test_agent_session_deepagents_interrupt_creates_permission_card(tmp_path: Path):
    workspace = Path.cwd() / "tmp" / f"deepagents-hitl-{uuid.uuid4().hex[:8]}"
    workspace.mkdir()
    try:
        target = workspace / "hello.txt"
        target.write_text("hello\n", encoding="utf-8")
        service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
        session = service.create_session(AgentSessionCreate(title="deepagents hitl", project_path=str(workspace)))
        responses = iter(
            [
                json.dumps(
                    {
                        "tool": "edit_file",
                        "arguments": {
                            "file_path": "/workspace/hello.txt",
                            "old_string": "hello\n",
                            "new_string": "hi\n",
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"type": "final", "content": "已完成。"}, ensure_ascii=False),
            ]
        )

        async def model_call(_messages):
            return next(responses)

        service.model_call = model_call
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="把 hello 改成 hi")))

        assert result.status == "waiting_approval"
        permission = next(part for part in result.parts if part.type == "permission")
        assert permission.status == "pending"
        assert permission.payload["official_hitl"] is True
        assert permission.payload["tool"] == "edit_file"
        assert target.read_text(encoding="utf-8") == "hello\n"

        completed = asyncio.run(service.approve_permission_async(permission.id, True))

        assert completed.status == "completed"
        assert target.read_text(encoding="utf-8") == "hi\n"
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_agent_session_permission_resume_is_queued_for_http_approval(tmp_path: Path):
    workspace = Path.cwd() / "tmp" / f"deepagents-background-hitl-{uuid.uuid4().hex[:8]}"
    workspace.mkdir()
    try:
        target = workspace / "hello.txt"
        target.write_text("hello\n", encoding="utf-8")
        service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
        session = service.create_session(AgentSessionCreate(title="deepagents background hitl", project_path=str(workspace)))

        responses = iter(
            [
                json.dumps(
                    {
                        "tool": "edit_file",
                        "arguments": {
                            "file_path": "/workspace/hello.txt",
                            "old_string": "hello\n",
                            "new_string": "hi\n",
                        },
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"type": "final", "content": "已完成。"}, ensure_ascii=False),
            ]
        )

        async def model_call(_messages):
            return next(responses)

        service.model_call = model_call
        result = asyncio.run(service.prompt(session.id, AgentPromptRequest(content="把 hello 改成 hi")))
        permission = next(part for part in result.parts if part.type == "permission")

        background_tasks = BackgroundTasks()
        queued = service.start_permission_resume_background(
            permission.id,
            [{"type": "approve"}],
            background_tasks,
        )

        assert queued.status == "running"
        assert target.read_text(encoding="utf-8") == "hello\n"
        assert len(background_tasks.tasks) == 1

        asyncio.run(background_tasks())

        completed = service.get_session(session.id)
        assert completed.status == "completed"
        assert target.read_text(encoding="utf-8") == "hi\n"
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_agent_session_permission_background_resume_failure_is_recorded(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(AgentSessionCreate(title="resume failure", project_path=str(Path.cwd())))
    service.repository.update_session(
        session.id,
        provider="mock",
        model="mock-model",
        metadata={
            "runtime": "deepagents",
            "active_prompt_id": "prompt-1",
            "background_run": True,
            "pending_deepagents_interrupt": {"part_id": "pending"},
            "ui_state": {"pending_permission": {"part_id": "pending"}},
        },
    )
    part = service.repository.add_part(
        session.id,
        "permission",
        status="pending",
        title="Confirm tool",
        content="Confirm tool",
        payload={
            "official_hitl": True,
            "action_requests": [{"name": "edit_file", "args": {"file_path": "/a.py"}}],
            "actions": [{"name": "edit_file", "args": {"file_path": "/a.py"}, "allowed_decisions": ["approve", "reject"]}],
        },
    )

    async def failing_resume(_session_id, _decision):
        raise RuntimeError("resume exploded")

    service.deepagents_runner.resume = failing_resume
    queued = asyncio.run(service.decide_permission_async(part["id"], [{"type": "approve"}]))
    assert queued.status == "needs_manual_review"

    failed = service.get_session(session.id)
    assert failed.status == "needs_manual_review"
    assert failed.metadata["active_prompt_id"] is None
    assert failed.metadata["background_run"] is False
    assert failed.metadata["pending_deepagents_interrupt"] is None
    assert failed.metadata["ui_state"]["pending_permission"] is None
    assert any(part.type == "summary" and "resume exploded" in part.content for part in failed.parts)


def test_agent_session_prompt_background_failure_fallback_marks_terminal(tmp_path: Path, caplog):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(AgentSessionCreate(title="prompt fallback", project_path=str(Path.cwd())))
    service.repository.update_session(session.id, status="running", metadata={"runtime": "deepagents", "active_prompt_id": "prompt-1"})

    async def failing_prompt(_session_id, _request):
        raise RuntimeError("prompt exploded")

    def failing_record(_session_id, _exc):
        raise RuntimeError("database locked")

    service.prompt = failing_prompt
    service.record_prompt_failure = failing_record

    caplog.set_level("ERROR")
    asyncio.run(service._run_prompt_background(session.id, AgentPromptRequest(content="run"), "prompt-1"))

    failed = service.get_session(session.id)
    assert failed.status == "needs_manual_review"
    assert "prompt exploded" in failed.metadata["latest_error"]
    assert any("Failed to record Agent background failure" in record.message for record in caplog.records)


def test_agent_session_stale_background_prompt_is_ignored(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(AgentSessionCreate(title="stale prompt", project_path=str(Path.cwd())))
    service.repository.update_session(
        session.id,
        status="running",
        metadata={"runtime": "deepagents", "active_prompt_id": "prompt-new", "background_run": True},
    )
    called = False

    async def stale_prompt(_session_id, _request):
        nonlocal called
        called = True
        raise RuntimeError("stale prompt should not run")

    service.prompt = stale_prompt
    asyncio.run(service._run_prompt_background(session.id, AgentPromptRequest(content="run"), "prompt-old"))

    current = service.get_session(session.id)
    assert called is False
    assert current.status == "running"
    assert current.metadata["active_prompt_id"] == "prompt-new"
    assert current.metadata.get("latest_error") in {None, ""}


def test_agent_session_background_failure_fallback_retries_locked_writes(tmp_path: Path, monkeypatch):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(AgentSessionCreate(title="locked fallback", project_path=str(Path.cwd())))
    service.repository.update_session(session.id, status="running", metadata={"runtime": "deepagents"})
    attempts = {"count": 0}
    original_update_session = service.repository.update_session

    def flaky_update_session(session_id: str, **updates):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise sqlite3.OperationalError("database is locked")
        return original_update_session(session_id, **updates)

    monkeypatch.setattr(service.repository, "update_session", flaky_update_session)

    service._record_background_failure_fallback(session.id, RuntimeError("prompt exploded"), RuntimeError("record failed"))

    failed = service.get_session(session.id)
    assert attempts["count"] >= 2
    assert failed.status == "needs_manual_review"
    assert "prompt exploded" in failed.metadata["latest_error"]


def test_agent_session_restart_recovery_marks_stale_running_sessions(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    running = service.create_session(AgentSessionCreate(title="stale running", project_path=str(Path.cwd())))
    completed = service.create_session(AgentSessionCreate(title="completed", project_path=str(Path.cwd())))
    service.repository.update_session(running.id, status="running", metadata={"runtime": "deepagents"})
    service.repository.update_session(completed.id, status="completed", metadata={"runtime": "deepagents"})

    recovered = service.recover_active_sessions_after_restart()

    assert recovered["recovered"] == 1
    stale = service.get_session(running.id)
    done = service.get_session(completed.id)
    assert stale.status == "needs_manual_review"
    assert stale.metadata["recovered_after_restart"] is True
    assert any(part.type == "summary" and "服务重启" in part.content for part in stale.parts)
    assert done.status == "completed"


@pytest.mark.asyncio
async def test_async_subtask_cancel_cancels_registered_task(tmp_path: Path):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    parent = repository.create_session({"agent_id": "build", "title": "parent", "status": "running", "metadata": {}})
    child = repository.create_session({"agent_id": "review", "title": "child", "status": "running", "metadata": {}})
    subtask = repository.create_subtask(
        {
            "parent_session_id": parent["id"],
            "child_session_id": child["id"],
            "agent_name": "review",
            "status": "running",
            "input_json": {"description": "review"},
        }
    )
    service = AsyncSubagentService(repository, lambda *_args: None)
    cancelled = asyncio.Event()

    async def long_running():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    task = asyncio.create_task(long_running())
    await asyncio.sleep(0)
    service._tasks[subtask["id"]] = task

    result = await service.cancel_task(parent["id"], subtask["id"])

    assert result["status"] == "cancelled"
    assert task.cancelled()
    assert cancelled.is_set()


def test_agent_session_hitl_decision_validation_accepts_edit_and_respond(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(AgentSessionCreate(title="hitl decisions", project_path=str(Path.cwd())))
    service.repository.update_session(session.id, provider=None, model=None, metadata={"runtime": "deepagents"})
    part = service.repository.add_part(
        session.id,
        "permission",
        status="pending",
        title="Confirm tools",
        content="Confirm tools",
        payload={
            "official_hitl": True,
            "action_requests": [
                {"name": "edit_file", "args": {"file_path": "/a.py"}},
                {"name": "ask_user", "args": {"question": "Color?"}},
            ],
            "actions": [
                {"name": "edit_file", "args": {"file_path": "/a.py"}, "allowed_decisions": ["approve", "edit", "reject"]},
                {"name": "ask_user", "args": {"question": "Color?"}, "allowed_decisions": ["respond", "reject"]},
            ],
        },
    )

    result = asyncio.run(
        service.decide_permission_async(
            part["id"],
            [
                {"type": "edit", "edited_action": {"name": "edit_file", "args": {"file_path": "/b.py"}}},
                {"type": "respond", "message": "Blue."},
            ],
        )
    )

    updated = next(item for item in result.parts if item.id == part["id"])
    assert updated.status == "approved"
    assert updated.payload["decisions"][0]["edited_action"]["args"]["file_path"] == "/b.py"
    assert updated.payload["decisions"][1]["message"] == "Blue."


def test_agent_session_hitl_decision_cannot_be_recorded_twice(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(AgentSessionCreate(title="hitl race", project_path=str(Path.cwd())))
    service.repository.update_session(session.id, provider=None, model=None, metadata={"runtime": "deepagents"})
    part = service.repository.add_part(
        session.id,
        "permission",
        status="pending",
        title="Confirm tool",
        content="Confirm tool",
        payload={
            "official_hitl": True,
            "action_requests": [{"name": "edit_file", "args": {"file_path": "/a.py"}}],
            "actions": [{"name": "edit_file", "args": {"file_path": "/a.py"}, "allowed_decisions": ["approve", "reject"]}],
        },
    )

    first = asyncio.run(service.decide_permission_async(part["id"], [{"type": "approve"}]))
    assert first.status == "running"

    with pytest.raises(ValueError, match="not pending"):
        asyncio.run(service.decide_permission_async(part["id"], [{"type": "approve"}]))


@pytest.mark.asyncio
async def test_agent_session_interrupt_cancels_running_prompt_task(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(AgentSessionCreate(title="interrupt task", project_path=str(Path.cwd())))
    service.repository.update_session(
        session.id,
        status="running",
        metadata={
            "runtime": "deepagents",
            "active_prompt_id": "prompt-1",
            "background_run": True,
            "pending_deepagents_interrupt": {"part_id": "pending"},
            "ui_state": {"pending_permission": {"part_id": "pending"}},
        },
    )
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def waiting_prompt(_session_id, _request):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    service.prompt = waiting_prompt
    task = asyncio.create_task(service._run_prompt_background(session.id, AgentPromptRequest(content="run"), "prompt-1"))
    await started.wait()

    interrupted = service.interrupt_session(session.id)
    await asyncio.wait_for(cancelled.wait(), timeout=2)
    await asyncio.wait_for(task, timeout=2)

    assert interrupted.status == "interrupted"
    current = service.get_session(session.id)
    assert current.status == "interrupted"
    assert current.metadata["active_prompt_id"] is None
    assert current.metadata["background_run"] is False
    assert current.metadata["pending_deepagents_interrupt"] is None
    assert current.metadata["ui_state"]["pending_permission"] is None


@pytest.mark.asyncio
async def test_agent_session_interrupt_keeps_permission_resume_interrupted(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(AgentSessionCreate(title="interrupt resume", project_path=str(Path.cwd())))
    service.repository.update_session(
        session.id,
        status="running",
        provider="mock",
        model="mock-model",
        metadata={
            "runtime": "deepagents",
            "active_prompt_id": "prompt-1",
            "background_run": True,
            "pending_deepagents_interrupt": {"part_id": "pending"},
            "ui_state": {"pending_permission": {"part_id": "pending"}},
        },
    )
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def waiting_resume(_session_id, _decision):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    service.deepagents_runner.resume = waiting_resume
    task = asyncio.create_task(service._resume_permission_background(session.id, {"decisions": [{"type": "approve"}]}))
    await started.wait()

    interrupted = service.interrupt_session(session.id)
    await asyncio.wait_for(cancelled.wait(), timeout=2)
    await asyncio.wait_for(task, timeout=2)

    assert interrupted.status == "interrupted"
    current = service.get_session(session.id)
    assert current.status == "interrupted"
    assert current.metadata["active_prompt_id"] is None
    assert current.metadata["background_run"] is False
    assert current.metadata["pending_deepagents_interrupt"] is None
    assert current.metadata["ui_state"]["pending_permission"] is None
    assert not any(part.type == "summary" and "权限审批后的 Agent 恢复执行被取消" in (part.content or "") for part in current.parts)


def test_agent_session_hitl_decision_validation_rejects_bad_batches(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(AgentSessionCreate(title="hitl decisions", project_path=str(Path.cwd())))
    service.repository.update_session(session.id, provider=None, model=None, metadata={"runtime": "deepagents"})
    part = service.repository.add_part(
        session.id,
        "permission",
        status="pending",
        title="Confirm tools",
        content="Confirm tools",
        payload={
            "official_hitl": True,
            "action_requests": [{"name": "ask_user", "args": {}}],
            "actions": [{"name": "ask_user", "args": {}, "allowed_decisions": ["respond"]}],
        },
    )

    with pytest.raises(ValueError, match="require a message"):
        asyncio.run(service.decide_permission_async(part["id"], [{"type": "respond"}]))

    with pytest.raises(ValueError, match="Expected 1 HITL decision"):
        asyncio.run(service.decide_permission_async(part["id"], [{"type": "respond", "message": "A"}, {"type": "respond", "message": "B"}]))


def test_agent_session_response_includes_deepagents_ui_state(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(AgentSessionCreate(title="ui state", project_path=str(Path.cwd())))
    service.repository.add_part(
        session.id,
        "tool_call",
        status="completed",
        title="read_file",
        content="Reading file",
        payload={"tool": "read_file", "args": {"file_path": "/workspace/a.py"}},
    )
    service.repository.add_part(
        session.id,
        "tool_result",
        status="completed",
        title="read_file result",
        content="File content",
        payload={"tool": "read_file"},
    )
    permission = service.repository.add_part(
        session.id,
        "permission",
        status="pending",
        title="Confirm edit",
        content="Confirm edit",
        payload={
            "official_hitl": True,
            "actions": [
                {
                    "name": "edit_file",
                    "args": {"file_path": "/workspace/a.py"},
                    "allowed_decisions": ["approve", "edit", "reject"],
                }
            ],
        },
    )
    service.repository.add_part(
        session.id,
        "summary",
        status="completed",
        title="Final",
        content="Done",
        payload={},
    )
    service.repository.update_session(session.id, status="waiting_approval", metadata={"runtime": "deepagents"})

    result = service.get_session(session.id)
    ui_state = result.metadata["ui_state"]

    assert [item["type"] for item in ui_state["timeline"]] == ["tool_call", "tool_result", "permission", "summary"]
    assert ui_state["pending_permission"]["part_id"] == permission["id"]
    assert ui_state["pending_permission"]["actions"][0]["name"] == "edit_file"
    assert ui_state["latest"]["permission"]["id"] == permission["id"]
    assert result.metadata["diagnostics"]["latest_action"]["id"] == permission["id"]


def test_agent_session_stream_snapshot_uses_model_stream_completed_payload(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(AgentSessionCreate(title="stream completion", project_path=str(Path.cwd())))
    part = service.repository.add_part(
        session.id,
        "text",
        status="running",
        title="AI 正在思考...",
        content="old",
        payload={"streaming": True},
    )

    snapshot = service._stream_part_snapshot(
        {"session_id": session.id, "event_type": "model_stream_completed", "created_at": "now", "message": "done"},
        {
            "session_id": session.id,
            "part_id": part["id"],
            "part_type": "text",
            "part": {**part, "status": "completed", "content": "new", "payload": {"streaming": False}},
        },
    )

    assert snapshot["status"] == "completed"
    assert snapshot["content"] == "new"
    assert snapshot["payload"]["streaming"] is False


def test_agent_session_stream_chunk_recomputes_model_stream_completion_part(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(AgentSessionCreate(title="stream chunk completion", project_path=str(Path.cwd())))
    part = service.repository.add_part(
        session.id,
        "text",
        status="running",
        title="AI 正在思考...",
        content="old",
        payload={"streaming": True},
    )
    service.repository.update_part(part["id"], status="completed", content="new", payload={"streaming": False})
    event = service.repository.add_event(
        session.id,
        "model_stream_completed",
        "done",
        {
            "session_id": session.id,
            "part_id": part["id"],
            "part_type": "text",
            "part": {**part, "status": "running", "content": "old", "payload": {"streaming": True}},
        },
    )

    chunk = service.build_stream_chunk(event)

    assert chunk["chunk_type"] == "part_complete"
    assert chunk["part"]["status"] == "completed"
    assert chunk["part"]["content"] == "new"
    assert chunk["part"]["payload"]["streaming"] is False


def test_async_subtask_metrics_uses_sql_aggregation_without_loading_all_events(tmp_path: Path, monkeypatch):
    repository = AgentSessionRepository(str(tmp_path / "agents.db"))
    parent = repository.create_session({"agent_id": "build", "title": "parent", "status": "running", "metadata": {}})
    task = repository.create_subtask(
        {
            "parent_session_id": parent["id"],
            "child_session_id": "child-1",
            "agent_name": "review",
            "status": "running",
            "input_json": {"description": "review"},
        }
    )
    repository.add_subtask_event(task["id"], parent["id"], "recovered", "Recovered")
    repository.add_subtask_event(task["id"], parent["id"], "started", "Started")

    def fail_if_full_event_load(*_args, **_kwargs):
        raise AssertionError("metrics should not load full event history")

    monkeypatch.setattr(repository, "list_parent_subtask_events", fail_if_full_event_load)

    metrics = repository.summarize_subtask_metrics(parent["id"])

    assert metrics["total"] == 1
    assert metrics["running"] == 1
    assert metrics["event_count"] == 2
    assert metrics["recovery_count"] == 1
    assert metrics["last_event"]["event_type"] == "started"


def test_agent_session_ui_state_marks_legacy_actions_read_only(tmp_path: Path):
    service = AgentSessionService(AgentSessionRepository(str(tmp_path / "agents.db")))
    session = service.create_session(AgentSessionCreate(title="legacy ui", project_path=str(Path.cwd())))
    diff = service.repository.add_part(
        session.id,
        "diff",
        status="pending",
        title="Old patch",
        content="legacy patch",
        payload={"changed_files": ["a.py"]},
    )
    command = service.repository.add_part(
        session.id,
        "command",
        status="approved",
        title="Old command",
        content="legacy command",
        payload={"command": ["pytest"]},
    )

    result = service.get_session(session.id)
    ui_state = result.metadata["ui_state"]
    items = {item["id"]: item for item in ui_state["timeline"]}

    assert items[diff["id"]]["legacy"] is True
    assert items[command["id"]]["legacy"] is True
    assert ui_state["pending_permission"] is None
    assert result.metadata["diagnostics"]["latest_action"] is None
