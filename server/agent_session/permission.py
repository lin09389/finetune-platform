"""Official DeepAgents filesystem permission profiles + autonomy-mode gates.

Autonomy modes (UI: 工作台设置) map to real HITL / tool constraints:

- ``confirm_all``: write_file / edit_file / execute require approval (full HITL).
- ``safe_auto``: routine workspace write/edit/execute run without HITL (weaker than
  confirm_all). Sensitive paths (``.env``) remain filesystem-denied.
- ``read_only``: write/edit/execute tools are excluded and FS profile is readonly
  so workspace mutation cannot succeed even if a tool were re-introduced.

Explicit ``metadata.deepagents_interrupt_on`` (bool or tool map) always wins over
autonomy defaults when the key is present.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from .execution_context import AgentDefinition

FilesystemPermissionProfile = Literal["build", "readonly", "deny_all"]
AutonomyMode = Literal["safe_auto", "confirm_all", "read_only"]

DEFAULT_DEEPAGENTS_INTERRUPT_ON = {"write_file": True, "edit_file": True, "execute": True}
# Tools that mutate workspace or run shell — blocked under read_only.
WRITE_EXECUTE_TOOLS = frozenset({"write_file", "edit_file", "execute"})
# Default read-only tool surface when an agent lists no tools but mode is read_only.
READ_ONLY_FALLBACK_TOOLS = frozenset(
    {"ls", "read_file", "glob", "grep", "task", "start_async_task", "check_async_task", "list_async_tasks", "update_async_task", "cancel_async_task"}
)

VALID_AUTONOMY_MODES: frozenset[str] = frozenset({"safe_auto", "confirm_all", "read_only"})

SENSITIVE_WORKSPACE_PATTERNS = (
    "/workspace/.env",
    "/workspace/.env.*",
    "/workspace/**/.env",
    "/workspace/**/.env.*",
)
WORKSPACE_PATTERN = "/workspace/**"
WORKSPACE_PATTERNS = ("/workspace", WORKSPACE_PATTERN)
INTERNAL_READ_PATTERNS = (
    "/context",
    "/context/**",
    "/large_tool_results",
    "/large_tool_results/**",
    "/conversation_history",
    "/conversation_history/**",
)
USER_MEMORY_PATTERN = "/memories/**"
AGENT_MEMORY_PATTERN = "/agent-memory/**"
ORG_POLICY_PATTERN = "/policies/**"
USER_MEMORY_PATTERNS = ("/memories", USER_MEMORY_PATTERN)
AGENT_MEMORY_PATTERNS = ("/agent-memory", AGENT_MEMORY_PATTERN)
ORG_POLICY_PATTERNS = ("/policies", ORG_POLICY_PATTERN)
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
                paths=list(WORKSPACE_PATTERNS),
                mode="allow",
            )
        )
    elif profile == "readonly":
        rules.append(
            FilesystemPermission(
                operations=["read"],
                paths=list(WORKSPACE_PATTERNS),
                mode="allow",
            )
        )

    if profile in {"build", "readonly"}:
        memory_operations = ["read", "write"] if profile == "build" else ["read"]
        rules.append(
            FilesystemPermission(
                operations=memory_operations,
                paths=[*USER_MEMORY_PATTERNS, *AGENT_MEMORY_PATTERNS],
                mode="allow",
            )
        )
        rules.append(
            FilesystemPermission(
                operations=["write"],
                paths=list(ORG_POLICY_PATTERNS),
                mode="deny",
            )
        )
        rules.append(
            FilesystemPermission(
                operations=["read"],
                paths=list(ORG_POLICY_PATTERNS),
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


def normalize_autonomy_mode(mode: str | None) -> AutonomyMode:
    """Normalize UI / API autonomy labels to the three product modes."""
    raw = str(mode or "safe_auto").strip().lower().replace("-", "_")
    if raw in {"confirm_all", "confirmall", "manual", "confirm"}:
        return "confirm_all"
    if raw in {"read_only", "readonly"}:
        return "read_only"
    return "safe_auto"


def interrupt_on_for_autonomy(mode: str | None) -> dict[str, Any] | None:
    """Map autonomy_mode to DeepAgents ``interrupt_on`` tool gates.

    - confirm_all → full HITL on write_file / edit_file / execute
    - safe_auto → no HITL for those tools (strictly weaker; sensitive FS deny remains)
    - read_only → no HITL map (tools are excluded separately)
    """
    normalized = normalize_autonomy_mode(mode)
    if normalized == "confirm_all":
        return dict(DEFAULT_DEEPAGENTS_INTERRUPT_ON)
    return None


def default_deepagents_permission_metadata(
    autonomy_mode: str | None = "safe_auto",
) -> dict[str, Any]:
    """Session metadata fragment for autonomy + default interrupt gates."""
    mode = normalize_autonomy_mode(autonomy_mode)
    interrupt = interrupt_on_for_autonomy(mode)
    # Store bool True for confirm_all (legacy shape); False means "no interrupt tools".
    if interrupt is None:
        stored: Any = False
    else:
        stored = True
    return {
        "autonomy_mode": mode,
        "deepagents_interrupt_on": stored,
    }


# Coding tools that may be trusted for the rest of a session after user approve.
# Training submit and other product gates stay independent.
TRUSTABLE_HITL_TOOLS: frozenset[str] = frozenset({"write_file", "edit_file", "execute"})
SESSION_TOOL_TRUST_KEY = "session_tool_trust"


def _base_interrupt_on_from_metadata(data: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve interrupt map before applying session-scoped trust grants."""
    if "deepagents_interrupt_on" in data:
        raw = data.get("deepagents_interrupt_on")
        if raw is True:
            return dict(DEFAULT_DEEPAGENTS_INTERRUPT_ON)
        if raw is False or raw is None:
            return None
        if isinstance(raw, dict):
            # Keep only truthy tool gates; empty → no interrupt.
            cleaned = {str(k): bool(v) for k, v in raw.items() if v}
            return cleaned or None
        return dict(DEFAULT_DEEPAGENTS_INTERRUPT_ON) if raw else None
    return interrupt_on_for_autonomy(data.get("autonomy_mode"))


