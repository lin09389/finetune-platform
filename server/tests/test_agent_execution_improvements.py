"""Tests for agent execution layer improvements (Phase 1/3/4/6)."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Phase 1: Tool Loop Resilience
# ---------------------------------------------------------------------------


class TestSanitizeModelOutput:
    """Test JSON sanitization from noisy LLM outputs."""

    def test_clean_json_passthrough(self):
        from agent_runtime.tool_loop import _sanitize_model_output

        raw = '{"thought":"ok","tool":"finalize","arguments":{}}'
        assert _sanitize_model_output(raw) == raw

    def test_extract_from_markdown_fence(self):
        from agent_runtime.tool_loop import _sanitize_model_output

        raw = 'Here is the result:\n```json\n{"thought":"x","tool":"finalize","arguments":{}}\n```\nDone.'
        result = _sanitize_model_output(raw)
        parsed = json.loads(result)
        assert parsed["tool"] == "finalize"

    def test_extract_from_markdown_fence_no_lang(self):
        from agent_runtime.tool_loop import _sanitize_model_output

        raw = '```\n{"thought":"x","tool":"finalize","arguments":{}}\n```'
        result = _sanitize_model_output(raw)
        parsed = json.loads(result)
        assert parsed["tool"] == "finalize"

    def test_extract_embedded_json(self):
        from agent_runtime.tool_loop import _sanitize_model_output

        raw = 'I will call the tool: {"thought":"test","tool":"read_file","arguments":{"path":"a.py"}} end.'
        result = _sanitize_model_output(raw)
        parsed = json.loads(result)
        assert parsed["tool"] == "read_file"

    def test_empty_string(self):
        from agent_runtime.tool_loop import _sanitize_model_output

        assert _sanitize_model_output("") == ""

    def test_no_json_returns_original(self):
        from agent_runtime.tool_loop import _sanitize_model_output

        raw = "I don't know what to do."
        assert _sanitize_model_output(raw) == raw


class TestDynamicMaxIterations:
    """Test that max_iterations is read from agent definition."""

    def test_from_agent_definition(self):
        from agent_runtime.tool_loop import AgentToolLoop

        loop = AgentToolLoop(
            repository=MagicMock(),
            executor=MagicMock(),
            max_iterations=6,
        )
        step_input = {"agent": {"max_iterations": 10}}
        assert loop._resolve_max_iterations(step_input) == 10

    def test_fallback_to_instance_default(self):
        from agent_runtime.tool_loop import AgentToolLoop

        loop = AgentToolLoop(
            repository=MagicMock(),
            executor=MagicMock(),
            max_iterations=8,
        )
        step_input = {"agent": {}}
        assert loop._resolve_max_iterations(step_input) == 8

    def test_invalid_agent_max_iterations(self):
        from agent_runtime.tool_loop import AgentToolLoop

        loop = AgentToolLoop(
            repository=MagicMock(),
            executor=MagicMock(),
            max_iterations=6,
        )
        step_input = {"agent": {"max_iterations": -1}}
        assert loop._resolve_max_iterations(step_input) == 6

    def test_no_agent_in_step_input(self):
        from agent_runtime.tool_loop import AgentToolLoop

        loop = AgentToolLoop(
            repository=MagicMock(),
            executor=MagicMock(),
            max_iterations=5,
        )
        assert loop._resolve_max_iterations({}) == 5


# ---------------------------------------------------------------------------
# Phase 3: Step Retry + Rollback
# ---------------------------------------------------------------------------


class TestStepRetryPolicy:
    """Test the StepRetryPolicy dataclass."""

    def test_default_values(self):
        from agent_runtime.engine import StepRetryPolicy

        policy = StepRetryPolicy()
        assert policy.max_retries == 1
        assert policy.backoff_seconds == 2.0
        assert RuntimeError in policy.retry_on

    def test_custom_values(self):
        from agent_runtime.engine import StepRetryPolicy

        policy = StepRetryPolicy(max_retries=3, backoff_seconds=5.0)
        assert policy.max_retries == 3
        assert policy.backoff_seconds == 5.0


class TestPatchEngineRollback:
    """Test SafePatchEngine backup and rollback."""

    def test_backup_and_rollback_existing_file(self, tmp_path):
        from agent_runtime.patch_engine import SafePatchEngine

        target = tmp_path / "test.txt"
        target.write_text("original content", encoding="utf-8")

        engine = SafePatchEngine(tmp_path)
        engine.apply_file_writes([{"path": "test.txt", "content": "new content"}])

        assert target.read_text(encoding="utf-8") == "new content"
        assert engine.has_backup

        restored = engine.rollback()
        assert target.read_text(encoding="utf-8") == "original content"
        assert len(restored) == 1

    def test_backup_and_rollback_new_file(self, tmp_path):
        from agent_runtime.patch_engine import SafePatchEngine

        engine = SafePatchEngine(tmp_path)
        engine.apply_file_writes([{"path": "new_file.txt", "content": "hello"}])

        assert (tmp_path / "new_file.txt").exists()
        engine.rollback()
        assert not (tmp_path / "new_file.txt").exists()

    def test_clear_backup(self, tmp_path):
        from agent_runtime.patch_engine import SafePatchEngine

        target = tmp_path / "test.txt"
        target.write_text("original", encoding="utf-8")

        engine = SafePatchEngine(tmp_path)
        engine.apply_file_writes([{"path": "test.txt", "content": "new"}])
        assert engine.has_backup

        engine.clear_backup()
        assert not engine.has_backup

    def test_no_backup_initially(self, tmp_path):
        from agent_runtime.patch_engine import SafePatchEngine

        engine = SafePatchEngine(tmp_path)
        assert not engine.has_backup
        assert engine.rollback() == []


# ---------------------------------------------------------------------------
# Phase 4: Context Window Management
# ---------------------------------------------------------------------------


class TestContextManager:
    """Test ToolLoopContextManager."""

    def test_no_compression_below_threshold(self):
        from agent_runtime.context_manager import ToolLoopContextManager

        mgr = ToolLoopContextManager(summary_threshold=10)
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "initial"},
            {"role": "assistant", "content": '{"tool":"read_file"}'},
            {"role": "user", "content": "result"},
        ]
        assert not mgr.should_compress(messages)
        result = mgr.compress(messages)
        assert len(result) == len(messages)

    def test_compression_above_threshold(self):
        from agent_runtime.context_manager import ToolLoopContextManager

        mgr = ToolLoopContextManager(summary_threshold=6)
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "initial task"},
        ]
        # Add 10 assistant/user pairs
        for i in range(10):
            messages.append({"role": "assistant", "content": json.dumps({"tool": f"tool_{i}", "thought": f"step {i}"})})
            messages.append({"role": "user", "content": json.dumps({"tool": f"tool_{i}", "status": "completed", "summary": f"done {i}"})})

        assert mgr.should_compress(messages)
        result = mgr.compress(messages)
        # Should be shorter than original
        assert len(result) < len(messages)
        # Should preserve system + initial messages
        assert result[0]["role"] == "system"
        # Should preserve recent messages
        assert result[-1]["role"] == "user"

    def test_token_budget_triggers_compression(self):
        from agent_runtime.context_manager import ToolLoopContextManager

        mgr = ToolLoopContextManager(summary_threshold=100, token_budget=50, budget_ratio=0.5)
        messages = [
            {"role": "system", "content": "A" * 200},
            {"role": "user", "content": "B" * 200},
        ]
        # With tiny budget, should trigger compression
        assert mgr.should_compress(messages)

    def test_trim_large_payload(self):
        from agent_runtime.context_manager import ToolLoopContextManager

        mgr = ToolLoopContextManager()
        large = "line\n" * 5000
        trimmed = mgr.trim_large_payload(large, max_chars=100)
        assert len(trimmed) <= 140  # some margin for the truncation suffix
        assert "已截断" in trimmed


class TestTokenEstimation:
    """Test token estimation utility."""

    def test_empty_messages(self):
        from agent_runtime.context_manager import estimate_tokens

        assert estimate_tokens([]) == 0

    def test_estimates_increase_with_content(self):
        from agent_runtime.context_manager import estimate_tokens

        short = estimate_tokens([{"role": "user", "content": "hello"}])
        long = estimate_tokens([{"role": "user", "content": "hello " * 100}])
        assert long > short

    def test_cjk_text_uses_fewer_tokens_per_char(self):
        from agent_runtime.context_manager import _estimate_tokens_for_text

        cjk = _estimate_tokens_for_text("你好世界" * 10)
        latin = _estimate_tokens_for_text("abcd" * 10)
        # CJK should produce more tokens per character (1.5 vs 4 chars per token)
        assert cjk > latin


# ---------------------------------------------------------------------------
# Phase 6: Observability
# ---------------------------------------------------------------------------


class TestObservabilityModels:
    """Test observability model changes."""

    def test_step_log_has_trace_id(self):
        from agent_runtime.models import WorkflowStepLogResponse

        log = WorkflowStepLogResponse(
            id="1",
            workflow_id="w1",
            status="completed",
            trace_id="abc-123",
            created_at="2026-01-01",
        )
        assert log.trace_id == "abc-123"

    def test_tool_call_has_trace_id(self):
        from agent_runtime.models import WorkflowToolCallResponse

        call = WorkflowToolCallResponse(
            id="1",
            workflow_id="w1",
            tool_name="read_file",
            status="completed",
            trace_id="def-456",
            created_at="2026-01-01",
        )
        assert call.trace_id == "def-456"

    def test_observability_has_token_usage(self):
        from agent_runtime.models import WorkflowObservabilityResponse

        obs = WorkflowObservabilityResponse(
            workflow_id="w1",
            status="running",
            total_token_usage={"input": 1000, "output": 500},
        )
        assert obs.total_token_usage["input"] == 1000
        assert obs.total_token_usage["output"] == 500


class TestToolLoopResponseTokens:
    """Test AgentToolLoopResponse token tracking fields."""

    def test_response_includes_token_counts(self):
        from agent_runtime.tool_models import AgentToolLoopResponse
        from digital_team.models import AgentOutput

        response = AgentToolLoopResponse(
            output=AgentOutput(summary="done"),
            trace_id="trace-1",
            total_input_tokens=1500,
            total_output_tokens=300,
        )
        assert response.trace_id == "trace-1"
        assert response.total_input_tokens == 1500
        assert response.total_output_tokens == 300

    def test_response_defaults(self):
        from agent_runtime.tool_models import AgentToolLoopResponse
        from digital_team.models import AgentOutput

        response = AgentToolLoopResponse(output=AgentOutput(summary="done"))
        assert response.trace_id is None
        assert response.total_input_tokens == 0
        assert response.total_output_tokens == 0


# ---------------------------------------------------------------------------
# Phase 4.3: Smart trim
# ---------------------------------------------------------------------------


class TestSmartTrim:
    """Test context_builder improved _trim method."""

    def test_short_text_unchanged(self):
        from agent_runtime.context_builder import WorkflowContextBuilder

        builder = WorkflowContextBuilder(MagicMock())
        assert builder._trim("hello world", 100) == "hello world"

    def test_trims_at_paragraph_boundary(self):
        from agent_runtime.context_builder import WorkflowContextBuilder

        builder = WorkflowContextBuilder(MagicMock())
        text = "First paragraph.\n\nSecond paragraph.\n\nThird very long paragraph " + "x" * 200
        result = builder._trim(text, 80)
        assert "已截断" in result
        # Should have cut at a paragraph boundary
        assert result.count("\n\n") >= 1

    def test_trims_at_line_boundary(self):
        from agent_runtime.context_builder import WorkflowContextBuilder

        builder = WorkflowContextBuilder(MagicMock())
        text = "line1\nline2\nline3\n" + "x" * 200
        result = builder._trim(text, 30)
        assert "已截断" in result

    def test_empty_text(self):
        from agent_runtime.context_builder import WorkflowContextBuilder

        builder = WorkflowContextBuilder(MagicMock())
        assert builder._trim("", 100) == ""
        assert builder._trim(None, 100) == ""
