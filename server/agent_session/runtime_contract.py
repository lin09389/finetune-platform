from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .agent_registry import AgentRegistry
from .async_subagent_policy import ASYNC_SUBAGENT_TOOL_NAMES, async_subagent_manifest_for_agent
from .execution_context import AgentDefinition
from .permission import AgentRuntimePermissionPolicy, permission_policy_for_agent
from .phase_controller import parse_phase_state
from .phase_tool_router import parse_phase_tool_projection
from .runtime_policy import AgentRuntimePolicy, build_agent_runtime_policy, enabled_skill_paths
from .tool_projection import compile_session_tool_projection

RuntimeKind = Literal["agent_session", "project_chat"]
BackendMode = Literal["workspace", "project_chat_readonly"]
OrchestrationMode = Literal["legacy", "shadow", "controlled"]

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
    "命令本身不再走平台白名单，但高风险动作仍可能命中 HITL 人工审批。"
    "执行命令前优先说明意图，执行后根据 execute 输出继续判断。"
)


def build_execution_prompt() -> str:
    """Return the execution prompt with platform-specific shell guidance.

    The filesystem prompt tells the model to use ``/workspace/...`` for file
    tools, and the ``PlatformShellBackend`` rewrites those paths in ``execute``
    commands automatically. But the model also needs to know *which shell* it
    is targeting so it writes compatible command syntax:

    - WSL mode (Windows + ``SANDBOX_EXECUTION_MODE=wsl``): real Linux ``bash``,
      so ``ls``/``cat``/``grep``/pipes/heredocs all work natively.
    - Windows local: ``cmd.exe`` -- avoid Unix commands; use ``&&`` not ``;``.
    - POSIX: standard ``/bin/sh``.

    This is advisory (the path rewrite is the structural guarantee), but it
    reduces the number of failed attempts before the model converges.
    """
    base = EXECUTION_PROMPT
    # Check WSL mode first -- it takes precedence over the win32 default.
    try:
        from core.config import settings

        wsl_mode = settings.sandbox_execution_mode == "wsl" and sys.platform == "win32"
    except Exception:
        wsl_mode = False

    if wsl_mode:
        return (
            base
            + "execute 运行在 WSL2 Linux (bash) 环境。命令中的 `/workspace/...` 路径会自动映射到项目真实路径。"
            "你可以使用标准 Unix 命令（ls/cat/grep/管道/heredoc 等），工作目录已是项目根。"
            "WSL 只是命令兼容环境，不是额外的安全边界；仍必须遵守 Workspace 和审批策略。"
        )
    if sys.platform == "win32":
        return (
            base
            + "execute 运行在 Windows cmd 环境。命令中的 `/workspace/...` 路径会自动映射到项目真实路径，"
            "优先使用相对路径（工作目录已是项目根）。"
            "不要用 `ls`/`cat`/`grep` 等 Unix 命令做文件操作，改用内置的 ls/read_file/grep 工具。"
            "多条命令用 `&&` 分隔，不要用 `;`。"
        )
    return base + "execute 运行在 POSIX shell 环境。命令中的 `/workspace/...` 路径会自动映射到项目真实路径。"
PROJECT_CHAT_PROMPT = (
    "你是 Finetune Platform 的只读项目讨论助手。"
    "用户在普通 Chat 中讨论项目时，你可以使用 DeepAgents 官方文件系统工具查看项目。"
    "真实项目根目录挂载在 `/workspace/`，优先使用 ls、glob、grep、read_file 理解代码。"
    "上下文文件可能位于 `/context/`。"
    "你禁止写入文件、编辑文件或执行命令；不要调用 write_file、edit_file、execute。"
    "如果用户需要修改代码、安装依赖、运行测试或执行命令，请明确说明需要升级为 Agent Task。"
    "回答时直接给出基于项目文件的结论，并尽量引用具体文件路径。"
)
REASONING_PROMPT = (
    "【强制推理规范】在调用任何工具之前，你必须先进行简短的内部思考规划（Chain of Thought）。想清楚你目前的进展是什么，"
    "下一步需要哪些信息或操作，为什么要这么做，预期的结果是什么。这能帮助你避免迷失方向。"
)
ERROR_RECOVERY_PROMPT = (
    "【强制错误恢复机制】如果执行工具报错（例如 execute 失败、edit_file 后出现语法错误、grep 找不到预期内容），"
    "绝对禁止盲目重试或瞎猜修改。你必须立刻停下来，使用 read_file/grep/ls 检查具体报错与真实代码内容，理清原因后再尝试修复。"
    "平台会拦截：execute 失败后在未重新观察（read_file/grep/ls/glob）前的任何再次 execute（不限是否同一命令）；"
    "以及超出探索预算的无效扫描。"
    "最终摘要必须包含「已完成项」「变更文件」「验证结果」；有源码写入时必须实际验证通过后再收尾。"
)


