from pathlib import Path

import pytest

from agent_session.agent_registry import AgentRegistry


def test_builtin_agents_load_and_primary_filter():
    registry = AgentRegistry()

    agents = {agent.id for agent in registry.list_agents()}
    primary = {agent.id for agent in registry.list_primary_agents()}

    assert {"build", "explore", "review"} <= agents
    assert "build" in primary
    assert "explore" not in primary


def test_build_agent_allows_official_harness_edit_and_execute_tools():
    registry = AgentRegistry()
    build = registry.require("build")

    assert "write_file" in build.tools
    assert "edit_file" in build.tools
    assert "execute" in build.tools
    assert not hasattr(build, "permission_rules")
    assert build.default_provider == "openai"
    assert build.default_model == "gpt-4o"
    assert "官方 sandbox execute" in build.system_prompt
    assert "只分析" in build.system_prompt


def test_registry_treats_all_mode_as_direct_and_handoff_capable(tmp_path: Path):
    (tmp_path / "hybrid.md").write_text(
        "---\nid: hybrid\nname: Hybrid\nmode: all\nhandoff_targets:\n  - helper\n---\nHybrid prompt.\n",
        encoding="utf-8",
    )
    (tmp_path / "helper.md").write_text(
        "---\nid: helper\nname: Helper\nmode: subagent\n---\nHelper prompt.\n",
        encoding="utf-8",
    )

    registry = AgentRegistry(tmp_path)

    assert "hybrid" in {agent.id for agent in registry.list_primary_agents()}
    assert registry.require("hybrid").can_delegate is True
    assert registry.require("helper").can_be_handoff_target is True


def test_registry_rejects_invalid_handoff_modes(tmp_path: Path):
    (tmp_path / "parent.md").write_text(
        "---\nid: parent\nname: Parent\nmode: primary\nhandoff_targets:\n  - direct_only\n---\nParent prompt.\n",
        encoding="utf-8",
    )
    (tmp_path / "direct_only.md").write_text(
        "---\nid: direct_only\nname: Direct Only\nmode: primary\n---\nDirect prompt.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="cannot be used as a subagent"):
        AgentRegistry(tmp_path)

