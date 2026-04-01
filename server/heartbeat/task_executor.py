import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    CHECK = "check"
    REPORT = "report"
    REMINDER = "reminder"
    CUSTOM = "custom"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(init=False)
class TaskResult:
    task_id: str
    task_type: TaskType
    status: TaskStatus
    started_at: datetime
    completed_at: datetime | None
    result: dict[str, Any]
    error: str | None
    retries: int

    def __init__(self, task_id: str = "", task_type: TaskType = TaskType.CUSTOM, status: TaskStatus | None = None, started_at: datetime | None = None, completed_at: datetime | None = None, result: dict[str, Any] | None = None, error: str | None = None, retries: int = 0, success: bool | None = None, data: dict[str, Any] | None = None, message: str | None = None):
        self.task_id = task_id
        self.task_type = task_type
        if status is None:
            if success is True:
                status = TaskStatus.COMPLETED
            elif success is False:
                status = TaskStatus.FAILED
            else:
                status = TaskStatus.PENDING
        self.status = status
        self.started_at = started_at or datetime.now()
        self.completed_at = completed_at
        self.result = result if result is not None else (data or {})
        if message and "message" not in self.result:
            self.result["message"] = message
        self.error = error
        self.retries = retries

    @property
    def success(self) -> bool:
        return self.status == TaskStatus.COMPLETED

    @property
    def data(self) -> dict[str, Any]:
        return self.result


@dataclass
class ProactiveTask:
    id: str
    name: str
    task_type: TaskType
    description: str = ""
    schedule: str = "0"
    enabled: bool = True
    max_retries: int = 3
    retry_delay: int = 60
    timeout: int = 300
    config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class TaskExecutor:
    def __init__(self, workspace_path: Path | None = None):
        self._workspace_path = workspace_path
        self._tasks: dict[str, ProactiveTask] = {}
        self._results: dict[str, TaskResult] = {}
        self._handlers: dict[TaskType, Callable] = {}
        self._notification_handlers: list[Callable] = []
        self._register_default_handlers()

    def _register_default_handlers(self):
        self._handlers[TaskType.CHECK] = self._execute_check_task
        self._handlers[TaskType.REPORT] = self._execute_report_task
        self._handlers[TaskType.REMINDER] = self._execute_reminder_task

    def register_handler(self, task_type: TaskType, handler: Callable):
        self._handlers[task_type] = handler

    def register_notification_handler(self, handler: Callable):
        self._notification_handlers.append(handler)

    def add_task(self, task: ProactiveTask):
        self._tasks[task.id] = task

    def remove_task(self, task_id: str):
        self._tasks.pop(task_id, None)

    def get_task(self, task_id: str) -> ProactiveTask | None:
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> dict[str, ProactiveTask]:
        return self._tasks.copy()

    async def execute(self, task_type: TaskType, params: dict[str, Any] | None = None) -> TaskResult:
        params = params or {}
        task = ProactiveTask(
            id=f"task_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            name=task_type.value,
            task_type=task_type,
            config=params,
        )
        self.add_task(task)
        return await self.execute_task(task.id)

    async def execute_task(self, task_id: str) -> TaskResult:
        task = self._tasks.get(task_id)
        if not task:
            return TaskResult(task_id=task_id, task_type=TaskType.CUSTOM, status=TaskStatus.FAILED, started_at=datetime.now(), error="Task not found")
        if not task.enabled:
            return TaskResult(task_id=task_id, task_type=task.task_type, status=TaskStatus.CANCELLED, started_at=datetime.now(), error="Task is disabled")
        result = TaskResult(task_id=task.id, task_type=task.task_type, status=TaskStatus.RUNNING, started_at=datetime.now())
        self._results[task_id] = result
        try:
            handler = self._handlers.get(task.task_type)
            if not handler:
                raise ValueError(f"No handler for task type: {task.task_type}")
            async with asyncio.timeout(task.timeout):
                execution_result = await handler(task)
            result.status = TaskStatus.COMPLETED
            result.result = execution_result
            result.completed_at = datetime.now()
        except asyncio.TimeoutError:
            result.status = TaskStatus.FAILED
            result.error = f"Task timeout ({task.timeout}s)"
            result.completed_at = datetime.now()
        except Exception as e:
            result.status = TaskStatus.FAILED
            result.error = str(e)
            result.completed_at = datetime.now()
        await self._notify_result(result)
        return result

    async def execute_with_retry(self, task_id: str) -> TaskResult:
        task = self._tasks.get(task_id)
        if not task:
            return TaskResult(task_id=task_id, task_type=TaskType.CUSTOM, status=TaskStatus.FAILED, started_at=datetime.now(), error="Task not found")
        result = await self.execute_task(task_id)
        retry_count = 0
        while result.status == TaskStatus.FAILED and retry_count < task.max_retries:
            retry_count += 1
            result.retries = retry_count
            await asyncio.sleep(task.retry_delay)
            result = await self.execute_task(task_id)
        return result

    async def execute_all_pending(self) -> dict[str, TaskResult]:
        return {task_id: await self.execute_task(task_id) for task_id, task in self._tasks.items() if task.enabled}

    async def _execute_check_task(self, task: ProactiveTask) -> dict[str, Any]:
        target = task.config.get("target")
        return {"check_type": task.config.get("check_type", "general"), "target": target, "checked_at": datetime.now().isoformat(), "status": "ok", "findings": []}

    async def _execute_report_task(self, task: ProactiveTask) -> dict[str, Any]:
        report_type = task.config.get("report_type", "daily")
        return {"report_type": report_type, "generated_at": datetime.now().isoformat(), "content": f"report:{report_type}"}

    async def _execute_reminder_task(self, task: ProactiveTask) -> dict[str, Any]:
        return {"message": task.config.get("message", "reminder"), "sent_at": datetime.now().isoformat(), "status": "ok"}

    async def _notify_result(self, result: TaskResult):
        for handler in self._notification_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(result)
                else:
                    handler(result)
            except Exception:
                logger.exception("Notification handler failed")


_executor: TaskExecutor | None = None


def get_task_executor() -> TaskExecutor:
    global _executor
    if _executor is None:
        _executor = TaskExecutor()
    return _executor