def _agent_required_sections(agent: AgentDefinition | None) -> tuple[str, ...]:
    """Return the manifest-declared required summary sections for an agent.

    Falls back to the Build trio when the agent is unknown or declares none.
    """
    if agent is None:
        return ("已完成项", "变更文件", "验证结果")
    sections = agent.output_schema.get("required_sections") if isinstance(agent.output_schema, dict) else None
    if not sections or not isinstance(sections, list | tuple):
        return ("已完成项", "变更文件", "验证结果")
    return tuple(str(s).strip() for s in sections if str(s).strip())


def build_error_recovery_prompt(agent: AgentDefinition | None = None) -> str:
    """Per-agent error-recovery prompt.

    The base discipline (no blind retry, re-observe before re-executing) is
    shared, but the final-summary section contract is derived from the agent's
    manifest so Explore quotes its own sections instead of Build-only ones.
    """
    sections = _agent_required_sections(agent)
    sections_text = "「" + "」「".join(sections) + "」"
    recovery = (
        "【强制错误恢复机制】如果执行工具报错（例如 execute 失败、edit_file 后出现语法错误、grep 找不到预期内容），"
        "绝对禁止盲目重试或瞎猜修改。你必须立刻停下来，使用 read_file/grep/ls 检查具体报错与真实代码内容，理清原因后再尝试修复。"
        "平台会拦截：execute 失败后在未重新观察（read_file/grep/ls/glob）前的任何再次 execute（不限是否同一命令）；"
        "以及超出探索预算的无效扫描。"
    )
    if agent is not None and agent.id == "explore":
        # Explore is read-only: no source writes, so the gate is about
        # evidence-backed conclusions rather than write/verify.
        recovery += f"最终摘要必须包含{sections_text}；结论必须有文件证据支撑，不要臆测。"
    elif agent is not None and agent.id == "review":
        recovery += f"最终摘要必须包含{sections_text}；风险必须有代码证据，验证建议必须可执行。"
    else:
        recovery += f"最终摘要必须包含{sections_text}；有源码写入时必须实际验证通过后再收尾。"
    return recovery


