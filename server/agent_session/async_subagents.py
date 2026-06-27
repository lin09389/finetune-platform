from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from copy import deepcopy
from datetime import datetime
from typing import Any

from .agent_registry import AgentRegistry
from .async_subagent_policy import resolve_async_subagent_target
from .execution_context import AgentDefinition
from .permission import default_deepagents_permission_metadata
from .repository import AgentSessionRepository
from .status import (
    ASYNC_SUBTASK_STATUSES,
    ASYNC_SUBTASK_TERMINAL_STATUSES,
    FAILED_SESSION_STATUSES,
    WAITING_SESSION_STATUSES,
)

logger = logging.getLogger(__name__)

CHILD_WAITING_STATUSES = WAITING_SESSION_STATUSES
CHILD_FAILURE_STATUSES = FAILED_SESSION_STATUSES

NotifyEvent = Callable[[str, dict[str, Any]], None]
InterruptSession = Callable[[str, str | None], Any]
ModelCall = Callable[[list[dict[str, str]]], Awaitable[str]]

INHERITED_CHILD_METADATA_KEYS = {
    "autonomy_mode",
    "deepagents_interrupt_on",
    "enabled_skill_sources",
    "memory_user_id",
    "org_id",
    "user_id",
}


def _now() -> str:
    return datetime.now().isoformat()


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _elapsed_ms(start: Any, end: Any) -> int | None:
    start_dt = _parse_time(start)
    end_dt = _parse_time(end)
    if not start_dt or not end_dt:
        return None
    return max(0, int((end_dt - start_dt).total_seconds() * 1000))


