"""
训练任务队列管理模块（重构版�?
修复内容�?- P0-2: 完善任务取消功能，支持取消队列中的任�?- P1-3: 状态文件原子写入，防止损坏

支持�?- 任务排队
- 并发控制
- 优先级调�?- 任务取消
"""
import threading
from queue import PriorityQueue, Empty
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Callable, Set
from datetime import datetime
from enum import Enum
import logging
from pathlib import Path
import json
import tempfile
import os

from core.logging import get_logger
from core.training_state import TrainingRecord

logger = get_logger(__name__)


class TaskStatus(Enum):
    """任务状�?""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """任务优先�?""
    LOW = 3
    NORMAL = 2
    HIGH = 1
    URGENT = 0


@dataclass(order=True)
class TrainingTask:
    """训练任务"""
    priority: int
    created_at: float = field(compare=False)
    task_id: str = field(compare=False)
    config: Any = field(compare=False)
    callback: Optional[Callable] = field(compare=False, default=None)
    status: TaskStatus = field(compare=False, default=TaskStatus.PENDING)
    error: Optional[str] = field(compare=False, default=None)
    started_at: Optional[datetime] = field(compare=False, default=None)
    completed_at: Optional[datetime] = field(compare=False, default=None)

    def to_dict(self) -> Dict:
        """转换为字�?""
        return {
            "task_id": self.task_id,
            "priority": self.priority,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


class TrainingQueue:
    """
    训练任务队列管理器（重构版）

    修复�?    - P0-2: 完善任务取消功能
    - P1-3: 状态文件原子写�?
    特性：
    - 优先级队�?    - 并发控制
    - 自动重试
    - 任务取消
    """

    MAX_HISTORY_SIZE = 100

    def __init__(
        self,
        max_concurrent: int = 1,
        max_queue_size: int = 10,
        state_file: Optional[Path] = None
    ):
        self.max_concurrent = max_concurrent
        self.max_queue_size = max_queue_size
        self.state_file = state_file or Path(__file__).parent.parent / "outputs" / "queue_state.json"

        self._queue: PriorityQueue = PriorityQueue(maxsize=max_queue_size)

        self._running_tasks: Dict[str, TrainingTask] = {}
        self._running_threads: Dict[str, threading.Thread] = {}

        self._history: Dict[str, TrainingTask] = {}

        self._lock = threading.Lock()
        self._history_lock = threading.Lock()

        self._worker_running = False
        self._worker_thread: Optional[threading.Thread] = None

        self._semaphore = threading.Semaphore(max_concurrent)

        self._all_tasks: Dict[str, TrainingTask] = {}
        self._cancelled_tasks: Set[str] = set()

        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        self._load_state()

        logger.info(f"TrainingQueue 初始化完成：max_concurrent={max_concurrent}, max_queue_size={max_queue_size}")

    def start(self):
        """启动队列工作线程"""
        if self._worker_running:
            logger.warning("队列工作线程已在运行")
            return

        self._worker_running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        logger.info("队列工作线程已启�?)

    def stop(self):
        """停止队列工作线程"""
        self._worker_running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)
        logger.info("队列工作线程已停�?)

    def _worker_loop(self):
        """工作线程主循�?""
        while self._worker_running:
            try:
                task: TrainingTask = self._queue.get(timeout=1.0)

                if task.task_id in self._cancelled_tasks:
                    logger.debug(f"任务 {task.task_id} 已取消，跳过执行")
                    with self._lock:
                        self._cancelled_tasks.discard(task.task_id)
                        self._all_tasks.pop(task.task_id, None)
                    task.status = TaskStatus.CANCELLED
                    self._add_to_history(task)
                    continue

                if self._semaphore.acquire(timeout=0.5):
                    self._execute_task(task)

            except Empty:
                continue
            except Exception as e:
                logger.error(f"队列工作线程错误：{e}")

    def _execute_task(self, task: TrainingTask):
        """执行任务"""
        try:
            logger.info(f"开始执行任务：{task.task_id} (优先级：{task.priority})")

            with self._lock:
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now()
                self._running_tasks[task.task_id] = task

            if task.callback:
                task.callback()

            with self._lock:
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now()
                self._running_tasks.pop(task.task_id, None)
                self._running_threads.pop(task.task_id, None)
                self._all_tasks.pop(task.task_id, None)
                self._add_to_history(task)

            logger.info(f"任务完成：{task.task_id}")

        except Exception as e:
            logger.error(f"任务失败：{task.task_id}, 错误：{e}")
            with self._lock:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.completed_at = datetime.now()
                self._running_tasks.pop(task.task_id, None)
                self._running_threads.pop(task.task_id, None)
                self._all_tasks.pop(task.task_id, None)
                self._add_to_history(task)

        finally:
            self._semaphore.release()

    def _add_to_history(self, task: TrainingTask):
        """添加到历�?""
        with self._history_lock:
            self._history[task.task_id] = task

            if len(self._history) > self.MAX_HISTORY_SIZE:
                oldest_id = min(self._history.keys(), key=lambda k: self._history[k].created_at)
                self._history.pop(oldest_id)

            self._save_state()

    def _save_state(self):
        """P1-3: 原子写入状态到文件"""
        try:
            state = {
                "history": {
                    task_id: task.to_dict()
                    for task_id, task in self._history.items()
                },
                "running": {
                    task_id: task.to_dict()
                    for task_id, task in self._running_tasks.items()
                }
            }

            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            fd, temp_path = tempfile.mkstemp(
                suffix='.json',
                prefix='queue_state_',
                dir=str(self.state_file.parent)
            )

            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(state, f, indent=2, ensure_ascii=False)

                if self.state_file.exists():
                    backup_path = self.state_file.with_suffix('.json.bak')
                    try:
                        os.replace(str(self.state_file), str(backup_path))
                    except Exception:
                        pass

                os.replace(temp_path, str(self.state_file))

            except Exception as e:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise e

        except Exception as e:
            logger.error(f"保存队列状态失败：{e}")

    def _load_state(self):
        """从文件加载状�?""
        if not self.state_file.exists():
            backup_path = self.state_file.with_suffix('.json.bak')
            if backup_path.exists():
                try:
                    os.replace(str(backup_path), str(self.state_file))
                    logger.info("从备份文件恢复队列状�?)
                except Exception:
                    return
            else:
                return

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                state = json.load(f)

            for task_id, data in state.get("history", {}).items():
                task = TrainingTask(
                    priority=data["priority"],
                    created_at=data["created_at"],
                    task_id=task_id,
                    config=None,
                    status=TaskStatus(data["status"]),
                )
                if data.get("started_at"):
                    task.started_at = datetime.fromisoformat(data["started_at"])
                if data.get("completed_at"):
                    task.completed_at = datetime.fromisoformat(data["completed_at"])
                if data.get("error"):
                    task.error = data["error"]
                self._history[task_id] = task

            logger.info(f"从文件加载了 {len(self._history)} 个历史任�?)

        except Exception as e:
            logger.error(f"加载队列状态失败：{e}")

    def submit(
        self,
        task_id: str,
        config: Any,
        callback: Callable,
        priority: TaskPriority = TaskPriority.NORMAL
    ) -> bool:
        """
        提交任务到队�?
        Args:
            task_id: 任务 ID
            config: 任务配置
            callback: 任务回调函数
            priority: 优先�?
        Returns:
            是否提交成功
        """
        with self._lock:
            if self._queue.qsize() >= self.max_queue_size:
                logger.warning(f"队列已满，无法提交任�?{task_id}")
                return False

            task = TrainingTask(
                priority=priority.value,
                created_at=datetime.now().timestamp(),
                task_id=task_id,
                config=config,
                callback=callback,
                status=TaskStatus.QUEUED,
            )

            self._all_tasks[task_id] = task

            try:
                self._queue.put(task)
                logger.info(f"任务已提交：{task_id} (优先级：{priority.name})")
                return True
            except Exception as e:
                logger.error(f"提交任务失败：{e}")
                self._all_tasks.pop(task_id, None)
                return False

    def cancel(self, task_id: str) -> bool:
        """
        P0-2: 取消任务（支持队列中的任务）

        Args:
            task_id: 任务 ID

        Returns:
            是否取消成功
        """
        with self._lock:
            if task_id in self._running_tasks:
                task = self._running_tasks[task_id]
                task.status = TaskStatus.CANCELLED
                logger.info(f"运行中任务已标记取消：{task_id}")
                return True

            if task_id in self._all_tasks:
                self._cancelled_tasks.add(task_id)
                task = self._all_tasks[task_id]
                task.status = TaskStatus.CANCELLED
                logger.info(f"队列中任务已标记取消：{task_id}")
                return True

            logger.warning(f"无法取消任务 {task_id}：任务不存在")
            return False

    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状�?""
        with self._lock:
            return {
                "queue_size": self._queue.qsize(),
                "running_count": len(self._running_tasks),
                "history_count": len(self._history),
                "max_concurrent": self.max_concurrent,
                "max_queue_size": self.max_queue_size,
                "running_tasks": [
                    task.to_dict() for task in self._running_tasks.values()
                ],
                "cancelled_count": len(self._cancelled_tasks),
            }

    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """获取任务状�?""
        with self._lock:
            if task_id in self._running_tasks:
                return self._running_tasks[task_id].to_dict()

            if task_id in self._all_tasks:
                return self._all_tasks[task_id].to_dict()

        with self._history_lock:
            if task_id in self._history:
                return self._history[task_id].to_dict()

        return None

    def get_pending_tasks(self) -> List[Dict]:
        """获取所有待执行任务"""
        with self._lock:
            return [
                task.to_dict() for task in self._all_tasks.values()
                if task.status == TaskStatus.QUEUED
            ]

    def clear_cancelled_tasks(self) -> int:
        """清理已取消的任务记录"""
        with self._lock:
            count = len(self._cancelled_tasks)
            for task_id in self._cancelled_tasks:
                self._all_tasks.pop(task_id, None)
            self._cancelled_tasks.clear()
            return count


_training_queue: Optional[TrainingQueue] = None
_queue_lock = threading.Lock()


def get_training_queue(
    max_concurrent: int = 1,
    max_queue_size: int = 10,
    state_file: Optional[Path] = None
) -> TrainingQueue:
    """获取训练队列实例"""
    global _training_queue

    with _queue_lock:
        if _training_queue is None:
            _training_queue = TrainingQueue(
                max_concurrent=max_concurrent,
                max_queue_size=max_queue_size,
                state_file=state_file
            )
            _training_queue.start()

        return _training_queue


def shutdown_queue():
    """关闭队列"""
    global _training_queue

    with _queue_lock:
        if _training_queue:
            _training_queue.stop()
            _training_queue = None


def reset_training_queue():
    """重置训练队列（用于测试）"""
    global _training_queue

    with _queue_lock:
        if _training_queue:
            _training_queue.stop()
            _training_queue = None
