from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Sequence

from pydantic import BaseModel, Field
from langgraph.types import Command

from .agent_registry import AgentRegistry
from .async_subagents import AsyncSubagentService
from .deepagents_compat import patch_torch_pytree_for_transformers
from .deepagents_events import DeepAgentsEventMapper
from .execution_context import AgentDefinition, RuntimeExecutionContext
from .deepagents_checkpoint import get_checkpoint_db_path
from .model_adapter import get_chat_model
from .permission import permission_policy_for_agent
from .runtime import (
    DeepAgentRuntimeConfig,
    build_deep_agent_runtime,
    memory_files_for_project,
    resolve_enabled_skill_sources,
)
from .state import ensure_session_state, set_phase

logger = logging.getLogger(__name__)

DEEPAGENTS_BUILTIN_TOOLS = frozenset(
    {
        "write_todos",
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "glob",
        "grep",
        "execute",
        "task",
    }
)
LOCAL_ASYNC_TOOL_NAMES = frozenset(
    {
        "start_async_task",
        "check_async_task",
        "list_async_tasks",
        "update_async_task",
        "cancel_async_task",
    }
)

PLATFORM_IDENTITY_PROMPT = "你是 Finetune Platform 的代码 Agent。你需要先理解项目，再使用工具完成任务。"
FILESYSTEM_PROMPT = (
    "文件操作使用 DeepAgents harness 内置的 ls/read_file/glob/grep/write_file/edit_file。"
    "项目文件位于 `/workspace/`；DeepAgents 内部文件和上下文文件位于状态后端，"
    "包括 /context/、/large_tool_results/ 和 /conversation_history/。"
    "长期记忆位于 `/memories/`，Agent 自身记忆位于 `/agent-memory/`，"
    "组织策略位于只读的 `/policies/`。"
    "读取或修改项目文件时必须使用 `/workspace/...` 路径。"
)
CONTEXT_PROMPT = (
    "用户当前任务相关的大上下文会作为 /context/ 下的虚拟文件传入，"
    "你需要按需读取 /context/task.md、/context/editor/active-file.md、"
    "/context/mentions/ 或 /context/retrieval/ 下的文件，"
    "不要把这些文件完整复述给用户。"
)
SKILLS_PROMPT = (
    "Skills 使用 DeepAgents 官方 Skills System 加载；你需要先依据 skills 列表匹配任务，"
    "只在适用时读取对应 SKILL.md 和其中引用的附属文件，不要把全部 skill 内容塞进主上下文。"
)
EXECUTION_PROMPT = (
    "需要运行测试、安装依赖或调用 CLI 时，直接使用官方 sandbox execute 工具；"
    "命令不需要平台白名单审批。"
    "执行命令前优先说明意图，执行后根据 execute 输出继续判断。"
)

class StartAsyncTaskInput(BaseModel):
    subagent_type: str = Field(
        description="The async subagent type to run. Use one of the available subagent names."
    )
    description: str = Field(description="Detailed task instructions for the async subagent.")


class CheckAsyncTaskInput(BaseModel):
    task_id: str = Field(description="The exact task_id returned by start_async_task.")


class ListAsyncTasksInput(BaseModel):
    status_filter: str | None = Field(
        default=None,
        description="Optional status filter: running, completed, failed, pending, or all.",
    )


class UpdateAsyncTaskInput(BaseModel):
    task_id: str = Field(description="The exact task_id returned by start_async_task.")
    description: str = Field(description="New task instructions. Updating restarts the async subagent task.")


class CancelAsyncTaskInput(BaseModel):
    task_id: str = Field(description="The exact task_id returned by start_async_task.")
    reason: str | None = Field(default=None, description="Optional cancellation reason.")


class DeepAgentsUnavailable(RuntimeError):
    pass


def deepagents_thread_id(session_id: str) -> str:
    return f"agent_session:{session_id}:deepagents"


def _load_create_deep_agent() -> Any:
    try:
        patch_torch_pytree_for_transformers()
        from deepagents import create_deep_agent
    except Exception as exc:  # pragma: no cover - depends on optional runtime dependency
        raise DeepAgentsUnavailable(f"DeepAgents is not installed or failed to import: {exc}") from exc
    return create_deep_agent


