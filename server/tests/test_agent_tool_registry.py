from __future__ import annotations

from agent_session.tools import AgentToolRegistry


def test_agent_tool_registry_has_core_tools():
    registry = AgentToolRegistry()
    names = {tool.name for tool in registry.list()}

    assert {"read", "search", "glob", "collect_context", "detect_project_commands", "patch", "bash_command", "read_execution", "finalize"} <= names
    assert registry.get("read").permission == "read"
    assert registry.get("patch").permission == "patch"
    assert registry.get("bash_command").permission == "command"


def test_unknown_tool_returns_none():
    registry = AgentToolRegistry()

    assert registry.get("unknown_tool") is None
