from agent_runtime.agent_registry import AgentRegistry


def test_builtin_agents_load_and_primary_filter():
    registry = AgentRegistry()

    agents = {agent.id for agent in registry.list_agents()}
    primary = {agent.id for agent in registry.list_primary_agents()}

    assert {"build", "plan", "explore", "review"} <= agents
    assert {"build", "plan"} <= primary
    assert "explore" not in primary
