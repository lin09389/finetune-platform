"""Permission evaluation for agent tool calls."""

from __future__ import annotations

import fnmatch
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PermissionAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class PermissionRule(BaseModel):
    permission: str = Field(default="*")
    pattern: str = Field(default="*")
    action: PermissionAction = PermissionAction.ASK


def evaluate(permission: str, pattern: str, ruleset: list[PermissionRule]) -> PermissionAction:
    """Evaluate permission with last rule wins semantics."""
    for rule in reversed(ruleset):
        if _match(permission, rule.permission) and _match(pattern, rule.pattern):
            return rule.action
    return PermissionAction.ASK


def _match(text: str, pattern: str) -> bool:
    if pattern == "*":
        return True
    return fnmatch.fnmatch(text, pattern)


def from_config(config: dict[str, Any]) -> list[PermissionRule]:
    rules: list[PermissionRule] = []
    for key, value in config.items():
        if isinstance(value, str):
            rules.append(PermissionRule(permission=key, pattern="*", action=PermissionAction(value)))
            continue
        if isinstance(value, dict):
            for pattern, action in value.items():
                rules.append(PermissionRule(permission=key, pattern=str(pattern), action=PermissionAction(str(action))))
    return rules


def default_rules_for_agent(agent_id: str) -> list[PermissionRule]:
    if agent_id == "planner":
        return from_config(
            {
                "tool.list_files": "allow",
                "tool.search_code": "allow",
                "tool.read_file": "allow",
                "tool.inspect_project": "allow",
                "tool.detect_project_commands": "allow",
                "tool.get_git_status": "allow",
                "tool.get_git_diff": "allow",
                "tool.list_changed_files": "allow",
                "tool.read_execution_result": "allow",
                "tool.read_test_failures": "allow",
                "tool.delegate_agent": "allow",
                "tool.propose_patch": "deny",
                "tool.propose_command": "deny",
                "tool.finalize": "allow",
            }
        )
    if agent_id == "implementer":
        return from_config(
            {
                "tool.list_files": "allow",
                "tool.search_code": "allow",
                "tool.read_file": "allow",
                "tool.inspect_project": "allow",
                "tool.detect_project_commands": "allow",
                "tool.get_git_status": "allow",
                "tool.get_git_diff": "allow",
                "tool.list_changed_files": "allow",
                "tool.read_execution_result": "allow",
                "tool.read_test_failures": "allow",
                "tool.delegate_agent": "allow",
                "tool.propose_patch": "allow",
                "tool.propose_command": "allow",
                "tool.finalize": "allow",
            }
        )
    if agent_id == "reviewer":
        return from_config(
            {
                "tool.list_files": "allow",
                "tool.search_code": "allow",
                "tool.read_file": "allow",
                "tool.inspect_project": "allow",
                "tool.detect_project_commands": "allow",
                "tool.get_git_status": "allow",
                "tool.get_git_diff": "allow",
                "tool.list_changed_files": "allow",
                "tool.read_execution_result": "allow",
                "tool.read_test_failures": "allow",
                "tool.delegate_agent": "deny",
                "tool.propose_patch": "deny",
                "tool.propose_command": "allow",
                "tool.finalize": "allow",
            }
        )
    return from_config({"*": "ask"})


__all__ = ["PermissionAction", "PermissionRule", "evaluate", "from_config", "default_rules_for_agent"]
