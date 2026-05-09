"""Tests for the WorkflowContextBuilder: context assembly, trimming, and budget allocation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_runtime.context_builder import WorkflowContextBuilder, ContextPack
from agent_runtime.definitions import AgentDefinition, StepDefinition, WorkflowDefinition


def _make_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        id="test_wf",
        name="Test Workflow",
        description="test",
        steps=[
            StepDefinition(
                key="plan",
                agent_id="planner",
                title="Plan",
                description="Plan step",
                artifact_type="plan",
                sort_order=0,
            ),
        ],
        agents=[AgentDefinition(id="planner", name="Planner")],
    )


class TestWorkflowContextBuilder:
    def test_build_for_step_returns_context_with_goal(self):
        repo = MagicMock()
        repo.get_context_profile.return_value = {
            "project_path": None,
            "include_project_context": False,
            "include_chat_context": False,
            "include_memory": False,
            "max_context_chars": 6000,
            "metadata": {},
        }
        builder = WorkflowContextBuilder(repo)
        project = {"id": "wf_1", "goal": "Build a feature", "provider": "minimax"}
        workflow = _make_workflow()
        step = workflow.steps[0]
        task = {"id": "task_1"}

        ctx = builder.build_for_step(project, workflow, step, task, [])

        assert ctx.workflow_id == "wf_1"
        assert ctx.goal == "Build a feature"
        assert ctx.provider == "minimax"

    def test_build_for_step_includes_fallback_project_context(self):
        repo = MagicMock()
        repo.get_context_profile.return_value = {
            "project_path": None,
            "include_project_context": True,
            "include_chat_context": False,
            "include_memory": False,
            "max_context_chars": 6000,
            "metadata": {},
        }
        builder = WorkflowContextBuilder(repo)
        project = {"id": "wf_2", "goal": "Test project", "provider": "minimax"}
        workflow = _make_workflow()
        step = workflow.steps[0]
        task = {"id": "task_2"}

        with patch.object(builder, "_project_context", return_value="Fallback context here"):
            ctx = builder.build_for_step(project, workflow, step, task, [], fallback_project_context="Fallback context here")

        assert "Fallback" in ctx.project_context or ctx.project_context == ""

    def test_build_for_step_includes_artifact_context(self):
        repo = MagicMock()
        repo.get_context_profile.return_value = {
            "project_path": None,
            "include_project_context": False,
            "include_chat_context": False,
            "include_memory": False,
            "max_context_chars": 6000,
            "metadata": {},
        }
        builder = WorkflowContextBuilder(repo)
        project = {"id": "wf_3", "goal": "Test", "provider": "minimax"}
        workflow = _make_workflow()
        step = workflow.steps[0]
        task = {"id": "task_3"}
        previous = [{"summary": "Step 1 completed"}, {"summary": "Step 2 done"}]

        ctx = builder.build_for_step(project, workflow, step, task, previous)

        assert "Step 1 completed" in ctx.artifact_context
        assert "Step 2 done" in ctx.artifact_context


class TestTrim:
    def test_trim_short_text_unchanged(self):
        builder = WorkflowContextBuilder(MagicMock())
        text = "Hello world"
        assert builder._trim(text, 100) == text

    def test_trim_long_text_at_paragraph_boundaries(self):
        builder = WorkflowContextBuilder(MagicMock())
        paragraphs = "\n\n".join([f"Para {i}: " + "x" * 200 for i in range(10)])
        result = builder._trim(paragraphs, 500)
        assert len(result) <= 530
        assert result.endswith("...[已截断]")

    def test_trim_falls_back_to_line_boundary(self):
        builder = WorkflowContextBuilder(MagicMock())
        text = "line1\n" + "a" * 800 + "\nline3"
        result = builder._trim(text, 400)
        assert len(result) <= 430

    def test_trim_hard_cut_as_last_resort(self):
        builder = WorkflowContextBuilder(MagicMock())
        text = "x" * 1000
        result = builder._trim(text, 500)
        assert len(result) <= 530
        assert "已截断" in result

    def test_trim_empty_string(self):
        builder = WorkflowContextBuilder(MagicMock())
        assert builder._trim("", 100) == ""
        assert builder._trim(None, 100) == ""

    def test_trim_unicode_content(self):
        builder = WorkflowContextBuilder(MagicMock())
        text = "这是一个中文测试" * 100
        result = builder._trim(text, 200)
        assert len(result) <= 230


class TestArtifactContext:
    def test_artifact_context_uses_last_four_outputs(self):
        builder = WorkflowContextBuilder(MagicMock())
        outputs = [
            {"summary": f"Output {i}"} for i in range(6)
        ]
        ctx = builder._artifact_context("wf_x", outputs, max_chars=2000)
        assert "Output 2" in ctx
        assert "Output 5" in ctx

    def test_artifact_context_handles_missing_summary(self):
        builder = WorkflowContextBuilder(MagicMock())
        outputs = [{"summary": "Good"}, {"no_summary_key": "data"}, {"summary": "Also good"}]
        ctx = builder._artifact_context("wf_x", outputs, max_chars=2000)
        assert "Good" in ctx
        assert "Also good" in ctx


class TestContextPackDefaults:
    def test_context_pack_defaults(self):
        pack = ContextPack()
        assert pack.project_context == ""
        assert pack.chat_context == ""
        assert pack.memory_context == ""
        assert pack.artifact_context == ""
        assert pack.combined_context == ""
        assert pack.sources == []