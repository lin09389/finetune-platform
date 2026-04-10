"""
操作进度反馈模块
使用 Server-Sent Events (SSE) 实现实时进度推送
"""
import asyncio
import json
import logging
import threading
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ProgressStatus(str, Enum):
    """进度状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ProgressInfo:
    """进度信息"""
    task_id: str
    action: str
    status: ProgressStatus = ProgressStatus.PENDING
    progress: float = 0.0
    message: str = ""
    current_step: int = 0
    total_steps: int = 0
    start_time: datetime | None = None
    end_time: datetime | None = None
    error: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        if self.start_time is None:
            return 0.0
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds() * 1000

    @property
    def eta_seconds(self) -> float | None:
        if self.progress <= 0 or self.start_time is None:
            return None

        elapsed = (datetime.now() - self.start_time).total_seconds()
        remaining_progress = 100 - self.progress
        eta = (elapsed / self.progress) * remaining_progress
        return eta

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "action": self.action,
            "status": self.status.value,
            "progress": round(self.progress, 2),
            "message": self.message,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "duration_ms": round(self.duration_ms, 2),
            "eta_seconds": round(self.eta_seconds, 2) if self.eta_seconds else None,
            "error": self.error,
            "data": self.data,
            "timestamp": datetime.now().isoformat(),
        }

    def to_sse(self) -> str:
        """转换为 SSE 格式"""
        data = json.dumps(self.to_dict(), ensure_ascii=False)
        return f"data: {data}\n\n"


class ProgressTracker:
    """
    进度追踪器

    追踪操作进度并支持 SSE 推送
    """

    def __init__(self):
        self._progress: dict[str, ProgressInfo] = {}
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._lock = threading.RLock()
        self._cancel_flags: dict[str, bool] = {}

    def create_task(self, task_id: str, action: str, total_steps: int = 0) -> ProgressInfo:
        """创建进度任务"""
        with self._lock:
            info = ProgressInfo(
                task_id=task_id,
                action=action,
                total_steps=total_steps,
                status=ProgressStatus.PENDING,
            )
            self._progress[task_id] = info
            self._cancel_flags[task_id] = False
            logger.info(f"创建进度任务: {task_id} - {action}")
            return info

    def start_task(self, task_id: str, message: str = "开始执行") -> bool:
        """开始任务"""
        with self._lock:
            if task_id not in self._progress:
                return False

            info = self._progress[task_id]
            info.status = ProgressStatus.RUNNING
            info.message = message
            info.start_time = datetime.now()

            self._notify_subscribers(task_id, info)
            return True

    def update_progress(
        self,
        task_id: str,
        progress: float = None,
        current_step: int = None,
        message: str = None,
        data: dict[str, Any] = None,
    ) -> bool:
        """更新进度"""
        with self._lock:
            if task_id not in self._progress:
                return False

            info = self._progress[task_id]

            if progress is not None:
                info.progress = min(100, max(0, progress))
            if current_step is not None:
                info.current_step = current_step
                if info.total_steps > 0:
                    info.progress = (current_step / info.total_steps) * 100
            if message is not None:
                info.message = message
            if data is not None:
                info.data.update(data)

            self._notify_subscribers(task_id, info)
            return True

    def complete_task(self, task_id: str, message: str = "完成", data: dict[str, Any] = None) -> bool:
        """完成任务"""
        with self._lock:
            if task_id not in self._progress:
                return False

            info = self._progress[task_id]
            info.status = ProgressStatus.COMPLETED
            info.progress = 100
            info.message = message
            info.end_time = datetime.now()
            if data:
                info.data.update(data)

            self._notify_subscribers(task_id, info)
            logger.info(f"任务完成: {task_id} - 耗时 {info.duration_ms:.0f}ms")
            return True

    def fail_task(self, task_id: str, error: str, message: str = "失败") -> bool:
        """任务失败"""
        with self._lock:
            if task_id not in self._progress:
                return False

            info = self._progress[task_id]
            info.status = ProgressStatus.FAILED
            info.message = message
            info.error = error
            info.end_time = datetime.now()

            self._notify_subscribers(task_id, info)
            logger.error(f"任务失败: {task_id} - {error}")
            return True

    def cancel_task(self, task_id: str, message: str = "已取消") -> bool:
        """取消任务"""
        with self._lock:
            if task_id not in self._progress:
                return False

            self._cancel_flags[task_id] = True

            info = self._progress[task_id]
            info.status = ProgressStatus.CANCELLED
            info.message = message
            info.end_time = datetime.now()

            self._notify_subscribers(task_id, info)
            logger.info(f"任务取消: {task_id}")
            return True

    def is_cancelled(self, task_id: str) -> bool:
        """检查任务是否被取消"""
        return self._cancel_flags.get(task_id, False)

    def get_progress(self, task_id: str) -> ProgressInfo | None:
        """获取进度"""
        return self._progress.get(task_id)

    def get_all_progress(self) -> dict[str, ProgressInfo]:
        """获取所有进度"""
        with self._lock:
            return dict(self._progress)

    def subscribe(self, task_id: str) -> asyncio.Queue:
        """订阅进度更新"""
        queue = asyncio.Queue()

        with self._lock:
            if task_id not in self._subscribers:
                self._subscribers[task_id] = []
            self._subscribers[task_id].append(queue)

            if task_id in self._progress:
                info = self._progress[task_id]
                try:
                    loop = asyncio.get_event_loop()
                    loop.call_soon_threadsafe(queue.put_nowait, info)
                except RuntimeError:
                    pass

        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue):
        """取消订阅"""
        with self._lock:
            if task_id in self._subscribers:
                with suppress(ValueError):
                    self._subscribers[task_id].remove(queue)

    def _notify_subscribers(self, task_id: str, info: ProgressInfo):
        """通知订阅者"""
        if task_id not in self._subscribers:
            return

        dead_queues = []
        for queue in self._subscribers[task_id]:
            try:
                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(queue.put_nowait, info)
            except Exception:
                dead_queues.append(queue)

        for queue in dead_queues:
            with suppress(ValueError):
                self._subscribers[task_id].remove(queue)

    def cleanup_completed(self, max_age_seconds: int = 3600):
        """清理已完成的任务"""
        now = datetime.now()
        to_remove = []

        with self._lock:
            for task_id, info in self._progress.items():
                if (
                    info.status in (ProgressStatus.COMPLETED, ProgressStatus.FAILED, ProgressStatus.CANCELLED)
                    and info.end_time
                    and (now - info.end_time).total_seconds() > max_age_seconds
                ):
                    to_remove.append(task_id)

            for task_id in to_remove:
                del self._progress[task_id]
                self._cancel_flags.pop(task_id, None)
                self._subscribers.pop(task_id, None)

        if to_remove:
            logger.info(f"清理了 {len(to_remove)} 个已完成的进度任务")


_progress_tracker: ProgressTracker | None = None


def get_progress_tracker() -> ProgressTracker:
    """获取进度追踪器单例"""
    global _progress_tracker
    if _progress_tracker is None:
        _progress_tracker = ProgressTracker()
    return _progress_tracker


class ProgressContext:
    """
    进度上下文管理器

    用于自动管理进度
    """

    def __init__(self, task_id: str, action: str, total_steps: int = 0):
        self.task_id = task_id
        self.action = action
        self.total_steps = total_steps
        self.tracker = get_progress_tracker()

    def __enter__(self):
        self.tracker.create_task(self.task_id, self.action, self.total_steps)
        self.tracker.start_task(self.task_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.tracker.fail_task(self.task_id, str(exc_val))
        else:
            self.tracker.complete_task(self.task_id)
        return False

    def update(self, progress: float = None, message: str = None, **kwargs):
        """更新进度"""
        self.tracker.update_progress(self.task_id, progress=progress, message=message, **kwargs)

    def step(self, message: str = None):
        """前进一步"""
        info = self.tracker.get_progress(self.task_id)
        if info:
            self.tracker.update_progress(
                self.task_id,
                current_step=info.current_step + 1,
                message=message
            )

    def check_cancelled(self) -> bool:
        """检查是否被取消"""
        return self.tracker.is_cancelled(self.task_id)
