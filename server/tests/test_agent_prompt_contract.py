"""Prompt-engineering contracts for built-in coding agents.

Loads real manifests via AgentRegistry and drives build_system_prompt /
summary enrichment on the shipped paths (no re-implemented prompt strings).
"""
from __future__ import annotations

from agent_session.agent_registry import AgentRegistry
from agent_session.runtime_contract import (
    build_error_recovery_prompt,
    build_execution_prompt,
    build_system_prompt,
)
from agent_session.session_progress import (
    BUILD_REQUIRED_SUMMARY_SECTIONS,
    empty_tool_metrics,
    enrich_final_summary,
    required_summary_sections_for_agent,
)

FORBIDDEN_PHRASES = (
    "工具 JSON 协议",
    "命令不需要平台白名单审批",
    "命令不需要审批",
)


def test_builtin_runtime_defaults_are_viable_not_unconfigured_openai():
    registry = AgentRegistry()
    for agent_id in ("build", "review", "explore"):
        agent = registry.require(agent_id)
        assert agent.default_provider != "openai", agent_id
        assert agent.default_model not in {None, "", "gpt-4o"}, agent_id
        assert agent.default_provider == "deepseek"
        assert agent.default_model == "deepseek-chat"


def test_build_system_prompt_drops_obsolete_json_protocol_and_blanket_no_approval():
    registry = AgentRegistry()
    build = registry.require("build")
    prompt = build_system_prompt(registry, build)

    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in prompt, phrase

    # HITL / autonomy nuance and security boundaries must be present for Build.
    assert "HITL" in prompt or "人工审批" in prompt
    assert ".env" in prompt or "敏感" in prompt
    assert "原生工具" in prompt or "工具调用" in prompt
    assert "已完成项" in prompt
    assert "变更文件" in prompt
    assert "验证结果" in prompt


def test_review_system_prompt_has_workflow_and_verify_only_execute():
    registry = AgentRegistry()
    review = registry.require("review")
    prompt = build_system_prompt(registry, review)

    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in prompt, phrase

    assert "工作流" in prompt or "Scope" in prompt or "Verify" in prompt
    assert "验证" in prompt
    assert "不写补丁" in prompt or "禁止创建" in prompt
    # Output contract uses Review sections, not Build-only names forced alone.
    assert "结论" in prompt
    assert "风险列表" in prompt
    assert "验证建议" in prompt


def test_explore_output_sections_are_not_build_only():
    registry = AgentRegistry()
    explore = registry.require("explore")
    prompt = build_system_prompt(registry, explore)

    assert "关键发现" in prompt
    assert "相关文件" in prompt
    assert "结论" in prompt
    # Platform recovery text must quote Explore sections, not overwrite with Build-only set alone.
    recovery = build_error_recovery_prompt(explore)
    assert "关键发现" in recovery
    assert "相关文件" in recovery
    # Build-only trio must not be the sole recovery requirement for Explore.
    assert "已完成项" not in recovery or "关键发现" in recovery


def test_required_summary_sections_parameterized_per_agent():
    registry = AgentRegistry()
    build = registry.require("build")
    review = registry.require("review")
    explore = registry.require("explore")

    assert required_summary_sections_for_agent(build) == (
        "已完成项",
        "变更文件",
        "验证结果",
        "后续建议或风险",
    )
    assert required_summary_sections_for_agent(review) == ("结论", "风险列表", "验证建议")
    assert required_summary_sections_for_agent(explore) == ("关键发现", "相关文件", "结论")
    assert required_summary_sections_for_agent(None) == BUILD_REQUIRED_SUMMARY_SECTIONS
    assert required_summary_sections_for_agent(agent_id="review") == ("结论", "风险列表", "验证建议")


def test_enrich_final_summary_uses_review_sections_not_build_only_headings():
    metadata = {
        "trajectory_guard": {},
        "tool_metrics": empty_tool_metrics(),
        "agent_id": "review",
    }
    registry = AgentRegistry()
    review = registry.require("review")
    text = enrich_final_summary(
        "静态审查完成。",
        metadata,
        status="completed",
        agent=review,
        agent_id="review",
    )
    assert "结论" in text
    assert "风险列表" in text
    assert "验证建议" in text
    # Missing-section backfill should not invent only Build headings for Review.
    assert "### 结论" in text
    assert "### 风险列表" in text


def test_enrich_final_summary_build_fallback_still_covers_write_verify_gate():
    metadata = {
        "trajectory_guard": {
            "writes": {"app.py": 1},
            "successful_write_sequences": [1],
            "diff_write_sequences": [1],
            "verified_paths": ["app.py"],
            "last_write_sequence": 1,
            "last_verification_sequence": 2,
        },
        "tool_metrics": {**empty_tool_metrics(), "verify_attempted": 1, "verify_ok": 1},
    }
    text = enrich_final_summary("修好了。", metadata, status="completed")
    assert "已完成项" in text
    assert "变更文件" in text
    assert "验证结果" in text
    assert "app.py" in text


def test_execution_prompt_mentions_hitl_not_blanket_no_approval():
    prompt = build_execution_prompt()
    assert "白名单" in prompt  # still mentions legacy whitelist removal
    assert "命令不需要平台白名单审批" not in prompt
    assert "HITL" in prompt or "人工审批" in prompt
