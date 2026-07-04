from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_session.service import AgentSessionService


class ModelCallCoordinatorService:
    def __init__(self, service: AgentSessionService) -> None:
        self.service = service

    def _sync_async_service_model_call(self) -> None:
        self.service.async_subagent_service.set_model_call(self.service.model_call)
        self.service.deepagents_runner.model_call = self.service.model_call
