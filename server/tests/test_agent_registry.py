from agent_runtime_legacy.agent_registry import AgentRegistry


def test_builtin_agents_load_and_primary_filter():
    registry = AgentRegistry()

    agents = {agent.id for agent in registry.list_agents()}
    primary = {agent.id for agent in registry.list_primary_agents()}

    assert {"build", "plan", "explore", "review"} <= agents
    assert {"build", "plan"} <= primary
    assert "explore" not in primary


def test_build_agent_lets_action_policy_gate_patch_and_command():
    registry = AgentRegistry()
    build = registry.require("build")
    rules = {rule["permission"]: rule["action"] for rule in build.permission_rules}

    assert rules["tool.propose_patch"] == "allow"
    assert rules["tool.propose_command"] == "allow"
    assert "必须提出对应的 `propose_patch`" in build.system_prompt
    assert "只分析" in build.system_prompt