@dataclass(frozen=True)
class AgentRuntimeContract:
    runtime_kind: RuntimeKind
    session_id: str
    project_path: str
    model: Any
    system_prompt: str
    memory: list[str]
    checkpointer: Any
    user_id: str = "default"
    agent_id: str = "build"
    org_id: str = "default-org"
    agent: AgentDefinition | None = None
    metadata: dict[str, Any] | None = None
    tools: list[Any] | None = None
    permissions: list[Any] | None = None
    middleware: list[Any] | None = None
    skills: list[str] | None = None
    enabled_skill_sources: list[str] | None = None
    subagents: list[dict[str, Any]] | None = None
    interrupt_on: dict[str, Any] | None = None
    backend_mode: BackendMode = "workspace"
    graph_thread_id: str | None = None
    recursion_limit: int | None = None
    runtime_policy: AgentRuntimePolicy | None = None
    orchestration_mode: OrchestrationMode = "legacy"
    tool_projection: Any = None
    phase_state: dict[str, Any] | None = None
    phase_tool_projection: dict[str, Any] | None = None
    phase_projection_application: Literal["none", "shadow", "next_runtime_contract", "blocked"] = "none"

    @classmethod
    def for_agent_session(
        cls,
        *,
        session: dict[str, Any],
        goal: str,
        model: Any,
        agent_registry: AgentRegistry,
        tools: list[Any],
        middleware: list[Any],
        subagents: list[dict[str, Any]],
        checkpointer: Any,
    ) -> AgentRuntimeContract:
        _ = goal
        session_id = str(session.get("id"))
        project_path = str(session.get("project_path") or Path.cwd())
        metadata = dict(session.get("metadata") or {})
        agent_id = str(session.get("agent_id") or "build")
        agent = agent_registry.get(agent_id)
        validate_agent_launch(agent, agent_id, metadata)
        enabled_skill_sources = normalize_enabled_skill_sources(metadata.get("enabled_skill_sources"))
        user_id = str(metadata.get("user_id") or metadata.get("memory_user_id") or "default")
        org_id = str(metadata.get("org_id") or "default-org")
        permission_policy = permission_policy_for_agent(agent, agent_id, metadata)
        permission_policy.validate_enabled_skills(project_path, enabled_skill_sources)
        orchestration_mode = resolve_orchestration_mode(metadata)
        tool_projection = None
        if orchestration_mode != "legacy":
            tool_projection = compile_session_tool_projection(
                agent_registry=agent_registry,
                agent_id=agent_id,
                metadata=metadata,
                orchestration_mode=orchestration_mode,
            )
        runtime_policy = build_agent_runtime_policy(
            agent=agent,
            agent_id=agent_id,
            project_path=project_path,
            metadata=metadata,
            provider=str(session.get("provider") or ""),
            model=session.get("model"),
            runtime_kind="agent_session",
            thread_id=f"agent_session:{session_id}:deepagents",
            checkpointer=True,
            agent_registry=agent_registry,
        )
        filtered_tools = permission_policy.filter_named_tools(tools)
        phase_state = parse_phase_state(metadata.get("phase_state"))
        phase_tool_projection = parse_phase_tool_projection(metadata.get("phase_tool_projection"))
        phase_application: Literal["none", "shadow", "next_runtime_contract", "blocked"] = "none"
        if phase_tool_projection is not None:
            phase_application = phase_tool_projection.application
            if phase_application == "next_runtime_contract" and orchestration_mode == "controlled":
                if phase_tool_projection.application == "blocked":
                    filtered_tools = []
                else:
                    allowed = frozenset(phase_tool_projection.allowed_tools)
                    filtered_tools = _filter_named_tools(filtered_tools, allowed)
        return cls(
            runtime_kind="agent_session",
            session_id=session_id,
            project_path=project_path,
            model=model,
            system_prompt=build_system_prompt(agent_registry, agent, metadata=metadata),
            memory=runtime_policy.memory_files,
            checkpointer=checkpointer,
            user_id=user_id,
            agent_id=agent_id,
            org_id=org_id,
            agent=agent,
            metadata=metadata,
            tools=filtered_tools,
            permissions=permission_policy.filesystem_permissions(),
            middleware=middleware,
            skills=enabled_skill_paths(runtime_policy),
            enabled_skill_sources=runtime_policy.enabled_skill_sources,
            subagents=subagents,
            interrupt_on=runtime_policy.interrupt_on,
            backend_mode=runtime_policy.execution_plan.backend_mode,
            graph_thread_id=runtime_policy.execution_plan.thread_id,
            recursion_limit=runtime_policy.execution_plan.recursion_limit,
            runtime_policy=runtime_policy,
            orchestration_mode=orchestration_mode,
            tool_projection=tool_projection,
            phase_state=phase_state.model_dump(mode="json") if phase_state else None,
            phase_tool_projection=phase_tool_projection.model_dump(mode="json") if phase_tool_projection else None,
            phase_projection_application=phase_application,
        )

    @classmethod
    def for_project_chat(
        cls,
        *,
        project_path: str,
        model: Any,
        metadata: dict[str, Any] | None = None,
        session_id: str = "project_chat",
    ) -> AgentRuntimeContract:
        root = str(Path(project_path).resolve())
        permission_policy = permission_policy_for_agent(None, "project_chat", dict(metadata or {}))
        runtime_policy = build_agent_runtime_policy(
            agent=None,
            agent_id="project_chat",
            project_path=root,
            metadata=metadata,
            runtime_kind="project_chat",
            thread_id=session_id,
            checkpointer=False,
        )
        return cls(
            runtime_kind="project_chat",
            session_id=session_id,
            project_path=root,
            model=model,
            system_prompt=PROJECT_CHAT_PROMPT,
            memory=runtime_policy.memory_files,
            checkpointer=False,
            agent_id="project_chat",
            metadata=dict(metadata or {}),
            tools=[],
            permissions=permission_policy.filesystem_permissions(),
            backend_mode=runtime_policy.execution_plan.backend_mode,
            graph_thread_id=runtime_policy.execution_plan.thread_id,
            runtime_policy=runtime_policy,
        )


def _filter_named_tools(tools: list[Any], allowed_names: frozenset[str]) -> list[Any]:
    filtered: list[Any] = []
    for tool in tools:
        name = getattr(tool, "name", None)
        if name is None and isinstance(tool, dict):
            name = tool.get("name")
        if name is not None and str(name) in allowed_names:
            filtered.append(tool)
    return filtered


def normalize_enabled_skill_sources(value: Any) -> list[str] | None:
    if value is None or not isinstance(value, list):
        return None
    return [str(item).strip() for item in value if str(item).strip()]


