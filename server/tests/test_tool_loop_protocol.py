"""Tests for the tool loop protocol: JSON sanitization, text detection, and parsing."""

from __future__ import annotations

import json
import pytest

from agent_runtime_legacy.tool_loop import _sanitize_model_output
from agent_runtime_legacy.tool_models import AgentToolRequest, AgentToolResult, AgentToolLoopState, AgentToolLoopResponse
from digital_team.models import AgentOutput


class TestSanitizeModelOutput:
    def test_clean_json_object(self):
        raw = '{"thought": "planning", "tool": "list_files", "arguments": {"pattern": "*.py"}}'
        assert json.loads(_sanitize_model_output(raw))["tool"] == "list_files"

    def test_markdown_fenced_json(self):
        raw = '```json\n{"thought": "looking", "tool": "search_code", "arguments": {"query": "TODO"}}\n```'
        result = _sanitize_model_output(raw)
        parsed = json.loads(result)
        assert parsed["tool"] == "search_code"

    def test_markdown_fenced_without_json_label(self):
        raw = '```\n{"thought": "", "tool": "read_file", "arguments": {"path": "main.py"}}\n```'
        result = _sanitize_model_output(raw)
        parsed = json.loads(result)
        assert parsed["tool"] == "read_file"

    def test_surrounding_text_with_json(self):
        raw = 'Here is my response:\n{"thought": "ok", "tool": "finalize", "arguments": {"summary": "done"}}\nHope that helps!'
        result = _sanitize_model_output(raw)
        parsed = json.loads(result)
        assert parsed["tool"] == "finalize"

    def test_json_array_wrapped(self):
        raw = '[{"thought": "step1", "tool": "list_files", "arguments": {}}]'
        result = _sanitize_model_output(raw)
        parsed = json.loads(result)
        assert isinstance(parsed, list)

    def test_empty_or_whitespace(self):
        assert _sanitize_model_output("") == ""
        assert _sanitize_model_output("   ").strip() == ""

    def test_no_json_found(self):
        raw = "This is just plain text with no JSON at all"
        result = _sanitize_model_output(raw)
        assert result == raw


class TestAgentToolRequest:
    def test_valid_request(self):
        req = AgentToolRequest(thought="listing files", tool="list_files", arguments={"pattern": "*.py"})
        assert req.tool == "list_files"
        assert req.arguments == {"pattern": "*.py"}

    def test_default_thought(self):
        req = AgentToolRequest(tool="read_file", arguments={"path": "main.py"})
        assert req.thought == ""

    def test_default_arguments(self):
        req = AgentToolRequest(tool="finalize", arguments={})
        assert req.arguments == {}


class TestAgentToolResult:
    def test_completed_result(self):
        result = AgentToolResult(
            tool="list_files",
            status="completed",
            summary="Found 5 files",
            payload={"files": ["a.py", "b.py"]},
        )
        assert result.status == "completed"
        assert result.payload["files"] == ["a.py", "b.py"]

    def test_blocked_result(self):
        result = AgentToolResult(
            tool="propose_patch",
            status="blocked",
            summary="Patch requires approval",
            blocked_reason="Source file not previously read",
            permission_decision="ask",
        )
        assert result.status == "blocked"
        assert result.permission_decision == "ask"


class TestAgentToolLoopState:
    def test_default_state(self):
        state = AgentToolLoopState(
            workflow_id="wf_1",
            step_id="step_1",
            agent_id="implementer",
        )
        assert state.iteration == 0
        assert state.max_iterations == 6
        assert state.results == []

    def test_custom_max_iterations(self):
        state = AgentToolLoopState(
            workflow_id="wf_1",
            agent_id="planner",
            max_iterations=10,
        )
        assert state.max_iterations == 10


class TestAgentToolLoopResponse:
    def test_default_response(self):
        output = AgentOutput(summary="done", tasks=[], risks=[], artifacts=[], next_action="", requires_approval=False)
        resp = AgentToolLoopResponse(output=output)
        assert resp.needs_manual_review is False
        assert resp.tool_calls == []
        assert resp.fallback_summary_used is False
        assert resp.parse_repair_count == 0