class AsyncSubagentService:
    def __init__(
        self,
        repository: AgentSessionRepository,
        notify_event: NotifyEvent,
        *,
        model_call: ModelCall | None = None,
        interrupt_session: InterruptSession | None = None,
        max_concurrency: int = 2,
    ):
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._tasks_lock = asyncio.Lock()
        self._semaphore: asyncio.Semaphore | None = None
        self._semaphore_loop: asyncio.AbstractEventLoop | None = None
        self.repository = repository
        self.notify_event = notify_event
        self.model_call = model_call
        self.interrupt_session = interrupt_session
        self.max_concurrency = max(1, max_concurrency)
        self.agent_registry = AgentRegistry()

    def set_model_call(self, model_call: ModelCall | None) -> None:
        self.model_call = model_call

    async def start_task(self, parent_session_id: str, subagent_type: str, description: str) -> dict[str, Any]:
        parent = self._require_parent(parent_session_id)
        description = description.strip()
        if not description:
            raise ValueError("Async subagent description is required")
        target = self._resolve_async_subagent(str(parent.get("agent_id") or ""), subagent_type)
        task = self.repository.create_subtask(
            {
                "parent_session_id": parent_session_id,
                "agent_name": target.id,
                "status": "pending",
                "input_json": {"description": description, "subagent_type": target.id, "revision": 1},
                "result_json": {},
                "previous_child_session_ids": [],
            }
        )
        self._record_subtask_event(task, "created", f"{target.name} 子任务已创建。", notify_parent=False)
        child = self._create_child_session(parent, target, task["id"], 1)
        task = self.repository.update_subtask(
            task["id"],
            child_session_id=child.get("id"),
            status="running",
            started_at=_now(),
            error=None,
        )
        self._publish_parent_part(parent_session_id, task, "running", f"{target.name} 子任务已启动。", "async_subtask_started")
        scheduled = await self._schedule_task(task["id"], str(child.get("id")), description)
        self._record_subtask_event(
            task,
            "scheduled" if scheduled else "schedule_skipped",
            "异步子任务已进入本地调度器。",
            notify_parent=False,
        )
        return self.task_response(task)

    def check_task(self, parent_session_id: str, task_id: str) -> dict[str, Any]:
        task = self._require_task(parent_session_id, task_id)
        task = self._refresh_from_child(task)
        task = self.repository.update_subtask(task["id"], last_checked_at=_now())
        return self.task_response(task, include_result=True)

    def list_tasks(self, parent_session_id: str, status_filter: str | None = None) -> dict[str, Any]:
        self._require_parent(parent_session_id)
        normalized = self._normalize_filter(status_filter)
        tasks = [
            self._refresh_from_child(task)
            for task in self.repository.list_subtasks(parent_session_id, normalized)
        ]
        return {
            "tasks": [self.task_response(task, include_result=True) for task in tasks],
            "status_filter": normalized,
        }

    async def cancel_task(self, parent_session_id: str, task_id: str, reason: str | None = None) -> dict[str, Any]:
        task = self._require_task(parent_session_id, task_id)
        if task.get("status") in ASYNC_SUBTASK_TERMINAL_STATUSES:
            return self.task_response(task, include_result=True)

        message = reason or "用户取消了异步子任务。"
        child_session_id = str(task.get("child_session_id") or "")
        if child_session_id:
            self._interrupt_child(child_session_id, message)
        await self._cancel_registered_task(task_id)
        result_json = dict(task.get("result_json") or {})
        result_json.update({"summary": message, "child_status": "interrupted"})
        updated = self.repository.update_subtask(
            task["id"],
            status="cancelled",
            error=message,
            result_json=result_json,
            cancelled_at=_now(),
            completed_at=_now(),
        )
        self._publish_parent_part(parent_session_id, updated, "cancelled", message, "async_subtask_cancelled")
        return self.task_response(updated, include_result=True)

    async def update_task(self, parent_session_id: str, task_id: str, description: str) -> dict[str, Any]:
        task = self._require_task(parent_session_id, task_id)
        parent = self._require_parent(parent_session_id)
        description = description.strip()
        if not description:
            raise ValueError("Async subagent description is required")
        target = self._resolve_async_subagent(str(parent.get("agent_id") or ""), str(task.get("agent_name") or ""))

        old_child_id = str(task.get("child_session_id") or "")
        if old_child_id and task.get("status") not in ASYNC_SUBTASK_TERMINAL_STATUSES:
            self._interrupt_child(old_child_id, "异步子任务已重启，旧子会话停止。")
            await self._cancel_registered_task(task_id)

        previous = list(task.get("previous_child_session_ids") or [])
        if old_child_id:
            previous.append(old_child_id)
        revision = int((task.get("input_json") or {}).get("revision") or 1) + 1
        child = self._create_child_session(parent, target, task["id"], revision)
        updated = self.repository.update_subtask(
            task["id"],
            child_session_id=child.get("id"),
            status="running",
            input_json={"description": description, "subagent_type": target.id, "revision": revision},
            result_json={"summary": "异步子任务已重启。", "recovered": False},
            error=None,
            restart_count=int(task.get("restart_count") or 0) + 1,
            previous_child_session_ids=previous,
            started_at=_now(),
            completed_at=None,
            cancelled_at=None,
        )
        self._publish_parent_part(parent_session_id, updated, "running", f"{target.name} 子任务已重启。", "async_subtask_restarted")
        scheduled = await self._schedule_task(updated["id"], str(child.get("id")), description)
        self._record_subtask_event(
            updated,
            "scheduled" if scheduled else "schedule_skipped",
            "重启后的异步子任务已进入本地调度器。",
            notify_parent=False,
        )
        return self.task_response(updated, include_result=True)

    async def recover_running_tasks(self) -> dict[str, Any]:
        scheduled = 0
        synchronized = 0
        for task in self.repository.list_all_subtasks(statuses={"pending", "running"}):
            refreshed = self._refresh_from_child(task)
            if refreshed.get("status") in ASYNC_SUBTASK_TERMINAL_STATUSES:
                self._record_subtask_event(refreshed, "recovery_skipped", "异步子任务已是终态，恢复流程跳过。", notify_parent=False)
                synchronized += 1
                continue
            child_session_id = str(refreshed.get("child_session_id") or "")
            description = str((refreshed.get("input_json") or {}).get("description") or "")
            if not child_session_id or not description:
                failed = self.repository.update_subtask(
                    refreshed["id"],
                    status="failed",
                    error="Async subtask cannot be recovered because child session or description is missing.",
                    completed_at=_now(),
                )
                self._record_subtask_event(failed, "recovery_failed", "异步子任务缺少 child session 或描述，无法恢复。", notify_parent=False)
                synchronized += 1
                continue
            if await self._schedule_task(refreshed["id"], child_session_id, description, recovered=True):
                self._record_subtask_event(refreshed, "recovered", "异步子任务已在服务启动时重新调度。", payload={"recovered": True})
                scheduled += 1
        return {"scheduled": scheduled, "synchronized": synchronized}

    def task_events(self, parent_session_id: str, task_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        self._require_task(parent_session_id, task_id)
        events = self.repository.list_subtask_events(task_id)
        return events[-limit:] if limit else events

    def parent_events(self, parent_session_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        self._require_parent(parent_session_id)
        events = self.repository.list_parent_subtask_events(parent_session_id)
        return events[-limit:] if limit else events

    def metrics(self, parent_session_id: str) -> dict[str, Any]:
        self._require_parent(parent_session_id)
        return self.repository.summarize_subtask_metrics(parent_session_id)

    async def shutdown(self) -> None:
        async with self._tasks_lock:
            tasks = list(self._tasks.values())
            self._tasks.clear()
        for task in tasks:
            if hasattr(task, "cancel"):
                task.cancel()
        awaitables = [task for task in tasks if hasattr(task, "__await__")]
        if awaitables:
            await asyncio.gather(*awaitables, return_exceptions=True)

    async def _cancel_registered_task(self, task_id: str) -> None:
        async with self._tasks_lock:
            task = self._tasks.pop(task_id, None)
        if task is None or not hasattr(task, "cancel") or task.done():
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _schedule_task(self, task_id: str, child_session_id: str, description: str, *, recovered: bool = False) -> bool:
        async with self._tasks_lock:
            running = self._tasks.get(task_id)
            if running and hasattr(running, "done") and not running.done():
                return False
            task = asyncio.create_task(self._run_task(task_id, child_session_id, description, recovered=recovered))
            self._tasks[task_id] = task
            if hasattr(task, "add_done_callback"):
                task.add_done_callback(
                    lambda done: self._tasks.pop(task_id, None) if self._tasks.get(task_id) is done else None
                )
            return True

    async def _run_task(self, task_id: str, child_session_id: str, description: str, *, recovered: bool = False) -> None:
        semaphore = self._semaphore_for_loop()
        async with semaphore:
            task = self.repository.get_subtask(task_id)
            if not task or task.get("child_session_id") != child_session_id or task.get("status") != "running":
                if task:
                    self._record_subtask_event(
                        task,
                        "stale_child_ignored",
                        "旧 child session 结果已忽略。",
                        payload={"child_session_id": child_session_id},
                        notify_parent=False,
                    )
                return
            self._record_subtask_event(task, "started", "异步子任务开始执行。", payload={"recovered": recovered}, notify_parent=False)
            try:
                from .deepagents_runtime import DeepAgentsSessionRunner

                child_runner = DeepAgentsSessionRunner(
                    repository=self.repository,
                    notify_event=self.notify_event,
                    model_call=self.model_call,
                    async_subagent_service=None,
                )
                result = await child_runner.run_prompt(child_session_id, description)
                fresh = self.repository.get_subtask(task_id)
                if not fresh or fresh.get("child_session_id") != child_session_id or fresh.get("status") != "running":
                    if fresh:
                        self._record_subtask_event(
                            fresh,
                            "stale_child_ignored",
                            "旧 child session 完成结果已忽略。",
                            payload={"child_session_id": child_session_id},
                            notify_parent=False,
                        )
                    return
                status = "completed" if result.get("status") == "completed" else "failed"
                summary = self._latest_summary(child_session_id) or f"子任务状态：{result.get('status')}"
                result_json = {
                    "summary": summary,
                    "child_status": result.get("status"),
                    "child_session_id": child_session_id,
                    "recovered": recovered,
                }
                updated = self.repository.update_subtask(
                    task_id,
                    status=status,
                    result_json=result_json,
                    error=None if status == "completed" else summary,
                    completed_at=_now(),
                )
                event_type = "async_subtask_completed" if status == "completed" else "async_subtask_failed"
                self._publish_parent_part(str(updated.get("parent_session_id") or ""), updated, status, summary, event_type)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                fresh = self.repository.get_subtask(task_id)
                if not fresh or fresh.get("child_session_id") != child_session_id or fresh.get("status") != "running":
                    if fresh:
                        self._record_subtask_event(
                            fresh,
                            "stale_child_ignored",
                            "旧 child session 异常结果已忽略。",
                            payload={"child_session_id": child_session_id},
                            notify_parent=False,
                        )
                    return
                updated = self.repository.update_subtask(task_id, status="failed", error=str(exc)[:1200], completed_at=_now())
                self._publish_parent_part(
                    str(updated.get("parent_session_id") or ""),
                    updated,
                    "failed",
                    f"异步子任务失败：{str(exc)[:400]}",
                    "async_subtask_failed",
                )

    def _semaphore_for_loop(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        if self._semaphore is None or self._semaphore_loop is not loop:
            self._semaphore = asyncio.Semaphore(self.max_concurrency)
            self._semaphore_loop = loop
        return self._semaphore

    def _create_child_session(self, parent: dict[str, Any], target: AgentDefinition, task_id: str, revision: int) -> dict[str, Any]:
        parent_metadata = dict(parent.get("metadata") or {})
        return self.repository.create_session(
            {
                "chat_session_id": parent.get("chat_session_id"),
                "agent_id": target.id,
                "status": "running",
                "title": f"{target.name} async task",
                "project_path": parent.get("project_path"),
                "provider": parent.get("provider"),
                "model": parent.get("model"),
                "metadata": {
                    **default_deepagents_permission_metadata(),
                    **self._child_inherited_metadata(parent_metadata),
                    "parent_session_id": parent.get("id"),
                    "async_task_id": task_id,
                    "async_task_revision": revision,
                    "async_subagent": True,
                },
            }
        )

    @staticmethod
    def _child_inherited_metadata(parent_metadata: dict[str, Any]) -> dict[str, Any]:
        return {
            key: deepcopy(parent_metadata[key])
            for key in INHERITED_CHILD_METADATA_KEYS
            if key in parent_metadata
        }

    def _require_parent(self, parent_session_id: str) -> dict[str, Any]:
        parent = self.repository.get_session(parent_session_id)
        if not parent:
            raise ValueError("Parent agent session not found")
        return parent

    def _require_task(self, parent_session_id: str, task_id: str) -> dict[str, Any]:
        task = self.repository.get_subtask(task_id.strip())
        if not task or task.get("parent_session_id") != parent_session_id:
            raise ValueError("Async subagent task not found")
        return task

    def _resolve_async_subagent(self, parent_agent_id: str, subagent_type: str) -> AgentDefinition:
        return resolve_async_subagent_target(self.agent_registry, parent_agent_id, subagent_type)

    def _refresh_from_child(self, task: dict[str, Any]) -> dict[str, Any]:
        if task.get("status") not in {"pending", "running"} or not task.get("child_session_id"):
            return task
        child = self.repository.get_session(str(task.get("child_session_id")))
        child_status = str((child or {}).get("status") or "")
        if child_status == "completed":
            summary = self._latest_summary(str(task.get("child_session_id"))) or "异步子任务已完成。"
            updated = self.repository.update_subtask(
                task["id"],
                status="completed",
                result_json={"summary": summary, "child_status": child_status},
                completed_at=_now(),
            )
            self._record_subtask_event(updated, "completed", summary)
            return updated
        if child_status in CHILD_WAITING_STATUSES:
            summary = self._latest_summary(str(task.get("child_session_id"))) or f"子任务状态：{child_status}"
            result_json = dict(task.get("result_json") or {})
            result_json.update({"summary": summary, "child_status": child_status})
            updated = self.repository.update_subtask(task["id"], status="running", result_json=result_json, error=None)
            self._record_subtask_event(updated, "waiting_permission", summary)
            return updated
        if child_status in CHILD_FAILURE_STATUSES:
            summary = self._latest_summary(str(task.get("child_session_id"))) or f"子任务状态：{child_status}"
            updated = self.repository.update_subtask(
                task["id"],
                status="failed",
                result_json={"summary": summary, "child_status": child_status},
                error=summary,
                completed_at=_now(),
            )
            self._record_subtask_event(updated, "failed", summary)
            return updated
        return task

    def _interrupt_child(self, child_session_id: str, reason: str) -> None:
        if self.interrupt_session is not None:
            self.interrupt_session(child_session_id, reason)
            return
        child = self.repository.get_session(child_session_id)
        if child and str(child.get("status") or "") not in {"completed", "failed", "interrupted"}:
            metadata = dict(child.get("metadata") or {})
            metadata["interrupt_requested"] = True
            metadata["interrupted_at"] = _now()
            self.repository.update_session(child_session_id, status="interrupted", metadata=metadata)

    def _publish_parent_part(self, parent_session_id: str, task: dict[str, Any], status: str, content: str, event_type: str) -> None:
        if not parent_session_id:
            return
        short_event_type = event_type.removeprefix("async_subtask_")
        self._record_subtask_event(task, short_event_type, content, status=status, notify_parent=False)
        child_state = self._child_state_payload(task)
        payload = {
            "runtime": "deepagents",
            "task_id": task.get("id"),
            "child_session_id": task.get("child_session_id"),
            "agent_name": task.get("agent_name"),
            "agent_role": "async_subagent",
            "async_status": status,
            **child_state,
            "health_status": self._health_status(task),
            "chunk_type": "async_task",
        }
        part = self.repository.add_part(
            parent_session_id,
            "summary",
            status="failed" if status == "failed" else ("completed" if status in {"completed", "cancelled"} else "running"),
            title=f"异步子任务：{task.get('agent_name')}",
            content=content,
            payload=payload,
        )
        event = self.repository.add_event(
            parent_session_id,
            event_type,
            content,
            {
                "session_id": parent_session_id,
                "part_id": part.get("id"),
                "part_type": "summary",
                "status": part.get("status"),
                "summary": content,
                "part": part,
                **payload,
            },
        )
        self.notify_event(parent_session_id, event)

    def _record_subtask_event(
        self,
        task: dict[str, Any],
        event_type: str,
        message: str,
        *,
        status: str | None = None,
        payload: dict[str, Any] | None = None,
        notify_parent: bool = True,
    ) -> dict[str, Any]:
        parent_session_id = str(task.get("parent_session_id") or "")
        event = self.repository.add_subtask_event(
            str(task.get("id") or ""),
            parent_session_id,
            event_type,
            message,
            child_session_id=task.get("child_session_id"),
            status=status or task.get("status"),
            payload={
                "agent_name": task.get("agent_name"),
                "restart_count": task.get("restart_count") or 0,
                "health_status": self._health_status(task),
                **self._child_state_payload(task),
                **(payload or {}),
            },
        )
        if notify_parent and parent_session_id:
            child_state = self._child_state_payload(task)
            parent_event = self.repository.add_event(
                parent_session_id,
                f"async_subtask_{event_type}",
                message,
                {
                    "session_id": parent_session_id,
                    "task_id": task.get("id"),
                    "child_session_id": task.get("child_session_id"),
                    "agent_name": task.get("agent_name"),
                    "agent_role": "async_subagent",
                    "async_status": status or task.get("status"),
                    **child_state,
                    "health_status": self._health_status(task),
                    "chunk_type": "async_task",
                    "subtask_event": event,
                    "summary": message,
                },
            )
            self.notify_event(parent_session_id, parent_event)
        return event

    def _child_state_payload(self, task: dict[str, Any]) -> dict[str, Any]:
        child_session_id = str(task.get("child_session_id") or "")
        result = task.get("result_json") or {}
        child = self.repository.get_session(child_session_id) if child_session_id else None
        child_status = str((child or {}).get("status") or result.get("child_status") or "")
        metadata = dict((child or {}).get("metadata") or {})
        ui_state = metadata.get("ui_state") if isinstance(metadata.get("ui_state"), dict) else {}
        pending_permission = ui_state.get("pending_permission") if isinstance(ui_state, dict) else None
        pending_permission_part_id = (
            pending_permission.get("part_id")
            if isinstance(pending_permission, dict)
            else None
        )
        has_pending_permission = bool(pending_permission) or child_status in CHILD_WAITING_STATUSES
        return {
            "child_status": child_status or None,
            "has_pending_permission": has_pending_permission,
            "pending_permission_part_id": pending_permission_part_id,
        }

    def _latest_summary(self, session_id: str) -> str:
        for part in reversed(self.repository.list_parts(session_id)):
            if part.get("type") == "summary" and part.get("content"):
                return str(part.get("content"))
        return ""

    @staticmethod
    def _normalize_filter(status_filter: str | None) -> str:
        normalized = (status_filter or "all").strip().lower()
        if normalized not in ASYNC_SUBTASK_STATUSES | {"all"}:
            raise ValueError(f"Invalid async task status filter: {status_filter}")
        return normalized

    def task_response(self, task: dict[str, Any], *, include_result: bool = False) -> dict[str, Any]:
        result = task.get("result_json") or {}
        if not include_result and task.get("status") not in ASYNC_SUBTASK_TERMINAL_STATUSES:
            result = {}
        events = self.repository.list_subtask_events(str(task.get("id") or ""))
        tail_events = events[-20:] if include_result else []
        diagnostics = self._task_diagnostics(task, events)
        child_state = self._child_state_payload(task)
        return {
            "task_id": task.get("id"),
            "parent_session_id": task.get("parent_session_id"),
            "child_session_id": task.get("child_session_id"),
            "previous_child_session_ids": task.get("previous_child_session_ids") or [],
            "agent_name": task.get("agent_name"),
            "status": task.get("status"),
            "input": task.get("input_json") or {},
            "result": result,
            "error": task.get("error"),
            "restart_count": int(task.get("restart_count") or 0),
            "created_at": task.get("created_at"),
            "updated_at": task.get("updated_at"),
            "started_at": task.get("started_at"),
            "completed_at": task.get("completed_at"),
            "cancelled_at": task.get("cancelled_at"),
            "last_checked_at": task.get("last_checked_at"),
            "diagnostics": diagnostics,
            "events": tail_events,
            "duration_ms": self._duration_ms(task),
            "queue_wait_ms": _elapsed_ms(task.get("created_at"), task.get("started_at")),
            "health_status": self._health_status(task),
            **child_state,
        }

    def _task_diagnostics(self, task: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
        child_session_id = str(task.get("child_session_id") or "")
        child = self.repository.get_session(child_session_id) if child_session_id else None
        last = events[-1] if events else None
        warnings: list[str] = []
        status = str(task.get("status") or "")
        if status == "failed" and task.get("error"):
            warnings.append(str(task.get("error")))
        if status in {"pending", "running"} and not child_session_id:
            warnings.append("缺少 child session，任务可能无法执行。")
        return {
            "last_event_type": (last or {}).get("event_type"),
            "last_event_at": (last or {}).get("created_at"),
            "recovery_count": sum(1 for event in events if event.get("event_type") == "recovered"),
            "restart_count": int(task.get("restart_count") or 0),
            "child_status": (child or {}).get("status"),
            "registry_state": self._registry_state(str(task.get("id") or "")),
            "warnings": warnings,
        }

    def _registry_state(self, task_id: str) -> str:
        task = self._tasks.get(task_id)
        if task is None:
            return "idle"
        if hasattr(task, "done") and task.done():
            return "done"
        return "scheduled"

    @staticmethod
    def _duration_ms(task: dict[str, Any]) -> int | None:
        start = task.get("started_at") or task.get("created_at")
        end = task.get("completed_at") or task.get("cancelled_at")
        if not end and task.get("status") in {"pending", "running"}:
            end = _now()
        return _elapsed_ms(start, end)

    @staticmethod
    def _health_status(task: dict[str, Any]) -> str:
        status = str(task.get("status") or "")
        if status == "completed":
            return "ok"
        if status == "cancelled":
            return "cancelled"
        if status == "failed":
            return "failed"
        if status in {"pending", "running"}:
            return "waiting"
        return "attention"
