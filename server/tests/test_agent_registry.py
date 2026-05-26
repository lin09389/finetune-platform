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

