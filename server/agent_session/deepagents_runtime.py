from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
import weakref
from collections.abc import Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
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
from .phase_tool_router import parse_phase_tool_projection
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
from .training_tools import (
    build_training_tools,
    training_submission_interrupt_metadata,
    training_tools_enabled_for_session,
)
from .trajectory import (
    TrajectoryStateStore,
    build_trajectory_middleware,
    trajectory_policy_for_agent,
)

logger = logging.getLogger(__name__)

# Tracks live runner instances so test fixtures can close compat checkpointer
# contexts created via _get_checkpointer() without each test having to do it.
_RUNNER_INSTANCES: weakref.WeakSet[DeepAgentsSessionRunner] = weakref.WeakSet()

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


def _is_tool_exclusion_middleware(middleware: Any) -> bool:
    """True for DeepAgents ``_ToolExclusionMiddleware`` instances."""
    return type(middleware).__name__ == "_ToolExclusionMiddleware"


def _build_exclusion_middleware(excluded: frozenset[str], logger: logging.Logger) -> Any:
    """Construct a DeepAgents tool-exclusion middleware for ``excluded`` names."""
    try:
        from deepagents.middleware._tool_exclusion import _ToolExclusionMiddleware
    except Exception:  # pragma: no cover - depends on optional runtime dependency
        logger.warning("DeepAgents tool exclusion middleware is unavailable; cannot enforce controlled exclusion")
        return None
    return _ToolExclusionMiddleware(excluded=excluded)


def _downgrade_contract_to_legacy(contract: AgentRuntimeContract) -> AgentRuntimeContract:
    """Return a copy of ``contract`` downgraded to legacy orchestration mode."""
    return dataclass_replace(contract, orchestration_mode="legacy", tool_projection=None)


@dataclass(frozen=True, slots=True)
class _ControlledToolRuntime:
    """Per-session owned Tool Gateway assembly for controlled mode.

    Holds the :class:`ToolGateway`, its backing registry and the event mapper
    together so prompt/resume turns on the same runner reuse the *exact same*
    in-process terminal-outcome cache (the cache that lets a HITL replay hit
    its prior suspended invocation instead of starting over).
    """

    gateway: Any
    registry: Any
    mapper: Any


def _controlled_interrupt_on(registry: Any, facts: Any) -> dict[str, Any] | None:
    """Derive the DeepAgents ``interrupt_on`` map for controlled mode.

    A managed tool is added to ``interrupt_on`` when its declared side effects
    intersect the session's ``require_approval_for`` set - i.e. exactly the
    tools the deterministic policy would ``ask`` for. DeepAgents then suspends
    the run before such a tool executes (waiting_approval -> approve -> resume),
    so the Tool Gateway only ever sees already-approved invocations and never
    has to grant an ``ask`` itself.
    """
    from tool_platform.registry import ToolProjectionContext

    require = facts.require_approval_for
    if not require:
        return None
    context = ToolProjectionContext(
        agent_id="build",
        runtime_kind=facts.runtime_kind,
        enabled_capabilities=facts.enabled_capabilities,
    )
    interrupt: dict[str, Any] = {}
    for definition in registry.project(context):
        if definition.meta.side_effects & require:
            # Use the canonical name: that is the StructuredTool name the model
            # sees (the bare alias is excluded by the middleware), so DeepAgents
            # interrupt_on must match the canonical name.
            interrupt[definition.meta.canonical_name] = True
    return interrupt or None


