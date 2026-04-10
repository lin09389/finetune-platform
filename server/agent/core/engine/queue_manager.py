import asyncio
import heapq
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskPriority(int, Enum):
    LOW = 1
    NORMAL = 5
    HIGH = 10
    URGENT = 20
    CRITICAL = 30


class TaskStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    RETRYING = "retrying"


@dataclass(order=True)
class PrioritizedTask:
    priority: int
    sequence: int
    task_id: str = field(compare=False)
    action: str = field(compare=False)
    params: dict[str, Any] = field(compare=False)
    created_at: datetime = field(compare=False)
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)
    retry_count: int = field(default=0, compare=False)
    max_retries: int = field(default=3, compare=False)
    timeout_seconds: float = field(default=60.0, compare=False)


class TaskInfo(BaseModel):
    task_id: str = Field(default="")
    action: str = Field(default="")
    params: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=TaskPriority.NORMAL)
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    retry_count: int = Field(default=0)
    max_retries: int = Field(default=3)
    error_message: str = Field(default="")
    result: dict[str, Any] | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "action": self.action,
            "params": self.params,
            "priority": self.priority,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error_message": self.error_message,
            "result": self.result,
            "metadata": self.metadata,
        }


class QueueStats(BaseModel):
    total_tasks: int = Field(default=0)
    pending_tasks: int = Field(default=0)
    running_tasks: int = Field(default=0)
    completed_tasks: int = Field(default=0)
    failed_tasks: int = Field(default=0)
    cancelled_tasks: int = Field(default=0)
    average_wait_time_ms: float = Field(default=0.0)
    average_execution_time_ms: float = Field(default=0.0)