class CallableToolCallingChatModel:
    """Small adapter used by tests and injected model_call hooks."""

    def __init__(self, model_call: Any, *, bound_tools: list[dict[str, Any]] | None = None):
        from langchain_core.language_models.chat_models import BaseChatModel

        class _Model(BaseChatModel):
            model_call: Any
            bound_tools: list[dict[str, Any]] = []

            @property
            def _llm_type(self) -> str:
                return "agent-session-callable"

            def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Any:
                from langchain_core.utils.function_calling import convert_to_openai_tool

                _ = kwargs
                return self.model_copy(update={"bound_tools": [convert_to_openai_tool(tool) for tool in tools]})

            async def _agenerate(self, messages: list[Any], stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any) -> Any:
                from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
                from langchain_core.outputs import ChatGeneration, ChatResult

                _ = stop, run_manager, kwargs
                converted: list[dict[str, str]] = []
                for message in messages:
                    role = "user"
                    if isinstance(message, AIMessage):
                        role = "assistant"
                    elif isinstance(message, SystemMessage):
                        role = "system"
                    elif isinstance(message, HumanMessage):
                        role = "user"
                    elif isinstance(message, ToolMessage):
                        role = "tool"
                    content = message.content if isinstance(message.content, str) else json.dumps(message.content, ensure_ascii=False)
                    converted.append({"role": role, "content": content})

                if converted and converted[-1]["role"] == "assistant" and not converted[-1]["content"].strip():
                    converted.pop()

                raw = await self.model_call(converted)
                return ChatResult(generations=[ChatGeneration(message=self._to_ai_message(str(raw)))])

            def _generate(self, messages: list[Any], stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any) -> Any:
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    return asyncio.run(self._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs))
                raise RuntimeError("CallableToolCallingChatModel only supports async invocation in a running event loop")

            def _to_ai_message(self, content: str) -> Any:
                from langchain_core.messages import AIMessage

                cleaned = content.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.strip("`")
                    if cleaned.startswith("json"):
                        cleaned = cleaned[4:].strip()
                try:
                    parsed = json.loads(cleaned)
                except json.JSONDecodeError:
                    return AIMessage(content=content)
                if not isinstance(parsed, dict):
                    return AIMessage(content=content)
                if parsed.get("tool_calls"):
                    calls = []
                    for item in parsed.get("tool_calls") or []:
                        if isinstance(item, dict):
                            calls.append(
                                {
                                    "name": item.get("name") or item.get("tool") or "tool",
                                    "args": item.get("arguments") or item.get("args") or {},
                                    "id": item.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                                }
                            )
                    return AIMessage(content=str(parsed.get("assistant_response") or ""), tool_calls=calls)
                if parsed.get("tool"):
                    return AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": parsed.get("tool"),
                                "args": parsed.get("arguments") or {},
                                "id": parsed.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                            }
                        ],
                    )
                if str(parsed.get("type") or "").lower() == "final":
                    return AIMessage(content=str(parsed.get("content") or parsed.get("summary") or ""))
                return AIMessage(content=content)

        self.model = _Model(model_call=model_call, bound_tools=bound_tools or [])


