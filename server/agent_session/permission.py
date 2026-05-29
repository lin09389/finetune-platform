"""Official DeepAgents filesystem permission profiles."""

from __future__ import annotations

from typing import Literal


FilesystemPermissionProfile = Literal["build", "readonly", "deny_all"]

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


__all__ = [
    "FilesystemPermissionProfile",
    "SENSITIVE_WORKSPACE_PATTERNS",
    "WORKSPACE_PATTERN",
    "INTERNAL_READ_PATTERNS",
    "USER_MEMORY_PATTERN",
    "AGENT_MEMORY_PATTERN",
    "ORG_POLICY_PATTERN",
    "FALLBACK_PATTERN",
    "build_filesystem_permissions",
    "filesystem_permission_profile_for_agent",
    "filesystem_permissions_for_agent",
]
