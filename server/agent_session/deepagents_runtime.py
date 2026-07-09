from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
import weakref
from collections.abc import Callable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from langgraph.types import Command
from pydantic import BaseModel, Field

from .agent_registry import AgentRegistry
from .async_subagent_policy import async_subagent_manifest_for_agent
from .async_subagents import AsyncSubagentService
from .deepagents_checkpoint import get_checkpoint_db_path
from .deepagents_events import DeepAgentsEventMapper
from .execution_context import AgentDefinition, RuntimeExecutionContext
from .model_adapter import get_chat_model
from .permission import permission_policy_for_agent
from .runtime import (
    build_deep_agent_runtime,
    prepare_deepagents_files,
)
from .runtime_contract import (
    AgentRuntimeContract,
    agent_system_prompt,
    build_system_prompt,
    platform_prompt_sections,
    recursion_limit_for_agent,
    system_prompt_sections,
    validate_agent_launch,
)
from .runtime_factory import ensure_deepagents_available
from .session_state_machine import AgentSessionStateMachine
from .trajectory import (
    TrajectoryStateStore,
    build_trajectory_middleware,
    trajectory_policy_for_agent,
)

logger = logging.getLogger(__name__)

# Tracks live runner instances so test fixtures can close compat checkpointer
# contexts created via _get_checkpointer() without each test having to do it.
_RUNNER_INSTANCES: "weakref.WeakSet[DeepAgentsSessionRunner]" = weakref.WeakSet()

