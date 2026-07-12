from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .agent_registry import AgentRegistry
from .async_subagent_policy import ASYNC_SUBAGENT_TOOL_NAMES, async_subagent_manifest_for_agent
from .execution_context import AgentDefinition
from .permission import filesystem_permission_profile_for_agent, permission_policy_for_agent
from .runtime import (
    describe_deepagents_mounts,
    describe_skill_sources,
    memory_files_for_project,
    resolve_enabled_skill_sources,
)
from .status import SESSION_LIFECYCLE

RuntimePolicyKind = Literal["agent_session", "project_chat", "agent_definition"]
RuntimeBackendMode = Literal["workspace", "project_chat_readonly", "definition_only"]
RUNTIME_POLICY_SCHEMA_VERSION = "agent.runtime.policy.v1"
EXECUTION_PLAN_SCHEMA_VERSION = "agent.execution.plan.v1"


@dataclass(frozen=True)
class AgentExecutionPlan:
    schema_version: str = EXECUTION_PLAN_SCHEMA_VERSION
    runtime: str = "deepagents"
    backend_mode: RuntimeBackendMode = "workspace"
    thread_id: str | None = None
    recursion_limit: int | None = None
    checkpointer: bool = True
    state_machine: str = "agent_session.v1"
    plan_id: str | None = None
    session_id: str | None = None
    goal: str = ""
    status: str = "planned"
    current_node_id: str | None = None
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    lifecycle: list[str] = field(default_factory=lambda: list(SESSION_LIFECYCLE))

    def model_dump(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "runtime": self.runtime,
            "backend_mode": self.backend_mode,
            "thread_id": self.thread_id,
            "recursion_limit": self.recursion_limit,
            "checkpointer": self.checkpointer,
            "state_machine": self.state_machine,
            "plan_id": self.plan_id,
            "session_id": self.session_id,
            "goal": self.goal,
            "status": self.status,
            "current_node_id": self.current_node_id,
            "nodes": [dict(item) for item in self.nodes],
            "edges": [dict(item) for item in self.edges],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "lifecycle": list(self.lifecycle),
        }


@dataclass(frozen=True)
class AgentResourceProfile:
    schema_version: str = "agent.resource.profile.v1"
    agent: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
    skills: dict[str, Any] = field(default_factory=dict)
    mounts: list[dict[str, Any]] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "agent": dict(self.agent),
            "memory": dict(self.memory),
            "skills": dict(self.skills),
            "mounts": [dict(item) for item in self.mounts],
        }


@dataclass(frozen=True)
class AgentRuntimePolicy:
    schema_version: str = RUNTIME_POLICY_SCHEMA_VERSION
    runtime_kind: RuntimePolicyKind = "agent_session"
    agent_id: str = "build"
    agent_name: str = "Build"
    mode: str = "all"
    readonly: bool = False
    workspace_root: str | None = None
    provider: str | None = None
    model: str | None = None
    capabilities: dict[str, bool] = field(default_factory=dict)
    tools: dict[str, Any] = field(default_factory=dict)
    output_contract: dict[str, Any] = field(default_factory=dict)
    recovery_policy: dict[str, Any] = field(default_factory=dict)
    handoff_targets: list[str] = field(default_factory=list)
    async_subagent_targets: list[str] = field(default_factory=list)
    filesystem_profile: str = "deny_all"
    interrupt_on: dict[str, Any] | None = None
    enabled_skill_sources: list[str] | None = None
    skill_sources: list[dict[str, Any]] = field(default_factory=list)
    vfs_mounts: list[dict[str, Any]] = field(default_factory=list)
    memory_files: list[str] = field(default_factory=list)
    resource_profile: AgentResourceProfile = field(default_factory=AgentResourceProfile)
    execution_plan: AgentExecutionPlan = field(default_factory=AgentExecutionPlan)

    def model_dump(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "runtime_kind": self.runtime_kind,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "mode": self.mode,
            "readonly": self.readonly,
            "workspace_root": self.workspace_root,
            "provider": self.provider,
            "model": self.model,
            "capabilities": dict(self.capabilities),
            "tools": dict(self.tools),
            "output_contract": dict(self.output_contract),
            "recovery_policy": dict(self.recovery_policy),
            "handoff_targets": list(self.handoff_targets),
            "async_subagent_targets": list(self.async_subagent_targets),
            "filesystem_profile": self.filesystem_profile,
            "interrupt_on": dict(self.interrupt_on) if isinstance(self.interrupt_on, dict) else self.interrupt_on,
            "enabled_skill_sources": list(self.enabled_skill_sources) if self.enabled_skill_sources is not None else None,
            "skill_sources": [dict(item) for item in self.skill_sources],
            "vfs_mounts": [dict(item) for item in self.vfs_mounts],
            "memory_files": list(self.memory_files),
            "resource_profile": self.resource_profile.model_dump(),
            "execution_plan": self.execution_plan.model_dump(),
        }


