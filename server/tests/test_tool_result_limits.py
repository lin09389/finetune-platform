"""Scheme A: tool result limits / offload detection."""
from __future__ import annotations

from agent_session.tool_result_limits import (
    detect_tool_result_offload,
    get_execute_max_output_bytes,
    get_tool_token_limit_before_evict,
    record_tool_offload_in_metadata,
    truncate_tool_result_for_ui,
)


def test_detect_offload_from_deepagents_message():
    text = (
        "Tool result too large, the result of this tool call call_1 was saved "
        "in the filesystem at this path: /large_tool_results/call_1\n\n"
        "You can read the result from the filesystem"
    )
    det = detect_tool_result_offload(text)
    assert det["offloaded"] is True
    assert det["path"] == "/large_tool_results/call_1"
    assert det["truncated"] is True


def test_detect_execute_byte_truncation():
    text = "lots of logs\n\n... Output truncated at 200000 bytes."
    det = detect_tool_result_offload(text)
    assert det["truncated"] is True
    assert det["execute_truncated_bytes"] == 200000


def test_truncate_tool_result_for_ui():
    big = "x" * 50_000
    out, truncated = truncate_tool_result_for_ui(big, max_chars=5_000)
    assert truncated is True
    assert len(out) < len(big)
    assert "UI truncated" in out


def test_record_tool_offload_in_metadata():
    meta = record_tool_offload_in_metadata(
        {},
        tool="execute",
        detection={"offloaded": True, "truncated": True, "path": "/large_tool_results/x"},
    )
    refresh = meta["context_refresh"]
    assert refresh["tool_offload_count"] == 1
    assert refresh["tool_truncate_count"] == 1
    assert refresh["recent_offloads"][0]["tool"] == "execute"


def test_settings_helpers_return_positive():
    assert get_execute_max_output_bytes() >= 8192
    assert get_tool_token_limit_before_evict() >= 1000
