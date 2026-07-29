"""Step 1: working-state card, tool metrics, completion gate."""
from __future__ import annotations

from agent_session.agent_registry import AgentRegistry
from agent_session.runtime_contract import build_system_prompt
from agent_session.session_progress import (
    WORKING_STATE_SECTION_TITLE,
    apply_tool_event,
    attach_completion_gate,
    build_completion_gate,
    build_working_state_card,
    empty_tool_metrics,
    reset_tool_metrics,
)


def test_apply_tool_event_counts_start_fail_and_verify():
    metrics = empty_tool_metrics()
    metrics = apply_tool_event(
        metrics,
        {"event_type": "tool_call_started", "payload": {"tool": "read_file"}},
    )
    assert metrics["tools_total"] == 1
    assert metrics["by_tool"]["read_file"]["calls"] == 1

    metrics = apply_tool_event(
        metrics,
        {
            "event_type": "tool_call_started",
            "payload": {"tool": "execute"},
        },
    )
    metrics = apply_tool_event(
        metrics,
        {
            "event_type": "tool_call_completed",
            "payload": {
                "tool": "execute",
                "part": {
                    "payload": {"tool": "execute", "input": {"command": "python -m pytest -q"}},
                    "content": "2 passed",
                },
            },
        },
    )
    assert metrics["tools_total"] == 2
    assert metrics["verify_attempted"] == 1
    assert metrics["verify_ok"] == 1

    metrics = apply_tool_event(
        metrics,
        {"event_type": "tool_call_failed", "payload": {"tool": "edit_file", "error": "blocked"}},
    )
    assert metrics["tools_failed"] == 1

    metrics = apply_tool_event(
        metrics,
        {"event_type": "trajectory_guard_blocked", "payload": {"guard": "trajectory_guard"}},
    )
    assert metrics["trajectory_blocks"] == 1


def test_working_state_card_includes_written_and_verify_gap():
    metadata = {
        "trajectory_guard": {
            "reads": {"app.py": 1},
            "writes": {"app.py": 2},
            "verified_paths": [],
            "reread_required": ["app.py"],
            "last_block_reason": "require_read_before_write",
            "violations": [{"x": 1}],
            "successful_write_sequences": [2],
            "diff_write_sequences": [2],
            "last_write_sequence": 2,
            "last_verification_sequence": 0,
        },
        "tool_metrics": {
            **empty_tool_metrics(),
            "tools_total": 5,
            "tools_failed": 1,
            "verify_attempted": 1,
            "verify_ok": 0,
            "trajectory_blocks": 1,
        },
    }
    card = build_working_state_card(metadata)
    assert WORKING_STATE_SECTION_TITLE in card
    assert "app.py" in card
    assert "验证" in card
    assert "未成功" in card or "尚未完成" in card


def test_build_system_prompt_appends_working_state_card():
    registry = AgentRegistry()
    agent = registry.get("build")
    metadata = {
        "trajectory_guard": {
            "reads": {"cli.py": 1},
            "writes": {"cli.py": 2},
            "verified_paths": [],
            "successful_write_sequences": [2],
            "diff_write_sequences": [],
            "last_write_sequence": 2,
            "last_verification_sequence": 0,
        },
        "tool_metrics": {**empty_tool_metrics(), "tools_total": 3},
    }
    prompt = build_system_prompt(registry, agent, metadata=metadata)
    assert WORKING_STATE_SECTION_TITLE in prompt
    assert "cli.py" in prompt


def test_completion_gate_requires_verify_after_writes():
    metadata = {
        "trajectory_guard": {
            "writes": {"app.py": 1},
            "successful_write_sequences": [1],
            "diff_write_sequences": [1],
            "verified_paths": [],
            "last_write_sequence": 1,
            "last_verification_sequence": 0,
        },
        "tool_metrics": {**empty_tool_metrics(), "verify_attempted": 0, "verify_ok": 0},
    }
    gate = build_completion_gate(metadata, status="completed")
    assert gate["completed_ok"] is False
    assert "verification_missing" in gate["gaps"] or "verification_required" in gate["gaps"]
    assert gate["has_writes"] is True
    assert gate["diff_visible"] is True


def test_completion_gate_ok_for_analysis_only_completed():
    gate = build_completion_gate({"tool_metrics": empty_tool_metrics()}, status="completed")
    assert gate["completed_ok"] is True
    assert gate["has_writes"] is False
    assert gate["gaps"] == []


def test_completion_gate_ok_when_writes_verified_with_diff():
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
    gate = build_completion_gate(metadata, status="completed")
    assert gate["completed_ok"] is True
    assert gate["gaps"] == []


def test_reset_tool_metrics_clears_gate():
    metadata = attach_completion_gate(
        {
            "tool_metrics": {**empty_tool_metrics(), "tools_total": 9},
            "trajectory_guard": {"writes": {"a.py": 1}},
        },
        status="completed",
    )
    assert "completion_gate" in metadata
    reset = reset_tool_metrics(metadata)
    assert reset["tool_metrics"]["tools_total"] == 0
    assert "completion_gate" not in reset


def test_trajectory_step_verification_updates_metrics():
    metrics = empty_tool_metrics()
    metrics = apply_tool_event(
        metrics,
        {
            "event_type": "trajectory_step_recorded",
            "payload": {"step": {"kind": "verification", "success": True, "command": "pytest"}},
        },
    )
    assert metrics["verify_attempted"] == 1
    assert metrics["verify_ok"] == 1