DEEPAGENTS_BUILTIN_TOOLS = frozenset(
    {
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
    ensure_deepagents_available()
    return True


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
                from langchain_core.messages import (
                    AIMessage,
                    HumanMessage,
                    SystemMessage,
                    ToolMessage,
                )
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
        interrupt_session: Callable[..., Any] | None = None,
    ):
        self.repository = repository
        self.notify_event = notify_event
        self.model_call = model_call
        self.agent_registry = AgentRegistry()
        self.async_subagent_service = async_subagent_service
        self.interrupt_session = interrupt_session
        self._compat_checkpointer_contexts: list[Any] = []
        self.state_machine = AgentSessionStateMachine(repository)
        _RUNNER_INSTANCES.add(self)

    async def run_prompt(self, session_id: str, prompt: str, *, context_files: dict[str, str] | None = None) -> dict[str, Any]:
        async with self._open_checkpointer() as checkpointer:
            session = self.repository.get_session(session_id)
            if not session:
                raise ValueError("Agent session not found")
            agent = self.agent_registry.get(str(session.get("agent_id") or "build"))
            policy = trajectory_policy_for_agent(agent)
            trajectory_store = TrajectoryStateStore(self.repository, self.notify_event, session_id)
            if policy["enabled"]:
                trajectory_store.begin_run()
            graph = await self._build_graph(session, prompt, checkpointer=checkpointer)
            config = self._graph_config(session)
            mapper = DeepAgentsEventMapper(self.repository, self.notify_event, session_id)
            mapper.session_started()
            last_summary = ""

            payload: dict[str, Any] = {"messages": prompt}
            if context_files:
                payload["files"] = await prepare_deepagents_files(graph, config, context_files)
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
            ready, correction_summary = await self._complete_trajectory_requirements(
                graph,
                config,
                mapper,
                session_id,
                policy,
                trajectory_store,
            )
            if not ready:
                return self._with_parts(session_id)
            if correction_summary:
                last_summary = correction_summary
            summary = last_summary or "DeepAgents 执行完成。"
            mapper.complete_summary(summary)
            self.state_machine.mark_completed(session_id)
            return self._with_parts(session_id)

    async def resume(self, session_id: str, decision: dict[str, Any]) -> dict[str, Any]:
        async with self._open_checkpointer() as checkpointer:
            session = self.repository.get_session(session_id)
            if not session:
                raise ValueError("Agent session not found")
            prompt = str((session.get("metadata") or {}).get("current_goal") or "继续执行。")
            graph = await self._build_graph(session, prompt, checkpointer=checkpointer)
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
            agent = self.agent_registry.get(str(session.get("agent_id") or "build"))
            policy = trajectory_policy_for_agent(agent)
            trajectory_store = TrajectoryStateStore(self.repository, self.notify_event, session_id)
            ready, correction_summary = await self._complete_trajectory_requirements(
                graph,
                config,
                mapper,
                session_id,
                policy,
                trajectory_store,
            )
            if not ready:
                return self._with_parts(session_id)
            if correction_summary:
                last_summary = correction_summary
            mapper.complete_summary(last_summary or "DeepAgents 已继续执行并完成。")
            self.state_machine.mark_completed(session_id)
            return self._with_parts(session_id)

    async def _build_graph(self, session: dict[str, Any], prompt: str, *, checkpointer: Any | None = None) -> Any:
        _load_create_deep_agent()
        session_id = str(session.get("id"))
        project_path = str(session.get("project_path") or Path.cwd())
        agent_id = str(session.get("agent_id") or "build")
        agent = self.agent_registry.get(agent_id)
        metadata = dict(session.get("metadata") or {})
        permission_policy = permission_policy_for_agent(agent, agent_id, metadata)
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
        trajectory_middleware = build_trajectory_middleware(
            repository=self.repository,
            notify_event=self.notify_event,
            session_id=session_id,
            project_path=project_path,
            agent=agent,
        )
        if checkpointer is None:
            checkpointer = await self._get_checkpointer()
        contract = AgentRuntimeContract.for_agent_session(
            session=session,
            goal=prompt,
            model=model,
            agent_registry=self.agent_registry,
            tools=self._local_async_tools_for_session(session),
            middleware=[
                *trajectory_middleware,
                *permission_policy.tool_constraint_middleware(DEEPAGENTS_BUILTIN_TOOLS, logger),
            ],
            subagents=self._subagents_for_agent(agent_id, model, metadata),
            checkpointer=checkpointer,
        )
        return build_deep_agent_runtime(contract)

    async def _complete_trajectory_requirements(
        self,
        graph: Any,
        config: dict[str, Any],
        mapper: DeepAgentsEventMapper,
        session_id: str,
        policy: dict[str, Any],
        store: TrajectoryStateStore,
    ) -> tuple[bool, str]:
        if not policy.get("enabled"):
            return True, ""
        last_summary = ""
        while issues := store.completion_issues(policy):
            state = store.load()
            correction_count = int(state.get("auto_corrections") or 0)
            if correction_count >= int(policy.get("max_auto_corrections") or 0):
                self._mark_trajectory_manual_review(session_id, issues, store)
                return False, last_summary
            attempt = store.increment_correction(issues)
            prompt = self._trajectory_correction_prompt(issues, attempt)
            async for event in graph.astream_events({"messages": prompt}, config=config, version="v2"):
                mapper.handle(event)
                summary = self._extract_summary(event)
                if summary:
                    last_summary = summary
                if self._is_interrupted(session_id) or self._has_pending_permission(session_id):
                    return False, last_summary
        return True, last_summary

    def _mark_trajectory_manual_review(
        self,
        session_id: str,
        issues: list[dict[str, Any]],
        store: TrajectoryStateStore,
    ) -> None:
        message = "轨迹验证要求在自动纠正次数耗尽后仍未满足：" + "；".join(
            str(issue.get("message") or "") for issue in issues
        )
        part = self.repository.add_part(
            session_id,
            "error",
            status="failed",
            title="轨迹验证未完成",
            content=message,
            payload={
                "guard": "trajectory_guard",
                "issues": issues,
                "trajectory_guard": store.public_summary(),
            },
        )
        event = self.repository.add_event(
            session_id,
            "trajectory_validation_required",
            message,
            {
                "session_id": session_id,
                "part_id": part.get("id"),
                "part_type": "error",
                "status": "failed",
                "guard": "trajectory_guard",
                "issues": issues,
                "part": part,
            },
        )
        self.notify_event(session_id, event)
        session = self.repository.get_session(session_id) or {}
        metadata = dict(session.get("metadata") or {})
        metadata["latest_error"] = message
        self.state_machine.mark_failed(
            session_id,
            metadata=metadata,
            status="needs_manual_review",
            error=message,
        )

    @staticmethod
    def _trajectory_correction_prompt(issues: list[dict[str, Any]], attempt: int) -> str:
        issue_text = "\n".join(
            f"- {issue.get('message')} 涉及：{', '.join(issue.get('paths') or [])}"
            for issue in issues
        )
        return (
            f"这是第 {attempt} 次轨迹自动纠正。你刚才准备结束任务，但尚未满足平台验证要求：\n"
            f"{issue_text}\n"
            "请立即完成缺失的验证。源码、测试或配置应运行相关测试、构建、类型检查、lint 或语法检查；"
            "文档可重新读取最终内容确认。若验证失败，先重新读取受影响文件，再修复并重新验证。"
            "不要只解释计划，必须实际执行验证。"
        )

    def _local_async_tools_for_session(self, session: dict[str, Any]) -> list[Any]:
        agent_id = str(session.get("agent_id") or "build")
        agent = self.agent_registry.get(agent_id)
        manifest = async_subagent_manifest_for_agent(self.agent_registry, agent)
        if not manifest.enabled:
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

        available = manifest.available_label()
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
                interrupt_session=self.interrupt_session,
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

    def _subagents_for_agent(self, agent_id: str, model: Any, metadata: dict[str, Any] | None = None) -> list[dict[str, Any]]:
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
            subagents.append(self._subagent_spec(target, model, metadata))
        return subagents

    def _subagent_spec(self, agent: AgentDefinition, model: Any, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        permission_policy = permission_policy_for_agent(agent, agent.id, metadata)
        return {
            "name": agent.id,
            "description": agent.description or agent.name,
            "system_prompt": self._agent_system_prompt(agent),
            "model": model,
            "tools": [],
            "middleware": permission_policy.tool_constraint_middleware(DEEPAGENTS_BUILTIN_TOOLS, logger),
            "permissions": permission_policy.filesystem_permissions(),
            "interrupt_on": permission_policy.interrupt_on(),
        }

    def _graph_config(self, session: dict[str, Any]) -> dict[str, Any]:
        session_id = str(session.get("id"))
        agent = self.agent_registry.get(str(session.get("agent_id") or "build"))
        config: dict[str, Any] = {"configurable": {"thread_id": deepagents_thread_id(session_id)}}
        if agent:
            config["recursion_limit"] = recursion_limit_for_agent(agent)
        return config

    @staticmethod
    def _validate_session_agent_mode(agent: AgentDefinition | None, session: dict[str, Any]) -> None:
        agent_id = str(session.get("agent_id") or "build")
        validate_agent_launch(agent, agent_id, dict(session.get("metadata") or {}))

    @staticmethod
    def _recursion_limit_for_agent(agent: AgentDefinition) -> int:
        return recursion_limit_for_agent(agent) or 0

    @staticmethod
    def _agent_system_prompt(agent: AgentDefinition) -> str:
        return agent_system_prompt(agent)

    def _system_prompt_sections(self, agent: AgentDefinition | None) -> list[str]:
        return system_prompt_sections(self.agent_registry, agent)

    @staticmethod
    def _platform_prompt_sections() -> list[str]:
        return platform_prompt_sections()

    def _async_subagent_prompt(self, agent: AgentDefinition | None) -> str:
        from .runtime_contract import async_subagent_prompt

        return async_subagent_prompt(self.agent_registry, agent)

    @asynccontextmanager
    async def _open_checkpointer(self) -> Any:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        context = AsyncSqliteSaver.from_conn_string(get_checkpoint_db_path())
        checkpointer = await context.__aenter__()
        try:
            await self._configure_checkpointer_sqlite(checkpointer)
            if hasattr(checkpointer, "setup"):
                await checkpointer.setup()
            yield checkpointer
        finally:
            try:
                await context.__aexit__(None, None, None)
            except Exception:
                logger.debug("Failed to close DeepAgents checkpointer", exc_info=True)

    async def _get_checkpointer(self) -> Any:
        """Compatibility helper for tests that call _build_graph directly.

        Production prompt/resume paths use _open_checkpointer so every run owns
        and closes its checkpointer in the current event loop.
        """
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        context = AsyncSqliteSaver.from_conn_string(get_checkpoint_db_path())
        checkpointer = await context.__aenter__()
        self._compat_checkpointer_contexts.append(context)
        await self._configure_checkpointer_sqlite(checkpointer)
        if hasattr(checkpointer, "setup"):
            await checkpointer.setup()
        return checkpointer

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
        while self._compat_checkpointer_contexts:
            context = self._compat_checkpointer_contexts.pop()
            try:
                await context.__aexit__(None, None, None)
            except Exception:
                logger.debug("Failed to close DeepAgents checkpointer", exc_info=True)

    async def aclose(self) -> None:
        """Close any compat checkpointer contexts held by this runner.

        Tests that construct a runner directly (and reach ``_get_checkpointer``)
        should ensure this is called in teardown. The shared autouse fixture in
        the runtime test modules calls it for all live runners automatically.
        """
        await self._close_checkpointer()

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
        return build_system_prompt(self.agent_registry, agent)


__all__ = ["DeepAgentsSessionRunner", "DeepAgentsUnavailable", "deepagents_thread_id"]
