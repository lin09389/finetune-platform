"""
训练状态管理模块 - 线程安全版本（重构版）
修复内容:
- P0-1: 移除未使用的 asyncio.Lock，统一使用 threading.Lock
- P1-1: 修复历史记录竞态条件，使用原子写入
- P1-6: 修复内存泄漏，定期清理已完成任务引用
- PERF: TrainingProgress 从 Pydantic BaseModel 改为 dataclass，避免高频 model_copy 开销
"""
import gc
import json
import os
import tempfile
import threading
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, field, fields
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from pydantic import BaseModel, ConfigDict

from core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TrainingProgress:
    """训练进度 - 使用 dataclass 替代 Pydantic BaseModel 以减少高频拷贝开销"""
    epoch: int = 0
    step: int = 0
    total_steps: int = 0
    loss: float = 0.0
    lr: float = 0.0
    vram_used: float = 0.0
    elapsed_time: float = 0.0
    eta: float = 0.0
    status: str = "idle"
    message: str = ""
    grad_norm: float | None = None
    speed: float = 0.0
    samples_per_sec: float = 0.0
    current_phase: str = ""
    phase_durations: dict[str, float] = field(default_factory=dict)
    retry_count: int = 0
    queue_position: int = 0
    estimated_wait_seconds: float = 0.0

    def copy(self) -> "TrainingProgress":
        """浅拷贝，避免 dataclass 字典构造开销"""
        return TrainingProgress(**{f.name: getattr(self, f.name) for f in fields(self)})

    def model_dump(self) -> dict[str, Any]:
        """兼容 Pydantic 接口的序列化方法"""
        return {f.name: getattr(self, f.name) for f in fields(self)}


class AwaitableBool:
    def __init__(self, value: bool):
        self.value = value

    def __bool__(self):
        return self.value

    def __eq__(self, other):
        return self.value == other

    def __await__(self):
        async def _return_value():
            return self.value
        return _return_value().__await__()


class TrainingRecord(BaseModel):
    """训练记录"""
    model_config = ConfigDict(protected_namespaces=())

    id: str
    model_name: str
    dataset_name: str
    base_model_id: str | None = None
    dataset_id: str | None = None
    task_goal: str | None = None
    method: str
    status: str
    start_time: str
    end_time: str | None = None
    config: dict
    output_path: str
    adapter_path: str | None = None
    checkpoint_path: str | None = None
    final_loss: float | None = None
    final_lr: float | None = None
    elapsed_time: float | None = None
    total_steps: int | None = None


class StateUpdate:
    """状态更新请求"""
    def __init__(self, update_type: str, **kwargs):
        self.update_type = update_type
        self.data = kwargs