def resolve_orchestration_mode(metadata: dict[str, Any]) -> OrchestrationMode:
    """Resolve the session tool-orchestration mode (metadata wins, then settings).

    - ``legacy`` (default): no binding, zero behaviour change.
    - ``shadow``: bind a read-only projection snapshot; DeepAgents still runs.
    - ``controlled``: the Tool Gateway is the execution path; the legacy
      ``execute`` entry is blocked at the backend layer (Task 9C). Task 9D
      adds the atomic startup gate that refuses controlled launch unless every
      Build tool has a hard enforcement boundary; until then a controlled
      session compiles its projection and blocks the legacy execute entry but
      does not yet reroute the model tool catalog.
    """
    raw = str(metadata.get("orchestration_mode") or "").strip().lower()
    if raw in {"shadow", "controlled"}:
        return raw  # type: ignore[return-value]
    try:
        from core.config import settings

        configured = str(getattr(settings, "agent_tool_orchestration_mode", "") or "").strip().lower()
        if configured in {"shadow", "controlled"}:
            return configured  # type: ignore[return-value]
    except Exception:
        pass
    return "legacy"


def validate_agent_launch(agent: AgentDefinition | None, agent_id: str, metadata: dict[str, Any]) -> None:
    if agent is None:
        raise ValueError(f"Unknown agent id: {agent_id}")
    if metadata.get("async_subagent"):
        if not agent.can_be_handoff_target:
            raise ValueError(f"Agent '{agent_id}' cannot run as a subagent in mode '{agent.mode}'")
        return
    if not agent.can_start_directly:
        raise ValueError(f"Agent '{agent_id}' cannot be started directly in mode '{agent.mode}'")


def recursion_limit_for_agent(agent: AgentDefinition | None) -> int | None:
    if agent is None:
        return None
    return max(2, int(agent.max_iterations)) * 4 + 8


def agent_system_prompt(agent: AgentDefinition) -> str:
    prompt = agent.system_prompt.strip()
    requirements = agent.output_requirements.strip()
    if not requirements:
        return prompt
    return f"{prompt}\n\n## 输出要求\n{requirements}" if prompt else f"## 输出要求\n{requirements}"


def platform_prompt_sections(agent: AgentDefinition | None = None) -> list[str]:
    return [
        PLATFORM_IDENTITY_PROMPT,
        REASONING_PROMPT,
        FILESYSTEM_PROMPT,
        CONTEXT_PROMPT,
        SKILLS_PROMPT,
        build_execution_prompt(),
        build_error_recovery_prompt(agent),
    ]


def system_prompt_sections(
    agent_registry: AgentRegistry,
    agent: AgentDefinition | None,
    *,
    metadata: dict[str, Any] | None = None,
) -> list[str]:
    sections: list[str] = []
    if agent:
        prompt = agent_system_prompt(agent)
        if prompt:
            sections.append(prompt)
    sections.extend(platform_prompt_sections(agent))
    async_section = async_subagent_prompt(agent_registry, agent)
    if async_section:
        sections.append(async_section)
    if metadata:
        from agent_session.session_progress import build_working_state_card

        card = build_working_state_card(metadata)
        if card:
            sections.append(card)
    return sections


def build_system_prompt(
    agent_registry: AgentRegistry,
    agent: AgentDefinition | None,
    *,
    metadata: dict[str, Any] | None = None,
) -> str:
    return "\n\n".join(system_prompt_sections(agent_registry, agent, metadata=metadata))


def async_subagent_prompt(agent_registry: AgentRegistry, agent: AgentDefinition | None) -> str:
    manifest = async_subagent_manifest_for_agent(agent_registry, agent)
    if not agent or not manifest.enabled:
        return ""
    enabled_tools = set(agent.tools or [])
    if not ASYNC_SUBAGENT_TOOL_NAMES.issubset(enabled_tools):
        return ""
    available = "、".join(manifest.target_ids)
    return (
        "你还可以启动本地异步子代理任务："
        f"可用子代理类型是 {available}。"
        "使用 start_async_task 启动后台只读任务后，必须立刻把完整 task_id 告诉用户并停止，"
        "不要在同一轮里马上轮询。只有用户要求查看状态或结果时，才使用 check_async_task 或 list_async_tasks。"
        "用户要求调整或停止异步任务时，使用 update_async_task 或 cancel_async_task。"
        "不要凭历史消息报告任务状态，必须调用工具获取最新状态。"
    )


def permission_policy_for_contract(contract: AgentRuntimeContract) -> AgentRuntimePermissionPolicy:
    return permission_policy_for_agent(contract.agent, contract.agent_id, dict(contract.metadata or {}))


__all__ = [
    "AgentRuntimeContract",
    "EXECUTION_PROMPT",
    "PROJECT_CHAT_PROMPT",
    "agent_system_prompt",
    "async_subagent_prompt",
    "build_error_recovery_prompt",
    "build_execution_prompt",
    "build_system_prompt",
    "normalize_enabled_skill_sources",
    "platform_prompt_sections",
    "recursion_limit_for_agent",
    "resolve_orchestration_mode",
    "system_prompt_sections",
    "validate_agent_launch",
]
