"""Compatibility wrapper for the internal runtime runner."""

from __future__ import annotations

from typing import Any

from agent_runtime.definitions import RuntimeExecutionContext
from agent_runtime.runner import AgentRuntimeRunner

from .models import AgentOutput


class DigitalTeamAgentRunner:
    def __init__(self, runtime_runner: AgentRuntimeRunner | None = None):
        self.runtime_runner = runtime_runner or AgentRuntimeRunner()

    async def execute(
        self,
        agent_id: str,
        context: RuntimeExecutionContext,
        step_input: dict[str, Any] | None = None,
    ) -> AgentOutput:
        return await self.runtime_runner.execute(agent_id, context, step_input or {})

    async def _chat(
        self,
        agent_id: str,
        provider_name: str,
        model: str | None,
        goal: str,
        project_path: str | None = None,
        project_context: str = "",
        step_input: dict[str, Any] | None = None,
    ) -> AgentOutput:
        return await self.execute(
            agent_id,
            RuntimeExecutionContext(
                workflow_id="digital_team_compat",
                goal=goal,
                project_path=project_path,
                project_context=project_context,
                provider=provider_name,
                model=model,
            ),
            step_input or {},
        )

    async def run_ceo(
        self,
        *,
        goal: str,
        project_path: str | None,
        project_context: str,
        provider: str,
        model: str | None,
    ) -> AgentOutput:
        return await self._chat(
            "planner",
            provider,
            model,
            goal,
            project_path=project_path,
            project_context=project_context,
        )

    async def run_developer(
        self,
        *,
        goal: str,
        ceo_output: dict[str, Any],
        project_path: str | None,
        project_context: str,
        provider: str,
        model: str | None,
    ) -> AgentOutput:
        return await self._chat(
            "implementer",
            provider,
            model,
            goal,
            project_path=project_path,
            project_context=project_context,
            step_input={"ceo_output": ceo_output},
        )

    async def run_reviewer(
        self,
        *,
        goal: str,
        developer_output: dict[str, Any],
        provider: str,
        model: str | None,
    ) -> AgentOutput:
        return await self._chat(
            "reviewer",
            provider,
            model,
            goal,
            step_input={"developer_output": developer_output},
        )