class TrainingState:
    """
    训练状态管理器 - 线程安全版本（重构版）
    修复:
    - P0-1: 移除 asyncio.Lock，统一使用 threading.Lock
    - P1-1: 历史记录原子写入
    - P1-6: 定期清理已完成任务
    使用队列 + 后台工作线程处理状态更新，消除 asyncio.new_event_loop() 开销
    """

    MAX_HISTORY_SIZE = 100
    TASK_CLEANUP_INTERVAL = 60
    MAX_COMPLETED_TASKS = 10

    def __init__(self, history_file: Path):
        self._lock = threading.Lock()
        self._is_training: bool = False
        self._stop_requested: bool = False
        self._current_record: TrainingRecord | None = None
        self._progress: TrainingProgress = TrainingProgress()
        self._training_tasks: dict[str, threading.Thread] = {}
        self._completed_tasks: dict[str, float] = {}
        self._history_file = history_file
        self._history_cache: list[TrainingRecord] | None = None
        self._history_dirty = False

        self._update_queue: Queue = Queue()
        self._worker_thread: threading.Thread | None = None
        self._worker_running = False

        self._history_file.parent.mkdir(parents=True, exist_ok=True)

        self._start_worker()

        self._last_cleanup_time = datetime.now().timestamp()

    def _start_worker(self):
        """启动后台工作线程"""
        self._worker_running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        logger.debug("TrainingState worker started")

    def _worker_loop(self):
        """后台工作线程主循环"""
        while self._worker_running:
            try:
                update: StateUpdate = self._update_queue.get(timeout=1.0)
                self._process_update(update)
            except Empty:
                self._periodic_cleanup()
                continue
            except Exception as e:
                logger.error(f"处理状态更新失败：{e}")

    def _periodic_cleanup(self):
        """P1-6: 定期清理已完成任务引用"""
        now = datetime.now().timestamp()
        if now - self._last_cleanup_time < self.TASK_CLEANUP_INTERVAL:
            return

        with self._lock:
            self._last_cleanup_time = now

            for task_id, completed_time in list(self._completed_tasks.items()):
                if now - completed_time > 300:
                    self._completed_tasks.pop(task_id, None)
                    if task_id in self._training_tasks:
                        del self._training_tasks[task_id]

            if len(self._completed_tasks) > self.MAX_COMPLETED_TASKS:
                oldest = sorted(self._completed_tasks.items(), key=lambda x: x[1])
                for task_id, _ in oldest[:-self.MAX_COMPLETED_TASKS]:
                    self._completed_tasks.pop(task_id, None)
                    if task_id in self._training_tasks:
                        del self._training_tasks[task_id]

            if len(self._training_tasks) > 20:
                active_tasks = {
                    k: v for k, v in self._training_tasks.items()
                    if v.is_alive()
                }
                self._training_tasks = active_tasks

    def _process_update(self, update: StateUpdate):
        """处理状态更新"""
        try:
            if update.update_type == 'progress':
                with self._lock:
                    for key, value in update.data.items():
                        if hasattr(self._progress, key):
                            setattr(self._progress, key, value)
            elif update.update_type == 'history_add':
                self._add_to_history_internal(update.data.get('record'))
        except Exception as e:
            logger.error(f"应用状态更新失败：{e}")

    def queue_progress_update(self, **kwargs):
        """队列式进度更新 - 线程安全"""
        try:
            self._update_queue.put(StateUpdate('progress', **kwargs))
        except Exception as e:
            logger.error(f"队列进度更新失败：{e}")

    def queue_training_state(self, value: bool):
        """训练状态更新（直接写入，已有锁保护）"""
        with self._lock:
            self._is_training = value
            if not value:
                self._stop_requested = False

    def queue_record_update(self, record: TrainingRecord | None):
        """记录更新（直接写入，已有锁保护）"""
        with self._lock:
            self._current_record = record

    def queue_history_add(self, record: TrainingRecord):
        """队列式添加历史记录"""
        try:
            self._update_queue.put(StateUpdate('history_add', record=record))
        except Exception as e:
            logger.error(f"队列历史记录添加失败：{e}")

    def stop_worker(self):
        """停止后台工作线程"""
        self._worker_running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=2.0)
            logger.debug("TrainingState worker stopped")

    def is_training(self) -> bool:
        """检查是否正在训练"""
        with self._lock:
            return self._is_training

    def set_training(self, value: bool):
        """设置训练状态"""
        self.queue_training_state(value)

    def request_stop(self):
        """请求停止当前训练任务。"""
        with self._lock:
            if self._is_training:
                self._stop_requested = True

    def clear_stop_request(self):
        """清除停止请求标记。"""
        with self._lock:
            self._stop_requested = False

    def should_stop(self) -> bool:
        """是否收到停止请求。"""
        with self._lock:
            return self._stop_requested

    def get_current_record(self) -> TrainingRecord | None:
        """获取当前训练记录"""
        with self._lock:
            return self._current_record.model_copy() if self._current_record else None

    def set_current_record(self, record: TrainingRecord | None):
        """设置当前训练记录"""
        self.queue_record_update(record)

    def get_progress(self) -> TrainingProgress:
        """获取训练进度"""
        with self._lock:
            return self._progress.copy()

    def update_progress(self, **kwargs):
        """更新训练进度"""
        self.queue_progress_update(**kwargs)

    def register_training_task(self, task_id: str, thread: threading.Thread):
        """注册训练任务"""
        with self._lock:
            self._training_tasks[task_id] = thread

    def unregister_training_task(self, task_id: str):
        """注销训练任务"""
        with self._lock:
            self._training_tasks.pop(task_id, None)
            self._completed_tasks[task_id] = datetime.now().timestamp()

    def get_active_tasks(self) -> dict[str, threading.Thread]:
        """获取所有活跃任务"""
        with self._lock:
            return {k: v for k, v in self._training_tasks.items() if v.is_alive()}

    def _load_history_internal(self) -> list[TrainingRecord]:
        """内部加载历史记录（带缓存）"""
        if self._history_cache is not None and not self._history_dirty:
            return self._history_cache

        if not self._history_file.exists():
            self._history_cache = []
            return self._history_cache

        try:
            with open(self._history_file, encoding="utf-8") as f:
                data = json.load(f)
                self._history_cache = [TrainingRecord(**r) for r in data]
                self._history_dirty = False
                return self._history_cache
        except Exception as e:
            logger.error(f"加载历史记录失败：{e}")
            self._history_cache = []
            return self._history_cache

    def _save_history_internal(self, records: list[TrainingRecord]):
        """P1-1: 原子写入历史记录"""
        try:
            self._history_file.parent.mkdir(parents=True, exist_ok=True)

            fd, temp_path = tempfile.mkstemp(
                suffix='.json',
                prefix='history_',
                dir=str(self._history_file.parent)
            )

            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(
                        [r.model_dump() for r in records],
                        f,
                        ensure_ascii=False,
                        indent=2
                    )

                if self._history_file.exists():
                    backup_path = self._history_file.with_suffix('.json.bak')
                    with suppress(Exception):
                        os.replace(str(self._history_file), str(backup_path))

                os.replace(temp_path, str(self._history_file))

                self._history_cache = records
                self._history_dirty = False

            except Exception as e:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise e

        except Exception as e:
            logger.error(f"保存历史记录失败：{e}")

    def _add_to_history_internal(self, record: TrainingRecord):
        """内部添加记录到历史 - 带文件锁"""
        with self._lock:
            records = self._load_history_internal()

            existing_idx = None
            for i, r in enumerate(records):
                if r.id == record.id:
                    existing_idx = i
                    break

            if existing_idx is not None:
                records[existing_idx] = record
            else:
                records.append(record)

            if len(records) > self.MAX_HISTORY_SIZE:
                records = records[-self.MAX_HISTORY_SIZE:]

            self._save_history_internal(records)

    def add_to_history_sync(self, record: TrainingRecord):
        """同步添加记录到历史（用于后台线程）"""
        self._add_to_history_internal(record)

    def load_history(self) -> list[TrainingRecord]:
        """加载历史记录"""
        return self._load_history_internal()

    def save_history(self, records: list[TrainingRecord]):
        """保存历史记录"""
        self._save_history_internal(records)

    def add_to_history(self, record: TrainingRecord):
        """添加记录到历史"""
        self.queue_history_add(record)

    def get_history(self) -> list[TrainingRecord]:
        """获取历史记录"""
        return self._load_history_internal()

    def get_status(self) -> dict[str, Any]:
        """获取完整状态"""
        with self._lock:
            active_count = sum(1 for t in self._training_tasks.values() if t.is_alive())
            return {
                "is_training": self._is_training,
                "record": self._current_record.model_dump() if self._current_record else None,
                "progress": self._progress.model_dump(),
                "active_tasks": active_count,
                "total_tasks_registered": len(self._training_tasks),
                "completed_tasks_cached": len(self._completed_tasks)
            }

    def cleanup(self):
        """清理资源"""
        self.stop_worker()

        with self._lock:
            self._training_tasks.clear()
            self._completed_tasks.clear()
            self._stop_requested = False
            self._history_cache = None

        gc.collect()
        logger.info("TrainingState 资源已清理")


_training_state: TrainingState | None = None
_state_lock = threading.Lock()


def create_training_state(outputs_dir: Path) -> TrainingState:
    """创建训练状态实例"""
    history_file = outputs_dir / "training_history.json"
    return TrainingState(history_file)


def get_training_state(outputs_dir: Path = None) -> TrainingState:
    """获取训练状态实例"""
    global _training_state

    with _state_lock:
        if _training_state is None:
            if outputs_dir is None:
                outputs_dir = Path(__file__).parent.parent.parent / "outputs"
            _training_state = create_training_state(outputs_dir)
        return _training_state


def reset_training_state():
    """重置训练状态（用于测试）"""
    global _training_state

    with _state_lock:
        if _training_state:
            _training_state.cleanup()
            _training_state = None
