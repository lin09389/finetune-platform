import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from ..types import ProgressInfo


class ProgressEvent(BaseModel):
    task_id: str
    event_type: str
    progress: float
    message: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProgressTracker:
    def __init__(self):
        self._tasks: dict[str, ProgressInfo] = {}
        self._event_subscribers: list[Callable[[ProgressEvent], None]] = []
        self._lock = asyncio.Lock()
        self._task_history: dict[str, list[ProgressEvent]] = {}
        self._max_history_size = 100

    async def start_task(
        self,
        task_id: str,
        total_steps: int = 100,
        initial_message: str = ""
    ) -> ProgressInfo:
        async with self._lock:
            progress_info = ProgressInfo(
                task_id=task_id,
                progress=0.0,
                status="started",
                message=initial_message or f"Task {task_id} started",
                current_step=0,
                total_steps=total_steps,
                eta_seconds=None
            )
            self._tasks[task_id] = progress_info
            self._task_history[task_id] = []

            await self._emit_event(ProgressEvent(
                task_id=task_id,
                event_type="started",
                progress=0.0,
                message=progress_info.message
            ))

            return progress_info

    async def update_progress(
        self,
        task_id: str,
        current_step: int,
        message: str = "",
        metadata: dict[str, Any] | None = None
    ) -> ProgressInfo | None:
        async with self._lock:
            if task_id not in self._tasks:
                return None

            task = self._tasks[task_id]
            task.current_step = current_step
            task.message = message or task.message

            if task.total_steps > 0:
                task.progress = current_step / task.total_steps

            if metadata:
                task.metadata = metadata

            eta = self._calculate_eta(task_id, current_step)
            task.eta_seconds = eta

            await self._emit_event(ProgressEvent(
                task_id=task_id,
                event_type="progress",
                progress=task.progress,
                message=message,
                metadata=metadata or {}
            ))

            return task

    async def complete_task(
        self,
        task_id: str,
        message: str = "Task completed"
    ) -> ProgressInfo | None:
        async with self._lock:
            if task_id not in self._tasks:
                return None

            task = self._tasks[task_id]
            task.progress = 1.0
            task.status = "completed"
            task.message = message
            task.current_step = task.total_steps
            task.eta_seconds = 0

            await self._emit_event(ProgressEvent(
                task_id=task_id,
                event_type="completed",
                progress=1.0,
                message=message
            ))

            return task

    async def fail_task(
        self,
        task_id: str,
        error_message: str = "Task failed"
    ) -> ProgressInfo | None:
        async with self._lock:
            if task_id not in self._tasks:
                return None

            task = self._tasks[task_id]
            task.status = "failed"
            task.message = error_message

            await self._emit_event(ProgressEvent(
                task_id=task_id,
                event_type="failed",
                progress=task.progress,
                message=error_message
            ))

            return task

    async def cancel_task(
        self,
        task_id: str,
        reason: str = "Task cancelled"
    ) -> ProgressInfo | None:
        async with self._lock:
            if task_id not in self._tasks:
                return None

            task = self._tasks[task_id]
            task.status = "cancelled"
            task.message = reason

            await self._emit_event(ProgressEvent(
                task_id=task_id,
                event_type="cancelled",
                progress=task.progress,
                message=reason
            ))

            return task

    async def get_progress(self, task_id: str) -> ProgressInfo | None:
        return self._tasks.get(task_id)

    async def get_all_tasks(self) -> dict[str, ProgressInfo]:
        return self._tasks.copy()

    async def get_active_tasks(self) -> list[ProgressInfo]:
        return [
            task for task in self._tasks.values()
            if task.status not in ["completed", "failed", "cancelled"]
        ]

    def subscribe(self, callback: Callable[[ProgressEvent], None]) -> None:
        self._event_subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[ProgressEvent], None]) -> None:
        if callback in self._event_subscribers:
            self._event_subscribers.remove(callback)

    async def _emit_event(self, event: ProgressEvent) -> None:
        if event.task_id in self._task_history:
            self._task_history[event.task_id].append(event)
            if len(self._task_history[event.task_id]) > self._max_history_size:
                self._task_history[event.task_id].pop(0)

        for callback in self._event_subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception:
                pass

    def _calculate_eta(self, task_id: str, current_step: int) -> float | None:
        if task_id not in self._task_history:
            return None

        history = self._task_history[task_id]
        if len(history) < 2:
            return None

        task = self._tasks.get(task_id)
        if not task or task.total_steps <= 0:
            return None

        recent_events = [e for e in history if e.event_type == "progress"][-10:]
        if len(recent_events) < 2:
            return None

        try:
            first_time = datetime.fromisoformat(recent_events[0].timestamp)
            last_time = datetime.fromisoformat(recent_events[-1].timestamp)
            time_diff = (last_time - first_time).total_seconds()

            if time_diff <= 0:
                return None

            steps_diff = recent_events[-1].progress - recent_events[0].progress
            if steps_diff <= 0:
                return None

            steps_per_second = steps_diff / time_diff
            remaining_progress = 1.0 - task.progress

            if steps_per_second > 0:
                eta = remaining_progress / steps_per_second
                return max(0, eta)
        except Exception:
            pass

        return None

    def get_progress_percentage(self, task_id: str) -> float:
        task = self._tasks.get(task_id)
        if task:
            return task.progress * 100
        return 0.0

    def get_eta_formatted(self, task_id: str) -> str:
        task = self._tasks.get(task_id)
        if not task or task.eta_seconds is None:
            return "N/A"

        eta = task.eta_seconds
        if eta < 60:
            return f"{int(eta)}s"
        elif eta < 3600:
            minutes = int(eta / 60)
            seconds = int(eta % 60)
            return f"{minutes}m {seconds}s"
        else:
            hours = int(eta / 3600)
            minutes = int((eta % 3600) / 60)
            return f"{hours}h {minutes}m"

    async def cleanup_completed_tasks(self, max_age_hours: int = 24) -> int:
        async with self._lock:
            cutoff = datetime.now() - timedelta(hours=max_age_hours)
            tasks_to_remove = []

            for task_id, task in self._tasks.items():
                if task.status in ["completed", "failed", "cancelled"]:
                    tasks_to_remove.append(task_id)

            for task_id in tasks_to_remove:
                del self._tasks[task_id]
                if task_id in self._task_history:
                    del self._task_history[task_id]

            return len(tasks_to_remove)
