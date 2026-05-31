from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Awaitable, Callable

from .agent_registry import AgentRegistry
from .execution_context import AgentDefinition
from .repository import AgentSessionRepository

logger = logging.getLogger(__name__)

ASYNC_SUBTASK_STATUSES = {"pending", "running", "completed", "failed", "cancelled"}
ASYNC_SUBTASK_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
CHILD_FAILURE_STATUSES = {"failed", "interrupted", "needs_manual_review", "waiting_approval", "waiting_permission"}

NotifyEvent = Callable[[str, dict[str, Any]], None]
InterruptSession = Callable[[str, str | None], Any]
ModelCall = Callable[[list[dict[str, str]]], Awaitable[str]]


def _now() -> str:
    return datetime.now().isoformat()


class AsyncSubagentService:
    _tasks: dict[str, asyncio.Task[Any]] = {}
    _tasks_lock = asyncio.Lock()
    _semaphore: asyncio.Semaphore | None = None
    _semaphore_loop: asyncio.AbstractEventLoop | None = None

    def __init__(
        self,
        repository: AgentSessionRepository,
        notify_event: NotifyEvent,
        *,
        model_call: ModelCall | None = None,
        interrupt_session: InterruptSession | None = None,
        max_concurrency: int = 2,
    ):
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
        child = self._create_child_session(parent, target, task["id"], 1)
        task = self.repository.update_subtask(
            task["id"],
            child_session_id=child.get("id"),
            status="running",
            started_at=_now(),
            error=None,
        )
        self._publish_parent_part(parent_session_id, task, "running", f"{target.name} 子任务已启动。", "async_subtask_started")
        await self._schedule_task(task["id"], str(child.get("id")), description)
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
        await self._schedule_task(updated["id"], str(child.get("id")), description)
        return self.task_response(updated, include_result=True)

    async def recover_running_tasks(self) -> dict[str, Any]:
        scheduled = 0
        synchronized = 0
        for task in self.repository.list_all_subtasks(statuses={"pending", "running"}):
            refreshed = self._refresh_from_child(task)
            if refreshed.get("status") in ASYNC_SUBTASK_TERMINAL_STATUSES:
                synchronized += 1
                continue
            child_session_id = str(refreshed.get("child_session_id") or "")
            description = str((refreshed.get("input_json") or {}).get("description") or "")
            if not child_session_id or not description:
                self.repository.update_subtask(
                    refreshed["id"],
                    status="failed",
                    error="Async subtask cannot be recovered because child session or description is missing.",
                    completed_at=_now(),
                )
                synchronized += 1
                continue
            if await self._schedule_task(refreshed["id"], child_session_id, description, recovered=True):
                scheduled += 1
        return {"scheduled": scheduled, "synchronized": synchronized}

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
                return
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
        if self.__class__._semaphore is None or self.__class__._semaphore_loop is not loop:
            self.__class__._semaphore = asyncio.Semaphore(self.max_concurrency)
            self.__class__._semaphore_loop = loop
        return self.__class__._semaphore

    def _create_child_session(self, parent: dict[str, Any], target: AgentDefinition, task_id: str, revision: int) -> dict[str, Any]:
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
                    "parent_session_id": parent.get("id"),
                    "async_task_id": task_id,
                    "async_task_revision": revision,
                    "async_subagent": True,
                    "deepagents_interrupt_on": True,
                },
            }
        )

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
        parent = self.agent_registry.get(parent_agent_id)
        requested = subagent_type.strip()
        target_id = requested if parent and requested in parent.handoff_targets else requested.lower()
        if not parent or target_id not in parent.handoff_targets:
            allowed = ", ".join(parent.handoff_targets if parent else [])
            raise ValueError(f"Unknown async subagent type '{subagent_type}'. Available types: {allowed}")
        target = self.agent_registry.get(target_id)
        if target is None or target.mode != "subagent":
            raise ValueError(f"Async target '{subagent_type}' is not a subagent")
        return target

    def _refresh_from_child(self, task: dict[str, Any]) -> dict[str, Any]:
        if task.get("status") not in {"pending", "running"} or not task.get("child_session_id"):
            return task
        child = self.repository.get_session(str(task.get("child_session_id")))
        child_status = str((child or {}).get("status") or "")
        if child_status == "completed":
            summary = self._latest_summary(str(task.get("child_session_id"))) or "异步子任务已完成。"
            return self.repository.update_subtask(
                task["id"],
                status="completed",
                result_json={"summary": summary, "child_status": child_status},
                completed_at=_now(),
            )
        if child_status in CHILD_FAILURE_STATUSES:
            summary = self._latest_summary(str(task.get("child_session_id"))) or f"子任务状态：{child_status}"
            return self.repository.update_subtask(
                task["id"],
                status="failed",
                result_json={"summary": summary, "child_status": child_status},
                error=summary,
                completed_at=_now(),
            )
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
        payload = {
            "runtime": "deepagents",
            "task_id": task.get("id"),
            "child_session_id": task.get("child_session_id"),
            "agent_name": task.get("agent_name"),
            "agent_role": "async_subagent",
            "async_status": status,
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

    @staticmethod
    def task_response(task: dict[str, Any], *, include_result: bool = False) -> dict[str, Any]:
        result = task.get("result_json") or {}
        if not include_result and task.get("status") not in ASYNC_SUBTASK_TERMINAL_STATUSES:
            result = {}
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
        }
