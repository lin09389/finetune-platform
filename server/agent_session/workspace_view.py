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
from .runtime import describe_deepagents_mounts, describe_skill_sources, memory_files_for_project


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
        plan = self._extract_plan(session, ui_state)
        runtime = self._runtime_context(session, metadata)
        execution_timeline = self._execution_timeline(getattr(session, "parts", []) or [])
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
            vfs_mounts=runtime.vfs_mounts,
            skill_sources=runtime.skill_sources,
        )

    def _extract_plan(self, session: Any, ui_state: dict[str, Any]) -> AgentWorkspacePlan:
        metadata = dict(getattr(session, "metadata", None) or {})
        candidates = [
            ui_state.get("todos"),
            dict(ui_state.get("plan") or {}).get("todos") if isinstance(ui_state.get("plan"), dict) else None,
            metadata.get("todos"),
            dict(metadata.get("plan") or {}).get("todos") if isinstance(metadata.get("plan"), dict) else None,
            dict(metadata.get("task_plan") or {}).get("todos") if isinstance(metadata.get("task_plan"), dict) else None,
        ]
        for raw in candidates:
            todos = self._normalize_todos(raw, source="metadata")
            if todos:
                return AgentWorkspacePlan(todos=todos, source="metadata", updated_at=getattr(session, "updated_at", None))

        task_plan = metadata.get("task_plan")
        todos = self._todos_from_task_plan(task_plan)
        if todos:
            return AgentWorkspacePlan(todos=todos, source="task_plan", updated_at=getattr(session, "updated_at", None))

        todos = self._todos_from_parts(getattr(session, "parts", []) or [])
        if todos:
            return AgentWorkspacePlan(todos=todos, source="write_todos", updated_at=getattr(session, "updated_at", None))

        return AgentWorkspacePlan(todos=[], source="empty", updated_at=getattr(session, "updated_at", None))

    def _execution_timeline(self, parts: list[Any]) -> list[AgentExecutionTimelineItem]:
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

    def _todos_from_parts(self, parts: list[Any]) -> list[AgentTodoItem]:
        for part in reversed(parts):
            payload = dict(getattr(part, "payload", None) or {})
            tool_name = str(payload.get("tool") or payload.get("name") or "")
            if not tool_name and isinstance(payload.get("action"), dict):
                tool_name = str(payload["action"].get("name") or "")
            if tool_name != "write_todos":
                continue
            raw_args = payload.get("args") or payload.get("arguments") or payload.get("input") or {}
            if isinstance(raw_args, dict):
                todos = self._normalize_todos(raw_args.get("todos") or raw_args.get("items"), source="write_todos")
                if todos:
                    return todos
        return []

    def _todos_from_task_plan(self, task_plan: Any) -> list[AgentTodoItem]:
        if not isinstance(task_plan, dict):
            return []
        todos: list[AgentTodoItem] = []
        for stage in task_plan.get("stages") or []:
            if not isinstance(stage, dict):
                continue
            stage_id = str(stage.get("id") or f"stage_{len(todos) + 1}")
            stage_title = str(stage.get("title") or "阶段")
            todos.append(
                AgentTodoItem(
                    id=stage_id,
                    title=stage_title,
                    status=self._todo_status(stage.get("status")),
                    summary=str(stage.get("summary") or stage.get("description") or ""),
                    source="task_plan",
                )
            )
            for node in stage.get("nodes") or []:
                if not isinstance(node, dict):
                    continue
                todos.append(
                    AgentTodoItem(
                        id=str(node.get("id") or f"{stage_id}_node_{len(todos) + 1}"),
                        title=str(node.get("title") or node.get("tool") or "任务"),
                        status=self._todo_status(node.get("status")),
                        summary=str(node.get("summary") or node.get("description") or ""),
                        source="task_plan",
                    )
                )
        return todos

    def _normalize_todos(self, raw: Any, *, source: str) -> list[AgentTodoItem]:
        if not isinstance(raw, list):
            return []
        todos: list[AgentTodoItem] = []
        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("content") or item.get("task") or item.get("text") or "").strip()
            if not title:
                continue
            todos.append(
                AgentTodoItem(
                    id=str(item.get("id") or f"todo_{index + 1}"),
                    title=title,
                    status=self._todo_status(item.get("status")),
                    summary=str(item.get("summary") or item.get("description") or ""),
                    owner_agent=str(item.get("owner_agent") or item.get("agent") or "") or None,
                    source=source,
                    linked_artifact_id=item.get("linked_artifact_id"),
                    linked_task_id=item.get("linked_task_id") or item.get("task_id"),
                )
            )
        return todos

    @staticmethod
    def _todo_status(value: Any) -> str:
        normalized = str(value or "pending").lower()
        if normalized in {"in_progress", "running", "active"}:
            return "in_progress"
        if normalized in {"done", "complete", "completed", "success"}:
            return "completed"
        if normalized in {"blocked", "failed", "waiting", "waiting_approval", "waiting_permission"}:
            return "blocked"
        return "pending"

    def _runtime_context(self, session: Any, metadata: dict[str, Any]) -> AgentWorkspaceRuntimeContext:
        project_path = str(getattr(session, "project_path", None) or "")
        agent_id = str(getattr(session, "agent_id", None) or "build")
        user_id = str(metadata.get("user_id") or metadata.get("memory_user_id") or "default")
        org_id = str(metadata.get("org_id") or "default-org")
        enabled_skill_sources = metadata.get("enabled_skill_sources")
        if enabled_skill_sources is not None and not isinstance(enabled_skill_sources, list):
            enabled_skill_sources = None
        vfs_mounts = [
            AgentWorkspaceMount(**item)
            for item in describe_deepagents_mounts(
                project_path or ".",
                agent_id=agent_id,
                enabled_skill_sources=enabled_skill_sources,
            )
        ]
        skill_sources = [
            AgentWorkspaceSkillSource(**item)
            for item in describe_skill_sources(
                project_path or ".",
                agent_id=agent_id,
                enabled_skill_sources=enabled_skill_sources,
            )
        ]
        try:
            memory_files = memory_files_for_project(project_path or ".", user_id=user_id, agent_id=agent_id, org_id=org_id)
        except Exception:
            memory_files = []
        return AgentWorkspaceRuntimeContext(
            workspace_root=project_path or None,
            vfs_mounts=vfs_mounts,
            skill_sources=skill_sources,
            memory_files=memory_files,
        )