def build_agent_runtime_policy(
    *,
    agent: AgentDefinition | None,
    agent_id: str,
    project_path: str | None = None,
    metadata: dict[str, Any] | None = None,
    provider: str | None = None,
    model: str | None = None,
    runtime_kind: RuntimePolicyKind = "agent_session",
    thread_id: str | None = None,
    checkpointer: bool = True,
    agent_registry: AgentRegistry | None = None,
) -> AgentRuntimePolicy:
    metadata = dict(metadata or {})
    effective_agent_id = agent.id if agent else agent_id
    workspace_root = str(Path(project_path).resolve()) if project_path else None
    enabled_skill_sources = _enabled_skill_sources(metadata.get("enabled_skill_sources"))
    permission_policy = permission_policy_for_agent(agent, effective_agent_id, metadata)
    manifest = async_subagent_manifest_for_agent(agent_registry or AgentRegistry(), agent)
    from .permission import is_read_only_autonomy

    readonly = (
        runtime_kind == "project_chat"
        or filesystem_permission_profile_for_agent(effective_agent_id) == "readonly"
        or is_read_only_autonomy(metadata)
    )
    backend_mode: RuntimeBackendMode = (
        "project_chat_readonly" if runtime_kind == "project_chat" else "workspace" if workspace_root else "definition_only"
    )
    capabilities = _capabilities(agent, runtime_kind=runtime_kind)
    tools = _tool_policy(agent, manifest_enabled=manifest.enabled)
    output_contract = _output_contract(agent, runtime_kind=runtime_kind)
    recovery_policy = _recovery_policy(runtime_kind=runtime_kind)
    vfs_mounts: list[dict[str, Any]] = []
    skill_sources: list[dict[str, Any]] = []
    memory_files: list[str] = []
    if workspace_root:
        vfs_mounts = describe_deepagents_mounts(
            workspace_root,
            agent_id=effective_agent_id,
            enabled_skill_sources=enabled_skill_sources,
        )
        skill_sources = describe_skill_sources(
            workspace_root,
            agent_id=effective_agent_id,
            enabled_skill_sources=enabled_skill_sources,
        )
        if runtime_kind == "project_chat":
            memory_files = ["/workspace/AGENTS.md"] if (Path(workspace_root) / "AGENTS.md").is_file() else []
        else:
            memory_files = _memory_files(workspace_root, effective_agent_id, metadata)
    resource_profile = build_agent_resource_profile(
        agent=agent,
        agent_id=effective_agent_id,
        runtime_kind=runtime_kind,
        workspace_root=workspace_root,
        metadata=metadata,
        enabled_skill_sources=enabled_skill_sources,
        skill_sources=skill_sources,
        vfs_mounts=vfs_mounts,
        memory_files=memory_files,
    )
    return AgentRuntimePolicy(
        runtime_kind=runtime_kind,
        agent_id=effective_agent_id,
        agent_name=agent.name if agent else ("Project Chat" if runtime_kind == "project_chat" else effective_agent_id),
        mode=agent.mode if agent else ("subagent" if runtime_kind == "project_chat" else "all"),
        readonly=readonly,
        workspace_root=workspace_root,
        provider=provider,
        model=model,
        capabilities=capabilities,
        tools=tools,
        output_contract=output_contract,
        recovery_policy=recovery_policy,
        handoff_targets=list(agent.handoff_targets if agent else []),
        async_subagent_targets=list(agent.async_subagent_targets if agent else []),
        filesystem_profile=filesystem_permission_profile_for_agent(effective_agent_id),
        interrupt_on=permission_policy.interrupt_on(),
        enabled_skill_sources=enabled_skill_sources,
        skill_sources=skill_sources,
        vfs_mounts=vfs_mounts,
        memory_files=memory_files,
        resource_profile=resource_profile,
        execution_plan=AgentExecutionPlan(
            backend_mode=backend_mode,
            thread_id=thread_id,
            recursion_limit=recursion_limit_for_agent(agent),
            checkpointer=checkpointer,
        ),
    )


