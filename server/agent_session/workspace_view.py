from __future__ import annotations

from typing import Any

from .artifact_extractor import AgentArtifactExtractor
from .models import (
    AgentAsyncTaskMetricsResponse,
    AgentAsyncTaskResponse,
    AgentWorkspaceAsyncTasks,
    AgentWorkspaceResponse,
)
from .orchestration_planner import AgentOrchestrationPlanner


class AgentWorkspaceViewService:
    def __init__(self, session_service: Any):
        self.session_service = session_service
        self.artifact_extractor = AgentArtifactExtractor()
        self.orchestration_planner = AgentOrchestrationPlanner()

    def get_workspace(self, session_id: str) -> AgentWorkspaceResponse:
        session = self.session_service.get_session(session_id)
        overview = self.session_service.get_overview(session_id)
        async_task_list = self.session_service.list_async_subtasks(session_id, "all")
        async_metrics = self.session_service.get_async_subtask_metrics(session_id)
        metadata = dict(session.metadata or {})
        ui_state = dict(metadata.get("ui_state") or {})
        diagnostics = dict(overview.diagnostics or {})
        timeline = list(ui_state.get("timeline") or [])
        tasks = list(async_task_list.get("tasks") or [])
        artifacts, changed_files = self.artifact_extractor.extract(session.parts, tasks, overview.artifacts)
        next_actions = self.orchestration_planner.plan(
            session=session,
            artifacts=artifacts,
            changed_files=changed_files,
            tasks=tasks,
            pending_permission=ui_state.get("pending_permission"),
        )

        return AgentWorkspaceResponse(
            session=session,
            status_text=dict(ui_state.get("status_text") or {}),
            timeline=timeline,
            pending_permission=ui_state.get("pending_permission"),
            task_plan=overview.task_plan,
            diagnostics=diagnostics,
            async_tasks=AgentWorkspaceAsyncTasks(
                tasks=[AgentAsyncTaskResponse(**task) for task in tasks],
                metrics=AgentAsyncTaskMetricsResponse(**async_metrics),
            ),
            artifacts=artifacts,
            changed_files=changed_files,
            next_actions=next_actions,
            recent_events=list(overview.recent_events or []),
        )
