"""Step 2 + B3: post-failure observation latch, exploration budget, summary enrichment."""
from __future__ import annotations

from agent_session.session_progress import (
    HARD_TOOL_BUDGET,
    SOFT_TOOL_BUDGET,
    apply_recovery_event,
    apply_tool_event,
    build_working_state_card,
    empty_tool_metrics,
    enrich_final_summary,
    evaluate_execute_blind_retry,
    evaluate_exploration_budget,
    mark_budget_soft_warned,
    normalize_command,
    reset_tool_metrics,
)


def test_normalize_command_collapses_whitespace():
    assert normalize_command("  python  -m   pytest  ") == "python -m pytest"


def test_recovery_blocks_same_and_different_execute_until_observation():
    """B3: latch blocks any execute after failure until observe tools run."""
    metadata = reset_tool_metrics({})
    metadata = apply_recovery_event(
        metadata,
        {
            "event_type": "tool_call_failed",
            "payload": {
                "tool": "execute",
                "error": "exit 1",
                "part": {"payload": {"tool": "execute", "input": {"command": "python cli.py -1"}}},
            },
        },
    )
    assert metadata["recovery_state"]["require_observation_before_retry"] is True

    same = evaluate_execute_blind_retry(metadata, "python cli.py -1")
    assert same is not None
    assert same["reason_code"] == "blind_execute_retry"
    assert same["same_command"] is True

    # B3: different command is also blocked until observation.
    other = evaluate_execute_blind_retry(metadata, "python cli.py 1")
    assert other is not None
    assert other["reason_code"] == "execute_without_observation"
    assert other["same_command"] is False

    # Successful different execute must NOT clear the latch (anti thrash).
    metadata = apply_recovery_event(
        metadata,
        {
            "event_type": "tool_call_completed",
            "payload": {
                "tool": "execute",
                "part": {"payload": {"input": {"command": "python cli.py 1"}}},
            },
        },
    )
    assert metadata["recovery_state"]["require_observation_before_retry"] is True
    assert evaluate_execute_blind_retry(metadata, "python -m py_compile cli.py") is not None

    # Observation clears latch.
    metadata = apply_recovery_event(
        metadata,
        {"event_type": "tool_call_completed", "payload": {"tool": "read_file"}},
    )
    assert metadata["recovery_state"]["require_observation_before_retry"] is False
    assert metadata["recovery_state"]["cleared_by"] == "read_file"
    assert evaluate_execute_blind_retry(metadata, "python cli.py -1") is None
    assert evaluate_execute_blind_retry(metadata, "python cli.py 1") is None


def test_working_state_card_mentions_b3_latch():
    metadata = reset_tool_metrics({})
    metadata = apply_recovery_event(
        metadata,
        {
            "event_type": "tool_call_failed",
            "payload": {
                "tool": "execute",
                "error": "TypeError",
                "part": {"payload": {"input": {"command": "npx tsc --noEmit"}}},
            },
        },
    )
    card = build_working_state_card(metadata)
    assert "失败恢复门闩" in card
    assert "不限" in card or "B3" in card
    assert "npx tsc" in card


def test_exploration_budget_soft_then_hard():
    metadata = {"tool_metrics": {**empty_tool_metrics(), "tools_total": SOFT_TOOL_BUDGET - 1}}
    soft = evaluate_exploration_budget(metadata, tool="glob")
    assert soft is not None
    assert soft["level"] == "soft"
    metadata = mark_budget_soft_warned(metadata)
    # After soft warned, same threshold does not re-warn until hard.
    assert evaluate_exploration_budget(metadata, tool="glob") is None

    metadata["tool_metrics"]["tools_total"] = HARD_TOOL_BUDGET - 1
    hard = evaluate_exploration_budget(metadata, tool="ls")
    assert hard is not None
    assert hard["level"] == "hard"
    assert hard["reason_code"] == "exploration_budget_exhausted"


def test_enrich_final_summary_appends_required_sections():
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
    text = enrich_final_summary("修好了索引错误。", metadata, status="completed")
    assert "已完成项" in text
    assert "变更文件" in text
    assert "验证结果" in text
    assert "app.py" in text
    assert "平台完成核对" in text


def test_observe_total_increments_for_read_tools():
    metrics = empty_tool_metrics()
    metrics = apply_tool_event(metrics, {"event_type": "tool_call_started", "payload": {"tool": "glob"}})
    metrics = apply_tool_event(metrics, {"event_type": "tool_call_started", "payload": {"tool": "read_file"}})
    assert metrics["observe_total"] == 2
    assert metrics["tools_total"] == 2
