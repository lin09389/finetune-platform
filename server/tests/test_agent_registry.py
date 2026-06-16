from pathlib import Path

import pytest

from agent_session.agent_registry import AgentRegistry
from agent_session.runtime_contract import agent_system_prompt
from agent_session.runtime_policy import build_agent_definition_policy


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
    assert build.handoff_targets == ["explore", "review"]
    assert build.async_subagent_targets == ["explore", "review"]
    assert build.definition_format == "agent_manifest_v2"
    assert build.schema_version == 2
    assert build.system_prompt_definition["identity"].startswith("你是一位资深全栈工程师")
    assert build.output_schema["format"] == "structured_markdown"
    assert build.few_shot_examples[0]["name"] == "targeted_code_change"
    assert "before_final" in build.reflection_rules
    assert "官方 sandbox execute" in build.system_prompt
    assert "只分析" in build.system_prompt


def test_yaml_manifest_v2_compiles_structured_sections(tmp_path: Path):
    (tmp_path / "parent.agent.yaml").write_text(
        """
schema_version: 2
id: parent
name: Parent
description: Parent agent
mode: primary
Runtime:
  default_provider: openai
  default_model: gpt-4o-mini
  max_iterations: 3
Tools:
  allowed:
    - read_file
    - grep
Handoff:
  targets:
    - helper
  async_targets:
    - helper
SystemPrompt:
  identity: |
    Parent identity.
  responsibilities:
    - Read first.
  sections:
    Extra: |
      Extra prompt.
OutputSchema:
  format: json
  required_fields:
    - summary
  schema:
    type: object
FewShotExamples:
  - name: small_fix
    user: Fix it.
    assistant: I will inspect and patch.
ReflectionRules:
  before_final:
    - Verify the result.
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "helper.agent.yaml").write_text(
        """
schema_version: 2
id: helper
name: Helper
mode: subagent
SystemPrompt:
  identity: Helper identity.
""".strip(),
        encoding="utf-8",
    )

    registry = AgentRegistry(tmp_path)
    parent = registry.require("parent")

    assert parent.definition_format == "agent_manifest_v2"
    assert parent.system_prompt_definition["responsibilities"] == ["Read first."]
    assert parent.default_model == "gpt-4o-mini"
    assert parent.max_iterations == 3
    assert parent.tools == ["read_file", "grep"]
    assert parent.handoff_targets == ["helper"]
    assert parent.async_subagent_targets == ["helper"]
    assert "## 身份\nParent identity." in parent.system_prompt
    assert "## Extra\nExtra prompt." in parent.system_prompt
    assert "## Few-shot Examples" in parent.system_prompt
    assert "### Before final" in parent.system_prompt
    assert "Required fields" in parent.output_requirements
    assert "type: object" in parent.output_requirements


def test_agent_system_prompt_includes_compiled_output_schema(tmp_path: Path):
    (tmp_path / "agent.agent.yaml").write_text(
        """
schema_version: 2
id: agent
name: Agent
mode: all
SystemPrompt:
  identity: Agent identity.
OutputSchema:
  format: structured_markdown
  required_sections:
    - Summary
""".strip(),
        encoding="utf-8",
    )

    prompt = agent_system_prompt(AgentRegistry(tmp_path).require("agent"))

    assert "Agent identity." in prompt
    assert "## 输出要求" in prompt
    assert "Required sections" in prompt
    assert "Summary" in prompt


def test_agent_definition_policy_exposes_manifest_v2_output_contract():
    build = AgentRegistry().require("build")

    policy = build_agent_definition_policy(build)
    output_contract = policy["output_contract"]

    assert output_contract["definition_format"] == "agent_manifest_v2"
    assert output_contract["schema_version"] == 2
    assert output_contract["format"] == "structured_markdown"
    assert output_contract["required_sections"] == ["已完成项", "变更文件", "验证结果", "后续建议或风险"]
    assert output_contract["few_shot_examples"] == 2
    assert output_contract["reflection_rules"] >= 8


def test_registry_treats_all_mode_as_direct_and_handoff_capable(tmp_path: Path):
    (tmp_path / "hybrid.agent.yaml").write_text(
        """
schema_version: 2
id: hybrid
name: Hybrid
mode: all
Handoff:
  targets:
    - helper
SystemPrompt:
  identity: Hybrid prompt.
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "helper.agent.yaml").write_text(
        """
schema_version: 2
id: helper
name: Helper
mode: subagent
SystemPrompt:
  identity: Helper prompt.
""".strip(),
        encoding="utf-8",
    )

    registry = AgentRegistry(tmp_path)

    assert "hybrid" in {agent.id for agent in registry.list_primary_agents()}
    assert registry.require("hybrid").can_delegate is True
    assert registry.require("helper").can_be_handoff_target is True


def test_registry_parses_scalar_and_inline_list_fields(tmp_path: Path):
    (tmp_path / "parent.agent.yaml").write_text(
        """
schema_version: 2
id: parent
name: Parent
mode: primary
tools:
  - read_file
  - grep
handoff_targets: helper
async_subagent_targets: [helper]
SystemPrompt:
  identity: Parent prompt.
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "helper.agent.yaml").write_text(
        """
schema_version: 2
id: helper
name: Helper
mode: subagent
SystemPrompt:
  identity: Helper prompt.
""".strip(),
        encoding="utf-8",
    )

    registry = AgentRegistry(tmp_path)
    parent = registry.require("parent")

    assert parent.tools == ["read_file", "grep"]
    assert parent.handoff_targets == ["helper"]
    assert parent.async_subagent_targets == ["helper"]


def test_registry_rejects_markdown_agent_files(tmp_path: Path):
    (tmp_path / "legacy.md").write_text(
        "---\nid: legacy\nname: Legacy\nmode: all\ntools: [read_file]\n---\nLegacy prompt.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Legacy markdown agent definitions are no longer supported"):
        AgentRegistry(tmp_path)


def test_registry_rejects_invalid_handoff_modes(tmp_path: Path):
    (tmp_path / "parent.agent.yaml").write_text(
        """
schema_version: 2
id: parent
name: Parent
mode: primary
Handoff:
  targets:
    - direct_only
SystemPrompt:
  identity: Parent prompt.
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "direct_only.agent.yaml").write_text(
        """
schema_version: 2
id: direct_only
name: Direct Only
mode: primary
SystemPrompt:
  identity: Direct prompt.
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="cannot be used as a subagent"):
        AgentRegistry(tmp_path)


def test_registry_requires_async_subagents_to_be_explicit_handoff_targets(tmp_path: Path):
    (tmp_path / "parent.agent.yaml").write_text(
        """
schema_version: 2
id: parent
name: Parent
mode: primary
Handoff:
  targets:
    - helper
  async_targets:
    - other
SystemPrompt:
  identity: Parent prompt.
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "helper.agent.yaml").write_text(
        """
schema_version: 2
id: helper
name: Helper
mode: subagent
SystemPrompt:
  identity: Helper prompt.
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "other.agent.yaml").write_text(
        """
schema_version: 2
id: other
name: Other
mode: subagent
SystemPrompt:
  identity: Other prompt.
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must also be declared in handoff_targets"):
        AgentRegistry(tmp_path)

