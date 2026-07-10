from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agent_session.async_subagents import AsyncSubagentService
from agent_session.deepagents_runtime import DeepAgentsSessionRunner
from agent_session.events import AgentSessionEventBus
from agent_session.failure_guard import AgentFailureGuard
from agent_session.models import (
    AgentExecutionPlanRecoverRequest,
    AgentExecutionPlanRecoveryResponse,
    AgentMemoryFileResponse,
    AgentPromptRequest,
    AgentSessionCreate,
    AgentSessionOverviewResponse,
    AgentSessionPreferencesUpdate,
    AgentSessionResponse,
)
from agent_session.repository import AgentSessionRepository
from agent_session.session_state_machine import AgentSessionStateMachine
from agent_session.status import ACTIVE_SESSION_STATUSES, TERMINAL_SESSION_STATUSES
from agent_session.workspace_view import AgentWorkspaceViewService

from .services import (
    ApprovalService,
    BackgroundTaskManagerService,
    EventBroadcastService,
    ModelCallCoordinatorService,
    RecoveryService,
    SessionLifecycleService,
)

ModelCall = Callable[[list[dict[str, str]]], Awaitable[str]]


class AgentSessionService:
    _event_bus = AgentSessionEventBus()
    _event_queues = AgentSessionEventBus._queues
    _event_lock = AgentSessionEventBus._lock

    ACTIVE_STATUSES = ACTIVE_SESSION_STATUSES
    TERMINAL_STATUSES = TERMINAL_SESSION_STATUSES

    def __init__(
        self,
        repository: AgentSessionRepository | None = None,
        processor: Any | None = None,
        model_call: ModelCall | None = None,
    ):
        _ = processor
        self.repository = repository or AgentSessionRepository()
        self.model_call = model_call
        self.agent_registry: Any = self._create_agent_registry()
        self.lifecycle = SessionLifecycleService(self)
        self.model_call_coordinator = ModelCallCoordinatorService(self)
        self.background_manager = BackgroundTaskManagerService(self)
        self.approval_service = ApprovalService(self)
        self.recovery_service = RecoveryService(self)
        self.event_service = EventBroadcastService(self)
        self.async_subagent_service = AsyncSubagentService(
            self.repository,
            self.event_service._notify_event,
            model_call=self.model_call,
            interrupt_session=self.background_manager.interrupt_session,
        )
        self.deepagents_runner = DeepAgentsSessionRunner(
            repository=self.repository,
            notify_event=self.event_service._notify_event,
            model_call=self.model_call,
            async_subagent_service=self.async_subagent_service,
            interrupt_session=self.background_manager.interrupt_session,
        )
        self.workspace_view_service = AgentWorkspaceViewService(self)
        self.state_machine = AgentSessionStateMachine(self.repository)
        self.failure_guard = AgentFailureGuard(self.repository, self.state_machine, self.event_service._notify_event)

    def _create_agent_registry(self) -> Any:
        from agent_session.agent_registry import AgentRegistry
        return AgentRegistry()

    def subscribe_events(self, session_id: str) -> Any:
        return self.event_service.subscribe_events(session_id)

    def unsubscribe_events(self, session_id: str, queue: Any) -> None:
        self.event_service.unsubscribe_events(session_id, queue)

    def subscribe_global_events(self) -> Any:
        return self.event_service.subscribe_global_events()

    def unsubscribe_global_events(self, queue: Any) -> None:
        self.event_service.unsubscribe_global_events(queue)

    def _notify_event(self, session_id: str, event: dict[str, Any]) -> None:
        self.event_service._notify_event(session_id, event)

    def _sync_async_service_model_call(self) -> None:
        self.model_call_coordinator._sync_async_service_model_call()

    def _event(self, session_id: str, event_type: str, message: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.event_service._event(session_id, event_type, message, payload)

    def _attach_recovery_diagnostics(self, session: dict[str, Any]) -> dict[str, Any]:
        return self.event_service._attach_recovery_diagnostics(session)

    def _has_running_prompt_task(self, session_id: str) -> bool:
        return self.background_manager._has_running_prompt_task(session_id)

    async def _run_prompt_background(self, session_id: str, request: AgentPromptRequest, prompt_id: str) -> None:
        await self.background_manager._run_prompt_background(session_id, request, prompt_id)

    def _record_background_failure_fallback(self, session_id: str, original_exc: Exception, failure_exc: Exception) -> None:
        self.background_manager._record_background_failure_fallback(session_id, original_exc, failure_exc)

    async def start_async_subtask(self, session_id: str, subagent_type: str, description: str) -> dict[str, Any]:
        self.model_call_coordinator._sync_async_service_model_call()
        return await self.async_subagent_service.start_task(session_id, subagent_type, description)

    def check_async_subtask(self, session_id: str, task_id: str) -> dict[str, Any]:
        return self.async_subagent_service.check_task(session_id, task_id)

    def list_async_subtasks(self, session_id: str, status_filter: str | None = None) -> dict[str, Any]:
        return self.async_subagent_service.list_tasks(session_id, status_filter)

    def list_async_subtask_events(self, session_id: str, task_id: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        if task_id:
            return self.async_subagent_service.task_events(session_id, task_id, limit)
        return self.async_subagent_service.parent_events(session_id, limit)

    def get_async_subtask_metrics(self, session_id: str) -> dict[str, Any]:
        return self.async_subagent_service.metrics(session_id)

    async def cancel_async_subtask(self, session_id: str, task_id: str, reason: str | None = None) -> dict[str, Any]:
        self.model_call_coordinator._sync_async_service_model_call()
        return await self.async_subagent_service.cancel_task(session_id, task_id, reason)

    async def update_async_subtask(self, session_id: str, task_id: str, description: str) -> dict[str, Any]:
        self.model_call_coordinator._sync_async_service_model_call()
        return await self.async_subagent_service.update_task(session_id, task_id, description)

    def _set_recovery_latch(self, session_id: str, node_id: str, recovery_id: str, action: str) -> None:
        self.recovery_service._set_recovery_latch(session_id, node_id, recovery_id, action)

    def _start_recovery_prompt_background(
        self,
        session_id: str,
        node: dict[str, Any],
        action: str,
        instruction: str,
        recovery_id: str,
        background_tasks: Any,
    ) -> None:
        self.recovery_service._start_recovery_prompt_background(session_id, node, action, instruction, recovery_id, background_tasks)

    async def recover_execution_node(
        self,
        session_id: str,
        node_id: str,
        request: AgentExecutionPlanRecoverRequest,
        background_tasks: Any,
    ) -> AgentExecutionPlanRecoveryResponse:
        return await self.recovery_service.recover_execution_node(session_id, node_id, request, background_tasks)

    async def recover_async_subtasks(self) -> dict[str, Any]:
        return await self.recovery_service.recover_async_subtasks()

    def recover_active_sessions_after_restart(self) -> dict[str, Any]:
        return self.recovery_service.recover_active_sessions_after_restart()

    async def shutdown_async_subtasks(self) -> None:
        await self.recovery_service.shutdown_async_subtasks()

    def create_session(self, request: AgentSessionCreate, user_id: str | None = None) -> AgentSessionResponse:
        return self.lifecycle.create_session(request, user_id)

    def get_session(self, session_id: str) -> AgentSessionResponse:
        return self.lifecycle.get_session(session_id)

    def update_session_preferences(
        self,
        session_id: str,
        request: AgentSessionPreferencesUpdate,
    ) -> AgentSessionResponse:
        return self.lifecycle.update_session_preferences(session_id, request)

    def list_sessions(self, user_id: str, include_all: bool = False, limit: int = 100) -> list[AgentSessionResponse]:
        return self.lifecycle.list_sessions(user_id, include_all, limit)

    def get_overview(self, session_id: str) -> AgentSessionOverviewResponse:
        return self.lifecycle.get_overview(session_id)

    def get_workspace(self, session_id: str) -> Any:
        return self.lifecycle.get_workspace(session_id)

    def list_memory_files(self, session_id: str) -> list[AgentMemoryFileResponse]:
        return self.lifecycle.list_memory_files(session_id)

    def read_memory_file(self, session_id: str, path: str) -> AgentMemoryFileResponse:
        return self.lifecycle.read_memory_file(session_id, path)

    def validate_project_path(self, project_path: str | None) -> str:
        return self.lifecycle.validate_project_path(project_path)

    async def prompt(self, session_id: str, request: AgentPromptRequest) -> AgentSessionResponse:
        return await self.background_manager.prompt(session_id, request)

    def record_prompt_failure(self, session_id: str, exc: Exception) -> dict[str, Any]:
        return self.background_manager.record_prompt_failure(session_id, exc)

    async def _resume_permission_background(self, session_id: str, decision: dict[str, Any]) -> None:
        await self.approval_service._resume_permission_background(session_id, decision)

    def _stream_part_snapshot(self, event: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
        return self.event_service._stream_part_snapshot(event, payload)

    def start_prompt_background(
        self,
        session_id: str,
        request: AgentPromptRequest,
        background_tasks: Any | None,
    ) -> AgentSessionResponse:
        return self.background_manager.start_prompt_background(session_id, request, background_tasks)

    async def start_prompt_detached(
        self,
        session_id: str,
        request: AgentPromptRequest,
    ) -> AgentSessionResponse:
        return await self.background_manager.start_prompt_detached(session_id, request)

    def interrupt_session(self, session_id: str, reason: str | None = None) -> AgentSessionResponse:
        return self.background_manager.interrupt_session(session_id, reason)

    def approve_permission(self, part_id: str, approved: bool) -> AgentSessionResponse:
        return self.approval_service.approve_permission(part_id, approved)

    async def approve_permission_async(
        self,
        part_id: str,
        approved: bool,
        background_tasks: Any,
    ) -> AgentSessionResponse:
        return await self.approval_service.approve_permission_async(part_id, approved, background_tasks)

    async def decide_permission_async(self, part_id: str, decisions: list[dict[str, Any]], background_tasks: Any) -> AgentSessionResponse:
        return await self.approval_service.decide_permission_async(part_id, decisions, background_tasks)

    def start_permission_resume_background(
        self,
        part_id: str,
        decisions: list[dict[str, Any]],
        background_tasks: Any,
    ) -> AgentSessionResponse:
        return self.approval_service.start_permission_resume_background(part_id, decisions, background_tasks)

    def list_events(self, session_id: str, since_event_id: str | None = None) -> list[dict[str, Any]]:
        return self.repository.list_events_after(session_id, since_event_id)

    def build_stream_chunk(self, event: dict[str, Any]) -> dict[str, Any]:
        return self.event_service.build_stream_chunk(event)

    def build_session_snapshot_chunk(self, session_id: str) -> dict[str, Any]:
        return self.event_service.build_session_snapshot_chunk(session_id)