class DeepAgentsSessionRunner:
    def __init__(
        self,
        *,
        repository: Any,
        notify_event: Any,
        model_call: Any = None,
        async_subagent_service: AsyncSubagentService | None = None,
    ):
        self.repository = repository
        self.notify_event = notify_event
        self.model_call = model_call
        self.agent_registry = AgentRegistry()
        self.async_subagent_service = async_subagent_service
        self._checkpointer = None
        self._checkpointer_context = None
        self._checkpointer_loop = None

    async def run_prompt(self, session_id: str, prompt: str, *, context_files: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            session = self.repository.get_session(session_id)
            if not session:
                raise ValueError("Agent session not found")
            graph = await self._build_graph(session, prompt)
            config = self._graph_config(session)
            mapper = DeepAgentsEventMapper(self.repository, self.notify_event, session_id)
            mapper.session_started()
            last_summary = ""

            payload: dict[str, Any] = {"messages": prompt}
            if context_files:
                payload["files"] = context_files
            async for event in graph.astream_events(payload, config=config, version="v2"):
                mapper.handle(event)
                summary = self._extract_summary(event)
                if summary:
                    last_summary = summary
                if self._is_interrupted(session_id):
                    return self._with_parts(session_id)

            session = self.repository.get_session(session_id) or session
            if self._is_interrupted(session_id):
                return self._with_parts(session_id)
            if self._has_pending_permission(session_id):
                return self._with_parts(session_id)
            metadata = ensure_session_state(dict(session.get("metadata") or {}))
            metadata = set_phase(metadata, "completed")
            summary = last_summary or "DeepAgents 执行完成。"
            mapper.complete_summary(summary)
            self.repository.update_session(session_id, status="completed", metadata=metadata)
            return self._with_parts(session_id)
        finally:
            await self._close_checkpointer()

    async def resume(self, session_id: str, decision: dict[str, Any]) -> dict[str, Any]:
        try:
            session = self.repository.get_session(session_id)
            if not session:
                raise ValueError("Agent session not found")
            prompt = str((session.get("metadata") or {}).get("current_goal") or "继续执行。")
            graph = await self._build_graph(session, prompt)
            mapper = DeepAgentsEventMapper(self.repository, self.notify_event, session_id)
            config = self._graph_config(session)
            last_summary = ""
            async for event in graph.astream_events(Command(resume=self._resume_payload(decision)), config=config, version="v2"):
                mapper.handle(event)
                summary = self._extract_summary(event)
                if summary:
                    last_summary = summary
                if self._is_interrupted(session_id):
                    return self._with_parts(session_id)
            session = self.repository.get_session(session_id) or session
            if self._is_interrupted(session_id):
                return self._with_parts(session_id)
            if self._has_pending_permission(session_id):
                return self._with_parts(session_id)
            metadata = ensure_session_state(dict(session.get("metadata") or {}))
            metadata = set_phase(metadata, "completed")
            mapper.complete_summary(last_summary or "DeepAgents 已继续执行并完成。")
            self.repository.update_session(session_id, status="completed", metadata=metadata)
            return self._with_parts(session_id)
        finally:
            await self._close_checkpointer()

    async def _build_graph(self, session: dict[str, Any], prompt: str) -> Any:
        _load_create_deep_agent()
        session_id = str(session.get("id"))
        project_path = str(session.get("project_path") or Path.cwd())
        metadata = dict(session.get("metadata") or {})
        agent_id = str(session.get("agent_id") or "build")
        agent = self.agent_registry.get(agent_id)
        self._validate_session_agent_mode(agent, session)
        user_id = str(metadata.get("user_id") or metadata.get("memory_user_id") or "default")
        org_id = str(metadata.get("org_id") or "default-org")
        enabled_skill_sources = metadata.get("enabled_skill_sources")
        if enabled_skill_sources is not None and not isinstance(enabled_skill_sources, list):
            enabled_skill_sources = None
        permission_policy = permission_policy_for_agent(agent, agent_id, metadata)
        permission_policy.validate_enabled_skills(project_path, enabled_skill_sources)
        context = RuntimeExecutionContext(
            session_id=session_id,
            goal=prompt,
            project_path=project_path,
            provider=str(session.get("provider") or ""),
            model=session.get("model"),
            metadata=metadata,
        )
        if self.model_call is not None:
            model = CallableToolCallingChatModel(self.model_call).model
        elif context.provider:
            model = get_chat_model(context)
        else:
            raise RuntimeError("DeepAgents requires a configured provider/model or injected model_call")
        return build_deep_agent_runtime(
            DeepAgentRuntimeConfig(
                model=model,
                tools=self._local_async_tools_for_session(session),
                system_prompt=self._system_prompt(agent_id),
                project_path=project_path,
                user_id=user_id,
                agent_id=agent_id,
                org_id=org_id,
                memory=memory_files_for_project(project_path, user_id=user_id, agent_id=agent_id, org_id=org_id),
                skills=resolve_enabled_skill_sources(
                    project_path,
                    user_id=user_id,
                    agent_id=agent_id,
                    org_id=org_id,
                    enabled_skill_sources=enabled_skill_sources,
                ),
                enabled_skill_sources=enabled_skill_sources,
                permissions=permission_policy.filesystem_permissions(),
                middleware=permission_policy.tool_constraint_middleware(DEEPAGENTS_BUILTIN_TOOLS, logger),
                subagents=self._subagents_for_agent(agent_id, model),
                interrupt_on=permission_policy.interrupt_on(),
                checkpointer=await self._get_checkpointer(),
            )
        )

    def _local_async_tools_for_session(self, session: dict[str, Any]) -> list[Any]:
        agent_id = str(session.get("agent_id") or "build")
        agent = self.agent_registry.get(agent_id)
        if not agent or not agent.can_delegate or not agent.handoff_targets:
            return []

        from langchain_core.tools import StructuredTool

        session_id = str(session.get("id"))
        service = self._async_subagent_service()

        async def start_async_task(subagent_type: str, description: str) -> str:
            try:
                result = await service.start_task(session_id, subagent_type, description)
            except ValueError as exc:
                result = {"status": "failed", "error": str(exc), "task_id": None}
            return self._json_tool_result(result)

        async def check_async_task(task_id: str) -> str:
            try:
                result = service.check_task(session_id, task_id)
            except ValueError as exc:
                result = {"status": "not_found", "task_id": task_id, "error": str(exc)}
            return self._json_tool_result(result)

        async def list_async_tasks(status_filter: str | None = None) -> str:
            try:
                result = service.list_tasks(session_id, status_filter)
            except ValueError as exc:
                result = {"tasks": [], "status_filter": status_filter or "all", "error": str(exc)}
            return self._json_tool_result(result)

        async def update_async_task(task_id: str, description: str) -> str:
            try:
                result = await service.update_task(session_id, task_id, description)
            except ValueError as exc:
                result = {"status": "failed", "task_id": task_id, "error": str(exc)}
            return self._json_tool_result(result)

        async def cancel_async_task(task_id: str, reason: str | None = None) -> str:
            try:
                result = await service.cancel_task(session_id, task_id, reason)
            except ValueError as exc:
                result = {"status": "not_found", "task_id": task_id, "error": str(exc)}
            return self._json_tool_result(result)

        available = ", ".join(agent.handoff_targets)
        tools = [
            StructuredTool.from_function(
                coroutine=start_async_task,
                name="start_async_task",
                description=(
                    "Start a local async subagent task. It returns a task_id immediately. "
                    f"Available subagent types: {available}. Do not immediately check status after starting."
                ),
                args_schema=StartAsyncTaskInput,
            ),
            StructuredTool.from_function(
                coroutine=check_async_task,
                name="check_async_task",
                description="Check the current status and result for a local async subagent task.",
                args_schema=CheckAsyncTaskInput,
            ),
            StructuredTool.from_function(
                coroutine=list_async_tasks,
                name="list_async_tasks",
                description="List local async subagent tasks for the current parent session.",
                args_schema=ListAsyncTasksInput,
            ),
            StructuredTool.from_function(
                coroutine=update_async_task,
                name="update_async_task",
                description="Restart a local async subagent task with new instructions while preserving its task_id.",
                args_schema=UpdateAsyncTaskInput,
            ),
            StructuredTool.from_function(
                coroutine=cancel_async_task,
                name="cancel_async_task",
                description="Soft-cancel a local async subagent task.",
                args_schema=CancelAsyncTaskInput,
            ),
        ]
        return permission_policy_for_agent(agent, agent_id, dict(session.get("metadata") or {})).filter_named_tools(tools)

    def _async_subagent_service(self) -> AsyncSubagentService:
        if self.async_subagent_service is None:
            self.async_subagent_service = AsyncSubagentService(
                self.repository,
                self.notify_event,
                model_call=self.model_call,
            )
        self.async_subagent_service.set_model_call(self.model_call)
        return self.async_subagent_service

    async def start_async_subtask(self, parent_session_id: str, subagent_type: str, description: str) -> dict[str, Any]:
        return await self._async_subagent_service().start_task(parent_session_id, subagent_type, description)

    def check_async_subtask(self, parent_session_id: str, task_id: str) -> dict[str, Any]:
        return self._async_subagent_service().check_task(parent_session_id, task_id)

    def list_async_subtasks(self, parent_session_id: str, status_filter: str | None = None) -> dict[str, Any]:
        return self._async_subagent_service().list_tasks(parent_session_id, status_filter)

    def list_async_subtask_events(self, parent_session_id: str, task_id: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        service = self._async_subagent_service()
        if task_id:
            return service.task_events(parent_session_id, task_id, limit)
        return service.parent_events(parent_session_id, limit)

    def get_async_subtask_metrics(self, parent_session_id: str) -> dict[str, Any]:
        return self._async_subagent_service().metrics(parent_session_id)

    @staticmethod
    def _json_tool_result(result: dict[str, Any]) -> str:
        return json.dumps(result, ensure_ascii=False)

    def _subagents_for_agent(self, agent_id: str, model: Any) -> list[dict[str, Any]]:
        agent = self.agent_registry.get(agent_id)
        if not agent or not agent.can_delegate:
            return []
        subagents: list[dict[str, Any]] = []
        for target_id in agent.handoff_targets:
            target = self.agent_registry.get(target_id)
            if target is None:
                raise ValueError(f"Unknown handoff target '{target_id}' for agent '{agent_id}'")
            if not target.can_be_handoff_target:
                raise ValueError(f"Handoff target '{target_id}' for agent '{agent_id}' cannot be used as a subagent")
            subagents.append(self._subagent_spec(target, model))
        return subagents

    def _subagent_spec(self, agent: AgentDefinition, model: Any) -> dict[str, Any]:
        permission_policy = permission_policy_for_agent(agent, agent.id)
        return {
            "name": agent.id,
            "description": agent.description or agent.name,
            "system_prompt": self._agent_system_prompt(agent),
            "model": model,
            "tools": [],
            "middleware": permission_policy.tool_constraint_middleware(DEEPAGENTS_BUILTIN_TOOLS, logger),
            "permissions": permission_policy.filesystem_permissions(),
        }

    def _graph_config(self, session: dict[str, Any]) -> dict[str, Any]:
        session_id = str(session.get("id"))
        agent = self.agent_registry.get(str(session.get("agent_id") or "build"))
        config: dict[str, Any] = {"configurable": {"thread_id": deepagents_thread_id(session_id)}}
        if agent:
            config["recursion_limit"] = self._recursion_limit_for_agent(agent)
        return config

    @staticmethod
    def _validate_session_agent_mode(agent: AgentDefinition | None, session: dict[str, Any]) -> None:
        agent_id = str(session.get("agent_id") or "build")
        if agent is None:
            raise ValueError(f"Unknown agent id: {agent_id}")
        metadata = dict(session.get("metadata") or {})
        is_async_child = bool(metadata.get("async_subagent"))
        if is_async_child:
            if not agent.can_be_handoff_target:
                raise ValueError(f"Agent '{agent_id}' cannot run as a subagent in mode '{agent.mode}'")
            return
        if not agent.can_start_directly:
            raise ValueError(f"Agent '{agent_id}' cannot be started directly in mode '{agent.mode}'")

    @staticmethod
    def _recursion_limit_for_agent(agent: AgentDefinition) -> int:
        return max(2, int(agent.max_iterations)) * 4 + 8

    @staticmethod
    def _agent_system_prompt(agent: AgentDefinition) -> str:
        prompt = agent.system_prompt.strip()
        requirements = agent.output_requirements.strip()
        if not requirements:
            return prompt
        return f"{prompt}\n\n## 输出要求\n{requirements}" if prompt else f"## 输出要求\n{requirements}"

    def _system_prompt_sections(self, agent: AgentDefinition | None) -> list[str]:
        sections: list[str] = []
        if agent:
            agent_prompt = self._agent_system_prompt(agent)
            if agent_prompt:
                sections.append(agent_prompt)
        sections.extend(self._platform_prompt_sections())
        async_section = self._async_subagent_prompt(agent)
        if async_section:
            sections.append(async_section)
        return sections

    @staticmethod
    def _platform_prompt_sections() -> list[str]:
        return [
            PLATFORM_IDENTITY_PROMPT,
            FILESYSTEM_PROMPT,
            CONTEXT_PROMPT,
            SKILLS_PROMPT,
            EXECUTION_PROMPT,
        ]

    @staticmethod
    def _async_subagent_prompt(agent: AgentDefinition | None) -> str:
        if not agent or not agent.can_delegate or not agent.handoff_targets:
            return ""
        available = "、".join(agent.handoff_targets)
        return (
            "你还可以启动本地异步子代理任务："
            f"可用子代理类型是 {available}。"
            "使用 start_async_task 启动后台只读任务后，必须立刻把完整 task_id 告诉用户并停止，"
            "不要在同一轮里马上轮询。只有用户要求查看状态或结果时，才使用 check_async_task 或 list_async_tasks。"
            "用户要求调整或停止异步任务时，使用 update_async_task 或 cancel_async_task。"
            "不要凭历史消息报告任务状态，必须调用工具获取最新状态。"
        )

    async def _get_checkpointer(self) -> Any:
        loop = asyncio.get_running_loop()
        if self._checkpointer is None or self._checkpointer_loop is not loop:
            if self._checkpointer_context is not None:
                try:
                    await self._checkpointer_context.__aexit__(None, None, None)
                except Exception:
                    logger.debug("Failed to close stale DeepAgents checkpointer", exc_info=True)
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

            self._checkpointer_context = AsyncSqliteSaver.from_conn_string(get_checkpoint_db_path())
            self._checkpointer = await self._checkpointer_context.__aenter__()
            await self._configure_checkpointer_sqlite(self._checkpointer)
            self._checkpointer_loop = loop
            if hasattr(self._checkpointer, "setup"):
                await self._checkpointer.setup()
        return self._checkpointer

    async def _configure_checkpointer_sqlite(self, checkpointer: Any) -> None:
        conn = getattr(checkpointer, "conn", None)
        if conn is None:
            conn = getattr(checkpointer, "connection", None)
        if conn is None:
            return
        busy_timeout = int(os.environ.get("LANGGRAPH_SQLITE_BUSY_TIMEOUT", os.environ.get("SQLITE_BUSY_TIMEOUT", "30000")))
        try:
            await conn.execute(f"PRAGMA busy_timeout = {busy_timeout}")
            await conn.execute("PRAGMA journal_mode = WAL")
            await conn.execute("PRAGMA synchronous = NORMAL")
            await conn.commit()
        except Exception:
            logger.warning("Failed to configure DeepAgents checkpoint SQLite pragmas", exc_info=True)

    async def _close_checkpointer(self) -> None:
        if self._checkpointer_context is not None:
            try:
                await self._checkpointer_context.__aexit__(None, None, None)
            except Exception:
                logger.debug("Failed to close DeepAgents checkpointer", exc_info=True)
            self._checkpointer_context = None
            self._checkpointer = None

    def _with_parts(self, session_id: str) -> dict[str, Any]:
        session = self.repository.get_session(session_id) or {}
        session["parts"] = self.repository.list_parts(session_id)
        return session

    def _has_pending_permission(self, session_id: str) -> bool:
        return any(
            part.get("type") == "permission" and part.get("status") == "pending"
            for part in self.repository.list_parts(session_id)
        )

    def _is_interrupted(self, session_id: str) -> bool:
        session = self.repository.get_session(session_id) or {}
        metadata = dict(session.get("metadata") or {})
        return str(session.get("status") or "") == "interrupted" or bool(metadata.get("interrupt_requested"))

    def _extract_summary(self, event: dict[str, Any]) -> str:
        if str(event.get("event") or "") not in {"on_chain_end", "on_chat_model_end"}:
            return ""
        data = event.get("data") or {}
        output = data.get("output")
        if isinstance(output, dict):
            messages = output.get("messages")
            if isinstance(messages, list) and messages:
                content = getattr(messages[-1], "content", "")
                return content if isinstance(content, str) else str(content)
        content = getattr(output, "content", "")
        return content if isinstance(content, str) else ""

    def _resume_payload(self, decision: dict[str, Any]) -> dict[str, Any]:
        if "decisions" in decision:
            return {"decisions": list(decision.get("decisions") or [])}
        approved = bool(decision.get("approved") or decision.get("decision") == "executed")
        return {"decisions": [{"type": "approve" if approved else "reject"}]}

    def _system_prompt(self, agent_id: str) -> str:
        agent = self.agent_registry.get(agent_id)
        return "\n\n".join(self._system_prompt_sections(agent))


__all__ = ["DeepAgentsSessionRunner", "DeepAgentsUnavailable", "deepagents_thread_id"]