class QueueManager:
    def __init__(
        self,
        max_concurrent: int = 5,
        default_timeout: float = 60.0,
        default_max_retries: int = 3,
    ):
        self.max_concurrent = max_concurrent
        self.default_timeout = default_timeout
        self.default_max_retries = default_max_retries

        self._queue: list[PrioritizedTask] = []
        self._sequence = 0
        self._tasks: dict[str, TaskInfo] = {}
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._executor: Callable | None = None
        self._running = False
        self._worker_task: asyncio.Task | None = None
        self._semaphore = asyncio.Semaphore(max_concurrent)

        self._completed_count = 0
        self._failed_count = 0
        self._cancelled_count = 0
        self._total_wait_time_ms = 0.0
        self._total_execution_time_ms = 0.0

    def set_executor(self, executor: Callable[[str, dict[str, Any]], Awaitable[Any]]) -> None:
        self._executor = executor

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker_task
            self._worker_task = None

    async def _worker_loop(self) -> None:
        while self._running:
            try:
                task = await self._dequeue()
                if task:
                    asyncio.create_task(self._execute_task(task))
                else:
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.1)

    async def enqueue(
        self,
        action: str,
        params: dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        metadata: dict[str, Any] | None = None,
        max_retries: int | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        task_id = str(uuid.uuid4())

        prioritized_task = PrioritizedTask(
            priority=priority.value,
            sequence=self._sequence,
            task_id=task_id,
            action=action,
            params=params,
            created_at=datetime.now(),
            metadata=metadata or {},
            retry_count=0,
            max_retries=max_retries if max_retries is not None else self.default_max_retries,
            timeout_seconds=timeout_seconds if timeout_seconds is not None else self.default_timeout,
        )

        self._sequence += 1

        task_info = TaskInfo(
            task_id=task_id,
            action=action,
            params=params,
            priority=priority.value,
            status=TaskStatus.QUEUED,
            created_at=prioritized_task.created_at,
            max_retries=prioritized_task.max_retries,
            metadata=metadata or {},
        )

        async with self._lock:
            heapq.heappush(self._queue, prioritized_task)
            self._tasks[task_id] = task_info

        return task_id

    async def _dequeue(self) -> PrioritizedTask | None:
        async with self._lock:
            if not self._queue:
                return None
            return heapq.heappop(self._queue)

    async def _execute_task(self, task: PrioritizedTask) -> None:
        if not self._executor:
            return

        async with self._semaphore:
            task_info = self._tasks.get(task.task_id)
            if not task_info:
                return

            if task_info.status == TaskStatus.CANCELLED:
                return

            task_info.status = TaskStatus.RUNNING
            task_info.started_at = datetime.now()

            wait_time = (task_info.started_at - task_info.created_at).total_seconds() * 1000
            self._total_wait_time_ms += wait_time

            try:
                result = await asyncio.wait_for(
                    self._executor(task.action, task.params),
                    timeout=task.timeout_seconds,
                )

                task_info.status = TaskStatus.COMPLETED
                task_info.completed_at = datetime.now()
                task_info.result = result if isinstance(result, dict) else {"value": result}

                execution_time = (task_info.completed_at - task_info.started_at).total_seconds() * 1000
                self._total_execution_time_ms += execution_time
                self._completed_count += 1

            except asyncio.TimeoutError:
                task_info.status = TaskStatus.TIMEOUT
                task_info.error_message = f"Task timed out after {task.timeout_seconds}s"
                task_info.completed_at = datetime.now()

                if task.retry_count < task.max_retries:
                    await self._retry_task(task)
                else:
                    self._failed_count += 1

            except asyncio.CancelledError:
                task_info.status = TaskStatus.CANCELLED
                task_info.completed_at = datetime.now()
                self._cancelled_count += 1

            except Exception as e:
                task_info.status = TaskStatus.FAILED
                task_info.error_message = str(e)
                task_info.completed_at = datetime.now()

                if task.retry_count < task.max_retries:
                    await self._retry_task(task)
                else:
                    self._failed_count += 1

    async def _retry_task(self, task: PrioritizedTask) -> None:
        task_info = self._tasks.get(task.task_id)
        if not task_info:
            return

        task_info.status = TaskStatus.RETRYING
        task_info.retry_count += 1

        retry_task = PrioritizedTask(
            priority=task.priority,
            sequence=self._sequence,
            task_id=task.task_id,
            action=task.action,
            params=task.params,
            created_at=datetime.now(),
            metadata=task.metadata,
            retry_count=task.retry_count + 1,
            max_retries=task.max_retries,
            timeout_seconds=task.timeout_seconds,
        )

        self._sequence += 1

        async with self._lock:
            heapq.heappush(self._queue, retry_task)

    async def cancel_task(self, task_id: str) -> bool:
        async with self._lock:
            task_info = self._tasks.get(task_id)
            if not task_info:
                return False

            if task_info.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return False

            task_info.status = TaskStatus.CANCELLED
            task_info.completed_at = datetime.now()
            self._cancelled_count += 1

            return True

    async def get_task_status(self, task_id: str) -> TaskInfo | None:
        return self._tasks.get(task_id)

    async def get_task_result(self, task_id: str) -> dict[str, Any] | None:
        task_info = self._tasks.get(task_id)
        if task_info and task_info.status == TaskStatus.COMPLETED:
            return task_info.result
        return None

    async def list_tasks(
        self,
        status: TaskStatus | None = None,
        limit: int = 100,
    ) -> list[TaskInfo]:
        tasks = list(self._tasks.values())

        if status:
            tasks = [t for t in tasks if t.status == status]

        tasks.sort(key=lambda x: x.created_at, reverse=True)
        return tasks[:limit]

    async def clear_completed_tasks(self, max_age_hours: int = 24) -> int:
        cutoff = datetime.now()
        count = 0

        async with self._lock:
            to_remove = []
            for task_id, task_info in self._tasks.items():
                if (
                    task_info.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
                    and task_info.completed_at
                ):
                    age_hours = (cutoff - task_info.completed_at).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        to_remove.append(task_id)

            for task_id in to_remove:
                del self._tasks[task_id]
                count += 1

        return count

    def get_queue_length(self) -> int:
        return len(self._queue)

    def get_running_count(self) -> int:
        return sum(1 for t in self._tasks.values() if t.status == TaskStatus.RUNNING)

    def get_stats(self) -> QueueStats:
        tasks = list(self._tasks.values())
        total = len(tasks)

        completed = [t for t in tasks if t.status == TaskStatus.COMPLETED]
        avg_exec = 0.0
        if completed and self._completed_count > 0:
            avg_exec = self._total_execution_time_ms / self._completed_count

        avg_wait = 0.0
        if self._completed_count > 0:
            avg_wait = self._total_wait_time_ms / self._completed_count

        return QueueStats(
            total_tasks=total,
            pending_tasks=sum(1 for t in tasks if t.status in (TaskStatus.PENDING, TaskStatus.QUEUED)),
            running_tasks=sum(1 for t in tasks if t.status == TaskStatus.RUNNING),
            completed_tasks=self._completed_count,
            failed_tasks=self._failed_count,
            cancelled_tasks=self._cancelled_count,
            average_wait_time_ms=avg_wait,
            average_execution_time_ms=avg_exec,
        )

    async def wait_for_task(self, task_id: str, timeout: float | None = None) -> TaskInfo | None:
        start = datetime.now()

        while True:
            task_info = self._tasks.get(task_id)
            if not task_info:
                return None

            if task_info.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.TIMEOUT):
                return task_info

            if timeout:
                elapsed = (datetime.now() - start).total_seconds()
                if elapsed > timeout:
                    return None

            await asyncio.sleep(0.1)

    async def prioritize_task(self, task_id: str, new_priority: TaskPriority) -> bool:
        async with self._lock:
            for i, task in enumerate(self._queue):
                if task.task_id == task_id:
                    self._queue[i] = PrioritizedTask(
                        priority=new_priority.value,
                        sequence=task.sequence,
                        task_id=task.task_id,
                        action=task.action,
                        params=task.params,
                        created_at=task.created_at,
                        metadata=task.metadata,
                        retry_count=task.retry_count,
                        max_retries=task.max_retries,
                        timeout_seconds=task.timeout_seconds,
                    )
                    heapq.heapify(self._queue)

                    task_info = self._tasks.get(task_id)
                    if task_info:
                        task_info.priority = new_priority.value

                    return True
        return False
