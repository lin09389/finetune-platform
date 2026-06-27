"""Official DeepAgents filesystem permission profiles."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from .execution_context import AgentDefinition

FilesystemPermissionProfile = Literal["build", "readonly", "deny_all"]
DEFAULT_DEEPAGENTS_INTERRUPT_ON = {"write_file": True, "edit_file": True, "execute": True}

SENSITIVE_WORKSPACE_PATTERNS = (
    "/workspace/.env",
    "/workspace/.env.*",
    "/workspace/**/.env",
    "/workspace/**/.env.*",
)
WORKSPACE_PATTERN = "/workspace/**"
INTERNAL_READ_PATTERNS = (
    "/context/**",
    "/large_tool_results/**",
    "/conversation_history/**",
)
USER_MEMORY_PATTERN = "/memories/**"
AGENT_MEMORY_PATTERN = "/agent-memory/**"
ORG_POLICY_PATTERN = "/policies/**"
FALLBACK_PATTERN = "/**"


def filesystem_permission_profile_for_agent(agent_id: str | None) -> FilesystemPermissionProfile:
    if agent_id == "build":
        return "build"
    if agent_id in {"explore", "review", "project_chat"}:
        return "readonly"
    return "deny_all"


def build_filesystem_permissions(profile: FilesystemPermissionProfile):
    """Build ordered official DeepAgents FilesystemPermission rules.

    DeepAgents evaluates filesystem permission rules in declaration order and
    defaults to allow when no rule matches. Keep the final deny route-scoped so
    the middleware remains compatible with execute-capable CompositeBackend.
    """

    from deepagents import FilesystemPermission

    rules = [
        FilesystemPermission(
            operations=["read", "write"],
            paths=list(SENSITIVE_WORKSPACE_PATTERNS),
            mode="deny",
        )
    ]

    if profile == "build":
        rules.append(
            FilesystemPermission(
                operations=["read", "write"],
                paths=[WORKSPACE_PATTERN],
                mode="allow",
            )
        )
    elif profile == "readonly":
        rules.append(
            FilesystemPermission(
                operations=["read"],
                paths=[WORKSPACE_PATTERN],
                mode="allow",
            )
        )

    if profile in {"build", "readonly"}:
        memory_operations = ["read", "write"] if profile == "build" else ["read"]
        rules.append(
            FilesystemPermission(
                operations=memory_operations,
                paths=[USER_MEMORY_PATTERN, AGENT_MEMORY_PATTERN],
                mode="allow",
            )
        )
        rules.append(
            FilesystemPermission(
                operations=["write"],
                paths=[ORG_POLICY_PATTERN],
                mode="deny",
            )
        )
        rules.append(
            FilesystemPermission(
                operations=["read"],
                paths=[ORG_POLICY_PATTERN],
                mode="allow",
            )
        )
        rules.append(
            FilesystemPermission(
                operations=["read"],
                paths=list(INTERNAL_READ_PATTERNS),
                mode="allow",
            )
        )

    rules.append(
        FilesystemPermission(
            operations=["read", "write"],
            paths=[FALLBACK_PATTERN],
            mode="deny",
        )
    )
    return rules


def filesystem_permissions_for_agent(agent_id: str | None):
    return build_filesystem_permissions(filesystem_permission_profile_for_agent(agent_id))


def default_deepagents_permission_metadata() -> dict[str, Any]:
    return {"deepagents_interrupt_on": True}


def resolve_deepagents_interrupt_on(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    """Read DeepAgents HITL interrupt configuration from session metadata."""

    raw = dict(metadata or {}).get("deepagents_interrupt_on")
    if raw is True:
        return dict(DEFAULT_DEEPAGENTS_INTERRUPT_ON)
    if isinstance(raw, dict):
        return raw
    return None


@dataclass(frozen=True)
class AgentRuntimePermissionPolicy:
    """Single policy surface for AgentSession runtime permission decisions."""

    agent: AgentDefinition | None
    agent_id: str
    metadata: dict[str, Any]

    def filesystem_permissions(self):
        return filesystem_permissions_for_agent(self.agent_id)

    def interrupt_on(self) -> dict[str, Any] | None:
        return resolve_deepagents_interrupt_on(self.metadata)

    def allowed_tools(self) -> set[str] | None:
        if not self.agent or not self.agent.tools:
            return None
        return {str(tool).strip() for tool in self.agent.tools if str(tool).strip()}

    def filter_named_tools(self, tools: list[Any]) -> list[Any]:
        allowed = self.allowed_tools()
        if allowed is None:
            return tools
        return [tool for tool in tools if getattr(tool, "name", "") in allowed]

    def validate_enabled_skills(self, project_path: str, enabled_skill_sources: list[str] | None) -> None:
        allowed = self.allowed_tools()
        if allowed is None:
            return
        from .runtime import validate_skill_tool_compatibility

        validate_skill_tool_compatibility(
            project_path,
            agent_id=self.agent_id,
            enabled_skill_sources=enabled_skill_sources,
            allowed_tools=allowed,
        )

    def tool_constraint_middleware(self, builtin_tool_names: set[str] | frozenset[str], logger: logging.Logger | None = None) -> list[Any]:
        allowed = self.allowed_tools()
        if allowed is None:
            return []
        excluded = set(builtin_tool_names) - allowed
        if not excluded:
            return []
        try:
            from deepagents.middleware._tool_exclusion import _ToolExclusionMiddleware
        except Exception:
            if logger is not None:
                logger.warning("DeepAgents tool exclusion middleware is unavailable; AgentDefinition.tools cannot be enforced")
            return []
        return [_ToolExclusionMiddleware(excluded=frozenset(excluded))]


def permission_policy_for_agent(
    agent: AgentDefinition | None,
    agent_id: str,
    metadata: dict[str, Any] | None = None,
) -> AgentRuntimePermissionPolicy:
    return AgentRuntimePermissionPolicy(agent=agent, agent_id=agent_id, metadata=dict(metadata or {}))


def validate_hitl_decisions(part: dict[str, Any], decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if part.get("type") != "permission":
        raise ValueError("HITL decisions only apply to permission parts")
    if part.get("status") != "pending":
        raise ValueError("Permission part is not pending")
    payload = dict(part.get("payload") or {})
    action_requests = payload.get("action_requests") if isinstance(payload.get("action_requests"), list) else []
    actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
    action_count = len(action_requests) or len(actions) or 1
    if len(decisions) != action_count:
        raise ValueError(f"Expected {action_count} HITL decision(s), got {len(decisions)}")

    normalized: list[dict[str, Any]] = []
    for index, raw_decision in enumerate(decisions):
        if not isinstance(raw_decision, dict):
            raise ValueError("Each HITL decision must be an object")
        decision_type = str(raw_decision.get("type") or "").strip()
        if decision_type not in {"approve", "edit", "reject", "respond"}:
            raise ValueError(f"Unsupported HITL decision type: {decision_type}")
        action = actions[index] if index < len(actions) and isinstance(actions[index], dict) else {}
        allowed = action.get("allowed_decisions") or payload.get("allowed_decisions") or ["approve", "edit", "reject", "respond"]
        allowed_set = {str(item) for item in allowed} if isinstance(allowed, (list, tuple)) else {"approve", "reject"}
        if decision_type not in allowed_set:
            raise ValueError(f"Decision '{decision_type}' is not allowed for action {index + 1}")

        decision: dict[str, Any] = {"type": decision_type}
        message = str(raw_decision.get("message") or "").strip()
        if decision_type in {"reject", "respond"}:
            if decision_type == "respond" and not message:
                raise ValueError("Respond decisions require a message")
            if message:
                decision["message"] = message
        if decision_type == "edit":
            edited_action = raw_decision.get("edited_action") or raw_decision.get("editedAction")
            if not isinstance(edited_action, dict):
                raise ValueError("Edit decisions require edited_action")
            name = str(edited_action.get("name") or "").strip()
            args = edited_action.get("args")
            if not name:
                raise ValueError("edited_action.name is required")
            if not isinstance(args, dict):
                raise ValueError("edited_action.args must be an object")
            decision["edited_action"] = {"name": name, "args": dict(args)}
        normalized.append(decision)
    return normalized


__all__ = [
    "AgentRuntimePermissionPolicy",
    "DEFAULT_DEEPAGENTS_INTERRUPT_ON",
    "FilesystemPermissionProfile",
    "SENSITIVE_WORKSPACE_PATTERNS",
    "WORKSPACE_PATTERN",
    "INTERNAL_READ_PATTERNS",
    "USER_MEMORY_PATTERN",
    "AGENT_MEMORY_PATTERN",
    "ORG_POLICY_PATTERN",
    "FALLBACK_PATTERN",
    "build_filesystem_permissions",
    "default_deepagents_permission_metadata",
    "filesystem_permission_profile_for_agent",
    "filesystem_permissions_for_agent",
    "permission_policy_for_agent",
    "resolve_deepagents_interrupt_on",
    "validate_hitl_decisions",
]
