"""Thin contract for executing evaluation work through AgentSessionService.

This module intentionally does not import ``agent_session``.  Application wiring
passes the existing service and a local-only session driver; evaluation never
creates a second planning, approval, or tool-execution loop.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from .models import LiveExecutionBudget, LiveExecutionResult, ScenarioDefinition


class AgentSessionServiceContract(Protocol):
    """Subset of the existing service used by an application-owned driver."""

    def create_session(self, request: object, user_id: str | None = None) -> object: ...

    async def prompt(self, session_id: str, request: object) -> object: ...

    def get_session(self, session_id: str) -> object: ...

    def interrupt_session(self, session_id: str, reason: str | None = None) -> object: ...


AgentSessionDriver = Callable[
    [AgentSessionServiceContract, ScenarioDefinition, Path, str, LiveExecutionBudget],
    Awaitable[LiveExecutionResult],
]


class AgentSessionServiceEvaluationAdapter:
    """Reusable RealModelExecutor adapter delegated to the existing service."""

    def __init__(self, service: AgentSessionServiceContract, driver: AgentSessionDriver) -> None:
        self._service = service
        self._driver = driver

    async def execute(
        self,
        scenario: ScenarioDefinition,
        fixture_path: Path,
        *,
        model_id: str,
        budget: LiveExecutionBudget,
    ) -> LiveExecutionResult:
        return await self._driver(self._service, scenario, fixture_path, model_id, budget)
