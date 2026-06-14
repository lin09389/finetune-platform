from __future__ import annotations

from typing import Any

from .artifact_extractor import AgentArtifactExtractor
from .models import (
    AgentAsyncTaskMetricsResponse,
    AgentAsyncTaskResponse,
    AgentExecutionTimelineItem,
    AgentTodoItem,
    AgentWorkspaceAsyncTasks,
    AgentWorkspaceMount,
    AgentWorkspacePlan,
    AgentWorkspaceResponse,
    AgentWorkspaceRuntimeContext,
    AgentWorkspaceSkillSource,
)
from .orchestration_planner import AgentOrchestrationPlanner
from .execution_plan import repair_execution_plan, todos_from_execution_plan
from .runtime_policy import AgentRuntimePolicy, build_agent_runtime_policy


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
        policy = self._runtime_policy(session, metadata)
        raw_execution_plan = metadata.get("execution_plan")
        execution_plan = raw_execution_plan if isinstance(raw_execution_plan, dict) else policy.execution_plan.model_dump()
        execution_plan, plan_warnings = repair_execution_plan(execution_plan, default_agent_id=str(getattr(session, "agent_id", None) or "build"))
        if plan_warnings:
            diagnostics["execution_plan_warnings"] = plan_warnings[-20:]
        plan = self._extract_plan(session, ui_state, execution_plan=execution_plan)
        runtime = self._runtime_context(session, metadata, policy=policy, execution_plan=execution_plan)
        execution_timeline = self._execution_timeline(getattr(session, "parts", []) or [], list(overview.recent_events or []))
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
            plan=plan,
            todos=plan.todos,
            diagnostics=diagnostics,
            async_tasks=AgentWorkspaceAsyncTasks(
                tasks=[AgentAsyncTaskResponse(**task) for task in tasks],
                metrics=AgentAsyncTaskMetricsResponse(**async_metrics),
            ),
            artifacts=artifacts,
            changed_files=changed_files,
            next_actions=next_actions,
            execution_timeline=execution_timeline,
            recent_events=list(overview.recent_events or []),
            runtime=runtime,
            runtime_policy=runtime.policy,
            resource_profile=runtime.resource_profile,
            execution_plan=runtime.execution_plan,
            vfs_mounts=runtime.vfs_mounts,
            skill_sources=runtime.skill_sources,
        )

    def _extract_plan(self, session: Any, ui_state: dict[str, Any], *, execution_plan: dict[str, Any] | None = None) -> AgentWorkspacePlan:
        _ = ui_state
        execution_todos = todos_from_execution_plan(execution_plan)
        if execution_todos:
            return AgentWorkspacePlan(
                todos=[AgentTodoItem(**todo) for todo in execution_todos],
                source="execution_plan",
                updated_at=getattr(session, "updated_at", None),
            )
        return AgentWorkspacePlan(todos=[], source="execution_plan", updated_at=getattr(session, "updated_at", None))

    def _execution_timeline(self, parts: list[Any], events: list[dict[str, Any]] | None = None) -> list[AgentExecutionTimelineItem]:
        items: list[AgentExecutionTimelineItem] = []
        for part in parts:
            part_type = str(getattr(part, "type", "") or "")
            item_type = self._execution_item_type(part_type)
            if not item_type:
                continue
            payload = dict(getattr(part, "payload", None) or {})
            part_id = str(getattr(part, "id", "") or "")
            title = str(getattr(part, "title", None) or self._tool_name(payload) or self._execution_title(item_type))
            summary = str(getattr(part, "content", None) or payload.get("summary") or payload.get("message") or "")[:300]
            duration_ms = payload.get("duration_ms") or payload.get("elapsed_ms")
            try:
                duration = int(duration_ms) if duration_ms is not None else None
            except (TypeError, ValueError):
                duration = None
            items.append(
                AgentExecutionTimelineItem(
                    id=f"exec:{part_id}",
                    type=item_type,
                    title=title,
                    status=getattr(part, "status", None),
                    summary=summary,
                    source_part_id=part_id,
                    created_at=getattr(part, "created_at", None),
                    duration_ms=duration,
                    payload_excerpt=self._payload_excerpt(payload),
                )
            )
        for event in events or []:
            event_type = str(event.get("event_type") or "")
            if not event_type.startswith("node_recovery_"):
                continue
            payload = dict(event.get("payload") or {})
            source_id = str(payload.get("node_id") or payload.get("recovery_id") or event.get("id") or "")
            items.append(
                AgentExecutionTimelineItem(
                    id=f"exec:{event.get('id')}",
                    type="recovery",
                    title=self._recovery_title(event_type),
                    status=event_type.removeprefix("node_recovery_"),
                    summary=str(event.get("message") or payload.get("summary") or "")[:300],
                    source_part_id=source_id,
                    created_at=event.get("created_at"),
                    duration_ms=None,
                    payload_excerpt=self._payload_excerpt(payload),
                )
            )
        return items

    @staticmethod
    def _execution_item_type(part_type: str) -> str | None:
        if part_type in {"tool_call", "tool_result", "command", "permission", "summary", "error"}:
            return part_type
        return None

    @staticmethod
    def _execution_title(item_type: str) -> str:
        return {
            "tool_call": "Tool call",
            "tool_result": "Tool result",
            "command": "Command",
            "permission": "Permission",
            "summary": "Summary",
            "error": "Error",
        }.get(item_type, item_type)

    @staticmethod
    def _recovery_title(event_type: str) -> str:
        return {
            "node_recovery_requested": "Recovery requested",
            "node_recovery_started": "Recovery started",
            "node_recovery_completed": "Recovery completed",
            "node_recovery_failed": "Recovery failed",
            "node_recovery_rejected": "Recovery rejected",
        }.get(event_type, "Recovery")

    @staticmethod
    def _tool_name(payload: dict[str, Any]) -> str:
        tool = payload.get("tool") or payload.get("name")
        if not tool and isinstance(payload.get("action"), dict):
            tool = payload["action"].get("name")
        if not tool and isinstance(payload.get("action_requests"), list) and payload["action_requests"]:
            first = payload["action_requests"][0]
            if isinstance(first, dict):
                tool = first.get("name")
        command = payload.get("command")
        if not tool and command:
            tool = " ".join(str(item) for item in command) if isinstance(command, list) else str(command)
        return str(tool or "")

    @staticmethod
    def _payload_excerpt(payload: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "tool",
            "name",
            "command",
            "exit_code",
            "args",
            "arguments",
            "action",
            "action_requests",
            "stdout",
            "stderr",
            "error",
            "message",
            "node_id",
            "recovery_id",
            "old_task_id",
            "new_task_id",
        )
        excerpt: dict[str, Any] = {}
        for key in keys:
            if key not in payload:
                continue
            value = payload[key]
            if isinstance(value, str):
                excerpt[key] = value[:500] + ("..." if len(value) > 500 else "")
            elif isinstance(value, list):
                excerpt[key] = value[:5]
            elif isinstance(value, dict):
                excerpt[key] = {str(k): v for k, v in list(value.items())[:10]}
            else:
                excerpt[key] = value
        return excerpt

    def _runtime_policy(self, session: Any, metadata: dict[str, Any]) -> AgentRuntimePolicy:
        project_path = str(getattr(session, "project_path", None) or "")
        agent_id = str(getattr(session, "agent_id", None) or "build")
        agent = self.session_service.agent_registry.get(agent_id)
        return build_agent_runtime_policy(
            agent=agent,
            agent_id=agent_id,
            project_path=project_path or ".",
            metadata=metadata,
            provider=getattr(session, "provider", None),
            model=getattr(session, "model", None),
            runtime_kind="agent_session",
            thread_id=str(metadata.get("deepagents_thread_id") or f"agent_session:{getattr(session, 'id', '')}:deepagents"),
            checkpointer=True,
            agent_registry=self.session_service.agent_registry,
        )

    def _runtime_context(
        self,
        session: Any,
        metadata: dict[str, Any],
        *,
        policy: AgentRuntimePolicy | None = None,
        execution_plan: dict[str, Any] | None = None,
    ) -> AgentWorkspaceRuntimeContext:
        policy = policy or self._runtime_policy(session, metadata)
        policy_payload = policy.model_dump()
        if execution_plan is not None:
            policy_payload["execution_plan"] = execution_plan
        vfs_mounts = [AgentWorkspaceMount(**item) for item in policy_payload["vfs_mounts"]]
        skill_sources = [AgentWorkspaceSkillSource(**item) for item in policy_payload["skill_sources"]]
        return AgentWorkspaceRuntimeContext(
            workspace_root=policy.workspace_root,
            vfs_mounts=vfs_mounts,
            skill_sources=skill_sources,
            memory_files=policy.memory_files,
            policy=policy_payload,
            resource_profile=policy_payload["resource_profile"],
            execution_plan=policy_payload["execution_plan"],
        )
