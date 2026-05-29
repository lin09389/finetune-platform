from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Sequence

from langgraph.types import Command

from .deepagents_compat import patch_torch_pytree_for_transformers
from .deepagents_events import DeepAgentsEventMapper
from .execution_context import RuntimeExecutionContext
from .deepagents_checkpoint import get_checkpoint_db_path
from .model_adapter import get_chat_model
from .permission import filesystem_permissions_for_agent
from .runtime import DeepAgentRuntimeConfig, build_deep_agent_runtime, memory_files_for_project, resolve_interrupt_on, resolve_skill_sources
from .state import ensure_session_state, set_phase

logger = logging.getLogger(__name__)


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
    def __init__(self, *, repository: Any, notify_event: Any, model_call: Any = None):
        self.repository = repository
        self.notify_event = notify_event
        self.model_call = model_call
        self._checkpointer = None
        self._checkpointer_context = None
        self._checkpointer_loop = None

    async def run_prompt(self, session_id: str, prompt: str, *, context_files: dict[str, str] | None = None) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        graph = await self._build_graph(session, prompt)
        config = {"configurable": {"thread_id": deepagents_thread_id(session_id)}}
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

        session = self.repository.get_session(session_id) or session
        if self._has_pending_permission(session_id):
            return self._with_parts(session_id)
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        metadata = set_phase(metadata, "completed")
        summary = last_summary or "DeepAgents 执行完成。"
        mapper.complete_summary(summary)
        self.repository.update_session(session_id, status="completed", metadata=metadata)
        return self._with_parts(session_id)

    async def resume(self, session_id: str, decision: dict[str, Any]) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        prompt = str((session.get("metadata") or {}).get("current_goal") or "继续执行。")
        graph = await self._build_graph(session, prompt)
        mapper = DeepAgentsEventMapper(self.repository, self.notify_event, session_id)
        config = {"configurable": {"thread_id": deepagents_thread_id(session_id)}}
        last_summary = ""
        async for event in graph.astream_events(Command(resume=self._resume_payload(decision)), config=config, version="v2"):
            mapper.handle(event)
            summary = self._extract_summary(event)
            if summary:
                last_summary = summary
        session = self.repository.get_session(session_id) or session
        if self._has_pending_permission(session_id):
            return self._with_parts(session_id)
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        metadata = set_phase(metadata, "completed")
        mapper.complete_summary(last_summary or "DeepAgents 已继续执行并完成。")
        self.repository.update_session(session_id, status="completed", metadata=metadata)
        return self._with_parts(session_id)

    async def _build_graph(self, session: dict[str, Any], prompt: str) -> Any:
        _load_create_deep_agent()
        session_id = str(session.get("id"))
        project_path = str(session.get("project_path") or Path.cwd())
        metadata = dict(session.get("metadata") or {})
        agent_id = str(session.get("agent_id") or "build")
        user_id = str(metadata.get("user_id") or metadata.get("memory_user_id") or "default")
        org_id = str(metadata.get("org_id") or "default-org")
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
                tools=[],
                system_prompt=self._system_prompt(),
                project_path=project_path,
                user_id=user_id,
                agent_id=agent_id,
                org_id=org_id,
                memory=memory_files_for_project(project_path, user_id=user_id, agent_id=agent_id, org_id=org_id),
                skills=resolve_skill_sources(project_path, user_id=user_id, agent_id=agent_id, org_id=org_id),
                permissions=filesystem_permissions_for_agent(agent_id),
                interrupt_on=resolve_interrupt_on(metadata),
                checkpointer=await self._get_checkpointer(),
            )
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
            self._checkpointer_loop = loop
            if hasattr(self._checkpointer, "setup"):
                await self._checkpointer.setup()
        return self._checkpointer

    def _with_parts(self, session_id: str) -> dict[str, Any]:
        session = self.repository.get_session(session_id) or {}
        session["parts"] = self.repository.list_parts(session_id)
        return session

    def _has_pending_permission(self, session_id: str) -> bool:
        return any(
            part.get("type") == "permission" and part.get("status") == "pending"
            for part in self.repository.list_parts(session_id)
        )

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

    def _system_prompt(self) -> str:
        return (
            "你是 Finetune Platform 的代码 Agent。你需要先理解项目，再使用工具完成任务。"
            "文件操作使用 DeepAgents harness 内置的 ls/read_file/glob/grep/write_file/edit_file。"
            "项目文件位于 `/workspace/`；DeepAgents 内部文件和上下文文件位于状态后端，"
            "包括 /context/、/large_tool_results/ 和 /conversation_history/。"
            "长期记忆位于 `/memories/`，Agent 自身记忆位于 `/agent-memory/`，"
            "组织策略位于只读的 `/policies/`。"
            "读取或修改项目文件时必须使用 `/workspace/...` 路径。"
            "用户当前任务相关的大上下文会作为 /context/ 下的虚拟文件传入，"
            "你需要按需读取 /context/task.md、/context/editor/active-file.md、"
            "/context/mentions/ 或 /context/retrieval/ 下的文件，"
            "不要把这些文件完整复述给用户。"
            "Skills 使用 DeepAgents 官方 Skills System 加载；你需要先依据 skills 列表匹配任务，"
            "只在适用时读取对应 SKILL.md 和其中引用的附属文件，不要把全部 skill 内容塞进主上下文。"
            "需要运行测试、安装依赖或调用 CLI 时，直接使用官方 sandbox execute 工具；"
            "命令不需要平台白名单审批。"
            "执行命令前优先说明意图，执行后根据 execute 输出继续判断。"
        )


__all__ = ["DeepAgentsSessionRunner", "DeepAgentsUnavailable", "deepagents_thread_id"]