def build_agent_resource_profile(
    *,
    agent: AgentDefinition | None,
    agent_id: str,
    runtime_kind: RuntimePolicyKind = "agent_session",
    workspace_root: str | None = None,
    metadata: dict[str, Any] | None = None,
    enabled_skill_sources: list[str] | None = None,
    skill_sources: list[dict[str, Any]] | None = None,
    vfs_mounts: list[dict[str, Any]] | None = None,
    memory_files: list[str] | None = None,
) -> AgentResourceProfile:
    metadata = dict(metadata or {})
    user_id = str(metadata.get("user_id") or metadata.get("memory_user_id") or "default")
    org_id = str(metadata.get("org_id") or "default-org")
    return AgentResourceProfile(
        agent={
            "id": agent.id if agent else agent_id,
            "name": agent.name if agent else ("Project Chat" if runtime_kind == "project_chat" else agent_id),
            "mode": agent.mode if agent else ("subagent" if runtime_kind == "project_chat" else "all"),
            "description": agent.description if agent else "",
        },
        memory={
            "user_id": user_id,
            "agent_id": agent.id if agent else agent_id,
            "org_id": org_id,
            "namespaces": [
                {"scope": "user", "namespace": user_id, "mount": "/memories/", "writable": runtime_kind != "project_chat"},
                {"scope": "agent", "namespace": agent.id if agent else agent_id, "mount": "/agent-memory/", "writable": runtime_kind != "project_chat"},
                {"scope": "org", "namespace": org_id, "mount": "/policies/", "writable": False},
            ],
            "files": list(memory_files or []),
        },
        skills={
            "enabled_skill_sources": list(enabled_skill_sources) if enabled_skill_sources is not None else None,
            "sources": [dict(item) for item in skill_sources or []],
        },
        mounts=[dict(item) for item in vfs_mounts or []],
    )


def build_agent_definition_policy(agent: AgentDefinition) -> dict[str, Any]:
    return build_agent_runtime_policy(agent=agent, agent_id=agent.id, runtime_kind="agent_definition").model_dump()


def enabled_skill_paths(policy: AgentRuntimePolicy) -> list[str]:
    if policy.workspace_root is None:
        return []
    return resolve_enabled_skill_sources(
        policy.workspace_root,
        agent_id=policy.agent_id,
        enabled_skill_sources=policy.enabled_skill_sources,
    )


def recursion_limit_for_agent(agent: AgentDefinition | None) -> int | None:
    if agent is None:
        return None
    return max(2, int(agent.max_iterations)) * 4 + 8


def _enabled_skill_sources(value: Any) -> list[str] | None:
    if value is None or not isinstance(value, list):
        return None
    return [str(item).strip() for item in value if str(item).strip()]


def _capabilities(agent: AgentDefinition | None, *, runtime_kind: RuntimePolicyKind) -> dict[str, bool]:
    if runtime_kind == "project_chat":
        return {
            "can_start_directly": False,
            "can_delegate": False,
            "can_be_handoff_target": False,
            "can_read_workspace": True,
            "can_write_workspace": False,
            "can_execute_commands": False,
            "can_use_async_subagents": False,
        }
    if agent is None:
        return {}
    allowed_tools = set(agent.tools or [])
    return {
        "can_start_directly": agent.can_start_directly,
        "can_delegate": agent.can_delegate,
        "can_be_handoff_target": agent.can_be_handoff_target,
        "can_read_workspace": not allowed_tools or bool({"read_file", "grep", "glob", "ls"} & allowed_tools),
        "can_write_workspace": not allowed_tools or bool({"write_file", "edit_file"} & allowed_tools),
        "can_execute_commands": not allowed_tools or "execute" in allowed_tools,
        "can_use_async_subagents": bool(ASYNC_SUBAGENT_TOOL_NAMES.issubset(allowed_tools)),
    }