def session_tool_trust_set(metadata: dict[str, Any] | None) -> set[str]:
    data = dict(metadata or {})
    raw = data.get(SESSION_TOOL_TRUST_KEY) or []
    if not isinstance(raw, (list, tuple, set)):
        return set()
    return {str(item).strip() for item in raw if str(item).strip() in TRUSTABLE_HITL_TOOLS}


def resolve_deepagents_interrupt_on(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    """Resolve DeepAgents HITL interrupt map from session metadata.

    Precedence:
    1. Explicit ``deepagents_interrupt_on`` when the key is present
       (``True`` → full default map; ``False``/empty → no interrupt; dict → as-is).
    2. Else derive from ``autonomy_mode`` (default ``safe_auto`` → no write/exec HITL).
    3. Subtract ``session_tool_trust`` tools granted after user approve in this session
       (cross-interrupt multi-file / multi-execute no longer re-prompts).
    """
    data = dict(metadata or {})
    base = _base_interrupt_on_from_metadata(data)
    if not base:
        return None
    trusted = session_tool_trust_set(data)
    if not trusted:
        return base
    remaining = {tool: True for tool, enabled in base.items() if enabled and str(tool) not in trusted}
    return remaining or None


def tools_granted_by_hitl_decisions(
    part: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> list[str]:
    """Return trustable tool names the user **approved** in this decision batch.

    Reject / edit / respond do not grant trust. Only tools listed on the
    permission part's action_requests (or single ``payload.tool``) are considered.
    """
    payload = dict(part.get("payload") or {})
    action_requests = payload.get("action_requests") if isinstance(payload.get("action_requests"), list) else []
    actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
    rows = action_requests or actions
    granted: list[str] = []
    for index, decision in enumerate(decisions):
        if not isinstance(decision, dict):
            continue
        if str(decision.get("type") or "").strip() != "approve":
            continue
        name = ""
        if index < len(rows) and isinstance(rows[index], dict):
            name = str(rows[index].get("name") or rows[index].get("tool") or "").strip()
        if not name:
            name = str(payload.get("tool") or payload.get("name") or "").strip()
        if name in TRUSTABLE_HITL_TOOLS and name not in granted:
            granted.append(name)
    return granted


def grant_session_tool_trust(
    metadata: dict[str, Any] | None,
    tools: list[str] | tuple[str, ...] | set[str],
) -> dict[str, Any]:
    """Merge approved tools into session-scoped trust (idempotent, same-session only)."""
    meta = dict(metadata or {})
    if is_read_only_autonomy(meta):
        # Never expand write/exec capability under read_only.
        return meta
    trusted = session_tool_trust_set(meta)
    for tool in tools:
        name = str(tool or "").strip()
        if name in TRUSTABLE_HITL_TOOLS:
            trusted.add(name)
    meta[SESSION_TOOL_TRUST_KEY] = sorted(trusted)
    return meta


def apply_hitl_approve_session_trust(
    metadata: dict[str, Any] | None,
    part: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Production helper: after HITL decisions, grant trust for approved coding tools."""
    granted = tools_granted_by_hitl_decisions(part, decisions)
    if not granted:
        return dict(metadata or {})
    return grant_session_tool_trust(metadata, granted)


def is_read_only_autonomy(metadata: dict[str, Any] | None) -> bool:
    return normalize_autonomy_mode(dict(metadata or {}).get("autonomy_mode")) == "read_only"


@dataclass(frozen=True)
class AgentRuntimePermissionPolicy:
    """Single policy surface for AgentSession runtime permission decisions."""

    agent: AgentDefinition | None
    agent_id: str
    metadata: dict[str, Any]

    def autonomy_mode(self) -> AutonomyMode:
        return normalize_autonomy_mode(self.metadata.get("autonomy_mode"))

    def filesystem_permissions(self):
        # read_only sessions always use the readonly FS profile, even for build agent.
        if self.autonomy_mode() == "read_only":
            return build_filesystem_permissions("readonly")
        return filesystem_permissions_for_agent(self.agent_id)

    def interrupt_on(self) -> dict[str, Any] | None:
        return resolve_deepagents_interrupt_on(self.metadata)

    def allowed_tools(self) -> set[str] | None:
        from .training_tools import (
            TRAINING_MUTATING_TOOL_NAMES,
            TRAINING_TOOL_NAMES,
            training_tools_enabled_for_session,
        )

        base: set[str] | None
        if not self.agent or not self.agent.tools:
            base = None
        else:
            base = {str(tool).strip() for tool in self.agent.tools if str(tool).strip()}
        # Train/Hybrid sessions inject training tools at runtime; allow them even
        # when the static Build manifest no longer lists them (coding-only default).
        session_like = {
            "agent_id": self.agent_id,
            "metadata": self.metadata,
            "task_mode": self.metadata.get("task_mode"),
        }
        if base is not None and training_tools_enabled_for_session(session_like):
            base = set(base) | set(TRAINING_TOOL_NAMES)

        if self.autonomy_mode() != "read_only":
            return base
        # Fail-closed: strip workspace mutation, shell, and mutating training tools.
        blocked = WRITE_EXECUTE_TOOLS | set(TRAINING_MUTATING_TOOL_NAMES)
        if base is None:
            return set(READ_ONLY_FALLBACK_TOOLS)
        return {tool for tool in base if tool not in blocked}

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
        allowed_set = {str(item) for item in allowed} if isinstance(allowed, list | tuple) else {"approve", "reject"}
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
    "AutonomyMode",
    "DEFAULT_DEEPAGENTS_INTERRUPT_ON",
    "FilesystemPermissionProfile",
    "READ_ONLY_FALLBACK_TOOLS",
    "SESSION_TOOL_TRUST_KEY",
    "TRUSTABLE_HITL_TOOLS",
    "VALID_AUTONOMY_MODES",
    "WRITE_EXECUTE_TOOLS",
    "SENSITIVE_WORKSPACE_PATTERNS",
    "WORKSPACE_PATTERN",
    "WORKSPACE_PATTERNS",
    "INTERNAL_READ_PATTERNS",
    "USER_MEMORY_PATTERN",
    "USER_MEMORY_PATTERNS",
    "AGENT_MEMORY_PATTERN",
    "AGENT_MEMORY_PATTERNS",
    "ORG_POLICY_PATTERN",
    "ORG_POLICY_PATTERNS",
    "FALLBACK_PATTERN",
    "apply_hitl_approve_session_trust",
    "build_filesystem_permissions",
    "default_deepagents_permission_metadata",
    "filesystem_permission_profile_for_agent",
    "filesystem_permissions_for_agent",
    "grant_session_tool_trust",
    "interrupt_on_for_autonomy",
    "is_read_only_autonomy",
    "normalize_autonomy_mode",
    "permission_policy_for_agent",
    "resolve_deepagents_interrupt_on",
    "session_tool_trust_set",
    "tools_granted_by_hitl_decisions",
    "validate_hitl_decisions",
]