def _replace_contract_for_controlled(
    contract: AgentRuntimeContract,
    *,
    tools: list[Any],
    middleware: list[Any],
    interrupt_on: dict[str, Any] | None = None,
) -> AgentRuntimeContract:
    """Return a copy of ``contract`` with controlled-mode tools/middleware applied."""
    effective_middleware = [mw for mw in middleware if mw is not None]
    return dataclass_replace(
        contract,
        tools=tools,
        middleware=effective_middleware,
        interrupt_on=interrupt_on,
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
        training_service: Any | None = None,
    ):
        self.repository = repository
        self.notify_event = notify_event
        self.model_call = model_call
        self.agent_registry = AgentRegistry()
        self.async_subagent_service = async_subagent_service
        self.interrupt_session = interrupt_session
        self.training_service = training_service
        self._compat_checkpointer_contexts: list[Any] = []
        # Per-session Tool Gateway cache (controlled mode): keyed by
        # ``(session_id, project_path)``. The gateway's in-process terminal
        # outcome cache (``_terminals``) must survive the prompt->resume turn
        # boundary — every resume re-runs ``_apply_controlled_cutover`` and a
        # fresh ToolGateway here would wipe the cache, re-issuing ``ask``
        # approvals forever. Restarts (lost process state) still lose this
        # cache; recovery then routes the session to ``needs_manual_review``.
        self._controlled_tool_runtimes: dict[tuple[str, str], _ControlledToolRuntime] = {}
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
            summary = self._enrich_summary(session_id, summary, status="completed")
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
            summary = self._enrich_summary(
                session_id,
                last_summary or "DeepAgents 已继续执行并完成。",
                status="completed",
            )
            mapper.complete_summary(summary)
            self.state_machine.mark_completed(session_id)
            return self._with_parts(session_id)

    def _enrich_summary(self, session_id: str, content: str, *, status: str) -> str:
        try:
            from agent_session.session_progress import enrich_final_summary

            session = self.repository.get_session(session_id) or {}
            return enrich_final_summary(
                content,
                dict(session.get("metadata") or {}),
                status=status,
            )
        except Exception:
            return content

    async def _build_graph(self, session: dict[str, Any], prompt: str, *, checkpointer: Any | None = None) -> Any:
        _load_create_deep_agent()
        session_id = str(session.get("id"))
        project_path = str(session.get("project_path") or Path.cwd())
        agent_id = str(session.get("agent_id") or "build")
        agent = self.agent_registry.get(agent_id)
        metadata = dict(session.get("metadata") or {})
        if training_tools_enabled_for_session({**session, "metadata": metadata}):
            metadata = training_submission_interrupt_metadata(metadata)
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
            self._persist_execution_trace(
                session_id,
                {
                    "model_entry": "injected_model_call",
                    "path": "injected",
                    "fallback_used": False,
                    "provider": str(session.get("provider") or ""),
                    "model": session.get("model"),
                },
            )
        elif context.provider:
            model = get_chat_model(context)
            try:
                from agent_session.model_adapter import get_last_chat_model_resolution

                resolution = get_last_chat_model_resolution()
            except Exception:
                resolution = None
            if resolution:
                self._persist_execution_trace(session_id, resolution)
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
            session={**session, "metadata": metadata},
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
        if contract.orchestration_mode == "controlled":
            contract = self._apply_controlled_cutover(contract, session_id, project_path, agent_id, metadata)
        self._persist_shadow_projection(session_id, contract)
        return build_deep_agent_runtime(contract)

    def _apply_controlled_cutover(
        self,
        contract: AgentRuntimeContract,
        session_id: str,
        project_path: str,
        agent_id: str,
        metadata: dict[str, Any],
    ) -> AgentRuntimeContract:
        """Substitute platform-managed tools (via Tool Gateway) for the legacy built-ins.

        Falls back to legacy if the startup gate cannot verify that every
        legacy built-in is excluded from the model catalog.
        """
        from tool_platform.adapters.deepagents import (
            controlled_mode_exclusion_set,
            verify_controlled_mode_exclusion,
        )

        exclusion_set = controlled_mode_exclusion_set()
        missing = verify_controlled_mode_exclusion(exclusion_set)
        if missing:
            logger.warning(
                "controlled mode startup gate failed for session %s; missing exclusions: %s. Falling back to legacy.",
                session_id,
                ", ".join(missing),
            )
            return _downgrade_contract_to_legacy(contract)

        try:
            from tool_platform.builtins import (
                make_execute_handlers,
                make_filesystem_handlers,
                make_git_handlers,
                make_write_handlers,
                platform_builtin_registry,
            )
            from tool_platform.builtins.gateway_tools import build_gateway_tool_structures
            from tool_platform.gateway import ToolGateway

            from .permission import policy_facts_for_session

            # Reuse the per-session Tool Gateway across prompts/resumes.  The
            # gateway owns the in-process terminal-outcome cache used by HITL
            # replay; recreating it on every resume would wipe that cache and
            # turn any ``ask`` policy decision into an infinite approval loop.
            cache_key = (session_id, str(project_path))
            runtime = getattr(self, "_controlled_tool_runtimes", {}).get(cache_key)
            cache = getattr(self, "_controlled_tool_runtimes", None)
            if cache is None:
                cache = {}
                self._controlled_tool_runtimes = cache
            if runtime is None:
                handlers = {
                    **make_filesystem_handlers(project_path),
                    **make_write_handlers(project_path),
                    **make_git_handlers(project_path, extra_roots=[project_path]),
                    **make_execute_handlers(project_path),
                }
                mapper = DeepAgentsEventMapper(self.repository, self.notify_event, session_id)
                gateway = ToolGateway(
                    platform_builtin_registry(),
                    mapper.publish_tool_event,
                    handlers=handlers,
                )
                runtime = _ControlledToolRuntime(
                    gateway=gateway,
                    registry=platform_builtin_registry(),
                    mapper=mapper,
                )
                cache[cache_key] = runtime
            facts = policy_facts_for_session(
                metadata,
                enforcement_status="controlled",
                runtime_kind="agent_session",
                enabled_capabilities=frozenset({"deepagents"}),
            )
        except Exception:
            logger.exception(
                "controlled mode tool assembly failed for session %s; falling back to legacy.",
                session_id,
            )
            return _downgrade_contract_to_legacy(contract)

        controlled_middleware = [*contract.middleware]
        # Replace the legacy builtin exclusion with the controlled full set so
        # no legacy built-in (incl. execute/task/write_todos) is model-visible.
        controlled_middleware = [
            mw for mw in controlled_middleware if not _is_tool_exclusion_middleware(mw)
        ]
        exclusion_middleware = _build_exclusion_middleware(exclusion_set, logger)
        if exclusion_middleware is None:
            # Fail-closed: if the exclusion middleware cannot be constructed,
            # the legacy built-ins would stay model-visible and bypass the
            # Tool Gateway. Downgrade to legacy rather than run controlled
            # without enforcement.
            logger.warning(
                "controlled mode exclusion middleware unavailable for session %s; falling back to legacy.",
                session_id,
            )
            return _downgrade_contract_to_legacy(contract)
        controlled_middleware.append(exclusion_middleware)

        # P0-2: route the Gateway's ``ask`` decisions through DeepAgents HITL.
        # Tools whose side effects intersect the session's
        # ``require_approval_for`` are declared in ``interrupt_on`` so DeepAgents
        # suspends the run *before* the tool executes (waiting_approval -> UI
        # approve -> resume). The Gateway is then run with a facts copy that
        # clears ``require_approval_for``: by the time a tool call reaches the
        # Gateway, HITL has already approved it, so the Gateway only enforces
        # allow/deny + dispatch. This avoids the needs_approval death-loop
        # where a SuspendedApprovalAdapter never grants and the model retries.
        interrupt_on = _controlled_interrupt_on(runtime.registry, facts)
        gateway_facts = facts.model_copy(update={"require_approval_for": frozenset()})
        allowed_tool_names: frozenset[str] | None = None
        if getattr(contract, "phase_projection_application", "none") == "next_runtime_contract":
            projection = parse_phase_tool_projection(
                getattr(contract, "phase_tool_projection", None) or (contract.metadata or {}).get("phase_tool_projection")
            )
            if projection is not None:
                allowed_tool_names = frozenset(projection.allowed_tools)
        gateway_tools = build_gateway_tool_structures(
            gateway=runtime.gateway,
            registry=runtime.registry,
            facts=gateway_facts,
            agent_id=agent_id,
            allowed_tool_names=allowed_tool_names,
        )
        return _replace_contract_for_controlled(
            contract,
            tools=[*contract.tools, *gateway_tools],
            middleware=controlled_middleware,
            interrupt_on=interrupt_on,
        )

    def _persist_shadow_projection(self, session_id: str, contract: AgentRuntimeContract) -> None:
        """Bind the read-only shadow tool projection to session metadata.

        Shadow mode compiles a deterministic snapshot for later offline
        comparison; it never changes the DeepAgents execution path. Legacy
        mode (no projection) assigns nothing.
        """
        projection = getattr(contract, "tool_projection", None)
        mode = getattr(contract, "orchestration_mode", "legacy")
        if projection is None or mode != "shadow":
            return
        try:
            session = self.repository.get_session(session_id) or {}
            metadata = dict(session.get("metadata") or {})
            if "tool_platform_shadow" in metadata:
                return
            metadata["tool_platform_shadow"] = projection.diagnostic_dump()
            self.repository.update_session(session_id, metadata=metadata)
        except Exception:
            logger.exception("Failed to persist shadow tool projection for session %s", session_id)

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
            if any(issue.get("reason_code") == "diff_coverage_required" for issue in issues):
                # An Agent cannot reconstruct a missing immutable record after
                # the write boundary.  Do not send it through a second tool
                # loop; retain the existing manual-review terminal path.
                self._mark_trajectory_manual_review(session_id, issues, store)
                return False, last_summary
            state = store.load()
            correction_count = int(state.get("auto_corrections") or 0)
            if correction_count >= int(policy.get("max_auto_corrections") or 0):
                self._mark_trajectory_manual_review(session_id, issues, store)
                return False, last_summary
            attempt = store.increment_correction(issues)
            prompt = self._trajectory_correction_prompt(issues, attempt, session_id=session_id)
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

    def _trajectory_correction_prompt(
        self,
        issues: list[dict[str, Any]],
        attempt: int,
        *,
        session_id: str | None = None,
    ) -> str:
        issue_text = "\n".join(
            f"- {issue.get('message')} 涉及：{', '.join(issue.get('paths') or [])}"
            for issue in issues
        )
        card = ""
        rec_section = ""
        multi_blurb = ""
        if session_id:
            try:
                from agent_session.session_progress import build_working_state_card
                from agent_session.task_scope import (
                    format_verify_recommendations_section,
                    get_task_scope,
                    recommend_verify_commands,
                )

                session = self.repository.get_session(session_id) or {}
                metadata = dict(session.get("metadata") or {})
                card = build_working_state_card(metadata)
                # Collect paths from issues + trajectory writes for B2 recommendations.
                issue_paths: list[str] = []
                for issue in issues:
                    for path in issue.get("paths") or []:
                        issue_paths.append(str(path))
                traj = metadata.get("trajectory_guard") if isinstance(metadata.get("trajectory_guard"), dict) else {}
                written = list((traj.get("writes") or traj.get("written_paths") or {}).keys()) if isinstance(
                    traj.get("writes") or traj.get("written_paths"), dict
                ) else list(traj.get("written_paths") or [])
                recipe = metadata.get("verify_recipe") if isinstance(metadata.get("verify_recipe"), dict) else None
                workspace = metadata.get("workspace") if isinstance(metadata.get("workspace"), dict) else {}
                rec = recommend_verify_commands(
                    written_paths=issue_paths or written,
                    recipe=recipe,
                    project_path=workspace.get("path") or session.get("project_path"),
                    scope=get_task_scope(metadata),
                )
                rec_section = format_verify_recommendations_section(rec)
                try:
                    from agent_session.multi_file import (
                        build_multi_file_state,
                        multi_file_correction_blurb,
                    )

                    multi_blurb = multi_file_correction_blurb(
                        build_multi_file_state(
                            metadata,
                            project_path=workspace.get("path") or session.get("project_path"),
                        )
                    )
                except Exception:
                    multi_blurb = ""
            except Exception:
                card = ""
                rec_section = ""
                multi_blurb = ""
        card_block = f"\n{card}\n" if card else "\n"
        rec_block = f"\n{rec_section}\n" if rec_section else "\n"
        multi_block = f"\n{multi_blurb}\n" if multi_blurb else "\n"
        return (
            f"这是第 {attempt} 次轨迹自动纠正。你刚才准备结束任务，但尚未满足平台验证要求：\n"
            f"{issue_text}\n"
            f"{card_block}"
            f"{rec_block}"
            f"{multi_block}"
            "请立即完成缺失的验证。优先执行上方「相关验证推荐」中的命令（可再缩小到改动路径）；"
            "不要无目标全仓扫描。文档可重新读取最终内容确认。若验证失败，先重新读取受影响文件，再修复并重新验证。"
            "不要只解释计划，必须实际执行验证。"
        )

    def _local_async_tools_for_session(self, session: dict[str, Any]) -> list[Any]:
        agent_id = str(session.get("agent_id") or "build")
        agent = self.agent_registry.get(agent_id)
        manifest = async_subagent_manifest_for_agent(self.agent_registry, agent)

        from langchain_core.tools import StructuredTool

        session_id = str(session.get("id"))
        tools: list[Any] = []
        if manifest.enabled:
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

        if manifest.enabled:
            available = manifest.available_label()
            tools.extend(
                [
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
            )
        if training_tools_enabled_for_session(session):
            if self.training_service is None:
                from agent_training.service import AgentTrainingService

                self.training_service = AgentTrainingService()
            tools.extend(
                build_training_tools(
                    session,
                    repository=self.repository,
                    training_service=self.training_service,
                )
            )
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

    def _persist_execution_trace(self, session_id: str, resolution: dict[str, Any]) -> None:
        """Merge non-secret model resolution facts into session execution_trace (Phase 4)."""
        try:
            session = self.repository.get_session(session_id) or {}
            metadata = dict(session.get("metadata") or {})
            trace = dict(metadata.get("execution_trace") or {})
            # Never persist raw api keys if a caller accidentally passed one.
            safe = {
                key: value
                for key, value in resolution.items()
                if key not in {"api_key", "openai_api_key"} and value is not None
            }
            if "base_url" in safe and isinstance(safe["base_url"], str):
                # Keep host path only for diagnostics (no query secrets expected).
                safe["base_url"] = safe["base_url"][:240]
            if "last_model_error" in safe and isinstance(safe["last_model_error"], str):
                safe["last_model_error"] = safe["last_model_error"][:600]
            if "official_error" in safe and isinstance(safe["official_error"], str):
                safe["official_error"] = safe["official_error"][:400]
            trace.update(safe)
            metadata["execution_trace"] = trace
            self.repository.update_session(session_id, metadata=metadata)
        except Exception:
            # Trace enrichment must never break graph construction.
            pass

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