def _tool_policy(agent: AgentDefinition | None, *, manifest_enabled: bool) -> dict[str, Any]:
    allowed = list(agent.tools if agent else [])
    return {
        "allowed": allowed,
        "allow_all_builtin": not allowed,
        "async_tools_enabled": bool(agent and manifest_enabled and ASYNC_SUBAGENT_TOOL_NAMES.issubset(set(allowed))),
        "async_tool_names": sorted(ASYNC_SUBAGENT_TOOL_NAMES),
    }


def _output_contract(agent: AgentDefinition | None, *, runtime_kind: RuntimePolicyKind) -> dict[str, Any]:
    if runtime_kind == "project_chat":
        return {
            "source": "project_chat",
            "format": "plain_text",
            "requirements": "回答时直接给出基于项目文件的结论，并尽量引用具体文件路径。",
            "enforced_in_prompt": True,
        }
    requirements = str(agent.output_requirements if agent else "").strip()
    output_schema = dict(agent.output_schema if agent else {})
    required_sections = _clean_string_list(output_schema.get("required_sections"))
    required_fields = _clean_string_list(output_schema.get("required_fields"))
    schema_payload = output_schema.get("schema") if isinstance(output_schema.get("schema"), dict) else {}
    reflection_rules = dict(agent.reflection_rules if agent else {})
    reflection_rule_count = _reflection_rule_count(reflection_rules)
    few_shot_count = len(agent.few_shot_examples if agent else [])
    return {
        "source": "agent_definition",
        "schema_version": agent.schema_version if agent else 1,
        "definition_format": agent.definition_format if agent else "runtime",
        "format": str(output_schema.get("format") or ("agent_defined" if requirements else "plain_text")),
        "requirements": requirements or "返回面向用户的简洁任务总结；如产生文件、命令、风险或后续动作，应在总结中明确说明。",
        "required_sections": required_sections,
        "required_fields": required_fields,
        "schema": schema_payload,
        "few_shot_examples": few_shot_count,
        "reflection_rules": reflection_rule_count,
        "trajectory_policy": dict(agent.trajectory_policy if agent else {}),
        "enforced_in_prompt": bool(requirements),
    }


def _clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _reflection_rule_count(reflection_rules: dict[str, Any]) -> int:
    total = 0
    for key in ("before_tool_use", "before_edit", "before_final", "on_error", "rules"):
        value = reflection_rules.get(key)
        if isinstance(value, list):
            total += len([item for item in value if item])
    sections = reflection_rules.get("sections")
    if isinstance(sections, dict):
        for value in sections.values():
            if isinstance(value, list):
                total += len([item for item in value if item])
            elif value:
                total += 1
    return total


def _recovery_policy(*, runtime_kind: RuntimePolicyKind) -> dict[str, Any]:
    if runtime_kind == "project_chat":
        return {
            "failure_status": "failed",
            "manual_review_status": None,
            "resume_after_permission": False,
            "restart_recovery": False,
            "records_fallback_summary": False,
        }
    return {
        "failure_status": "needs_manual_review",
        "manual_review_status": "needs_manual_review",
        "resume_after_permission": True,
        "restart_recovery": True,
        "records_fallback_summary": True,
        "state_machine": "agent_session.v1",
    }


def _memory_files(workspace_root: str, agent_id: str, metadata: dict[str, Any]) -> list[str]:
    try:
        return memory_files_for_project(
            workspace_root,
            user_id=str(metadata.get("user_id") or metadata.get("memory_user_id") or "default"),
            agent_id=agent_id,
            org_id=str(metadata.get("org_id") or "default-org"),
        )
    except Exception:
        return []


__all__ = [
    "AgentExecutionPlan",
    "AgentResourceProfile",
    "AgentRuntimePolicy",
    "build_agent_resource_profile",
    "build_agent_definition_policy",
    "build_agent_runtime_policy",
    "enabled_skill_paths",
    "recursion_limit_for_agent",
]
