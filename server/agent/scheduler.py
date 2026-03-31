"""
定时任务调度器 - 支持 Cron 表达式的任务调度
"""
import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from croniter import croniter

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    RUNNING = "running"
    PAUSED = "paused"


class TaskType(str, Enum):
    AGENT_ACTION = "agent_action"
    CHAIN = "chain"
    SCRIPT = "script"
    REMINDER = "reminder"


@dataclass
class ScheduledTask:
    id: str
    name: str
    description: str
    task_type: str
    task_data: dict[str, Any]
    cron_expression: str
    timezone: str = "Asia/Shanghai"
    enabled: bool = True
    last_run: str | None = None
    next_run: str | None = None
    run_count: int = 0
    max_runs: int | None = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = TaskStatus.ENABLED.value
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScheduledTask":
        return cls(**data)

    def calculate_next_run(self) -> datetime | None:
        if not self.enabled:
            return None

        try:
            cron = croniter(self.cron_expression, datetime.now())
            return cron.get_next(datetime)
        except Exception as e:
            logger.error(f"解析 Cron 表达式失败: {e}")
            return None


class TaskScheduler:
    TASKS_FILE = "data/scheduled_tasks.json"

    def __init__(
        self,
        executor_factory: Callable | None = None,
        chain_executor_factory: Callable | None = None,
    ):
        self.executor_factory = executor_factory
        self.chain_executor_factory = chain_executor_factory
        self.tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._callbacks: dict[str, list[Callable]] = {}
        self._tasks_file = Path(self.TASKS_FILE)
        self._load_tasks()

    def _load_tasks(self):
        if self._tasks_file.exists():
            try:
                with open(self._tasks_file, encoding="utf-8") as f:
                    data = json.load(f)
                    for task_id, task_data in data.items():
                        self.tasks[task_id] = ScheduledTask.from_dict(task_data)
                logger.info(f"加载了 {len(self.tasks)} 个定时任务")
            except Exception as e:
                logger.warning(f"加载定时任务失败: {e}")

    def _save_tasks(self):
        try:
            self._tasks_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._tasks_file, "w", encoding="utf-8") as f:
                json.dump(
                    {k: v.to_dict() for k, v in self.tasks.items()},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            logger.error(f"保存定时任务失败: {e}")

    def add_task(
        self,
        name: str,
        task_type: str,
        task_data: dict[str, Any],
        cron_expression: str,
        description: str = "",
        timezone: str = "Asia/Shanghai",
        enabled: bool = True,
        max_runs: int | None = None,
    ) -> ScheduledTask:
        task_id = f"task_{uuid.uuid4().hex[:8]}"

        task = ScheduledTask(
            id=task_id,
            name=name,
            description=description,
            task_type=task_type,
            task_data=task_data,
            cron_expression=cron_expression,
            timezone=timezone,
            enabled=enabled,
            max_runs=max_runs,
        )

        task.next_run = task.calculate_next_run()
        if task.next_run:
            task.next_run = task.next_run.isoformat()

        self.tasks[task_id] = task
        self._save_tasks()

        logger.info(f"添加定时任务: {name} ({task_id}), Cron: {cron_expression}")
        return task

    def update_task(
        self,
        task_id: str,
        **kwargs,
    ) -> ScheduledTask | None:
        task = self.tasks.get(task_id)
        if not task:
            return None

        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)

        task.updated_at = datetime.now().isoformat()
        task.next_run = task.calculate_next_run()
        if task.next_run:
            task.next_run = task.next_run.isoformat()

        self._save_tasks()
        logger.info(f"更新定时任务: {task_id}")
        return task

    def remove_task(self, task_id: str) -> bool:
        if task_id in self.tasks:
            del self.tasks[task_id]
            self._save_tasks()
            logger.info(f"移除定时任务: {task_id}")
            return True
        return False

    def get_task(self, task_id: str) -> ScheduledTask | None:
        return self.tasks.get(task_id)

    def get_all_tasks(self) -> list[ScheduledTask]:
        return list(self.tasks.values())

    def enable_task(self, task_id: str) -> bool:
        return self.update_task(task_id, enabled=True, status=TaskStatus.ENABLED.value) is not None

    def disable_task(self, task_id: str) -> bool:
        return self.update_task(task_id, enabled=False, status=TaskStatus.DISABLED.value) is not None

    async def run_task(self, task_id: str) -> dict[str, Any]:
        task = self.tasks.get(task_id)
        if not task:
            return {"success": False, "error": "任务不存在"}

        task.status = TaskStatus.RUNNING.value
        task.last_run = datetime.now().isoformat()
        self._save_tasks()

        result = {"success": False, "error": "未知错误"}

        try:
            if task.task_type == TaskType.AGENT_ACTION.value:
                if self.executor_factory:
                    executor = self.executor_factory()
                    from .config import ActionType
                    action = ActionType(task.task_data.get("action"))
                    params = task.task_data.get("params", {})
                    exec_result = await executor.execute(action, params)
                    result = {
                        "success": exec_result.success,
                        "message": exec_result.message,
                        "error": exec_result.error,
                    }

            elif task.task_type == TaskType.CHAIN.value:
                if self.chain_executor_factory:
                    chain_executor = self.chain_executor_factory()
                    chain_id = task.task_data.get("chain_id")
                    chain = chain_executor.get_chain(chain_id)
                    if chain:
                        chain_result = await chain_executor.execute(chain)
                        result = {"success": True, "result": chain_result}
                    else:
                        result = {"success": False, "error": "操作链不存在"}

            elif task.task_type == TaskType.REMINDER.value:
                message = task.task_data.get("message", "提醒")
                result = {"success": True, "message": message}
                logger.info(f"提醒: {message}")

            else:
                result = {"success": False, "error": f"不支持的任务类型: {task.task_type}"}

            task.run_count += 1
            task.error = None

        except Exception as e:
            task.error = str(e)
            result = {"success": False, "error": str(e)}
            logger.error(f"执行定时任务失败: {task_id}, 错误: {e}")

        finally:
            task.status = TaskStatus.ENABLED.value if task.enabled else TaskStatus.DISABLED.value
            task.next_run = task.calculate_next_run()
            if task.next_run:
                task.next_run = task.next_run.isoformat()
            self._save_tasks()

        if task.max_runs and task.run_count >= task.max_runs:
            task.enabled = False
            task.status = TaskStatus.DISABLED.value
            self._save_tasks()
            logger.info(f"任务 {task_id} 已达到最大运行次数，已禁用")

        return result

    async def start(self):
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._schedule_loop())
        logger.info("定时任务调度器已启动")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("定时任务调度器已停止")

    async def _schedule_loop(self):
        while self._running:
            try:
                now = datetime.now()

                for task_id, task in list(self.tasks.items()):
                    if not task.enabled:
                        continue

                    if task.next_run:
                        try:
                            next_run = datetime.fromisoformat(task.next_run)
                            if now >= next_run:
                                logger.info(f"执行定时任务: {task.name} ({task_id})")
                                asyncio.create_task(self.run_task(task_id))
                        except Exception as e:
                            logger.warning(f"解析下次运行时间失败: {e}")

                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"调度循环错误: {e}")
                await asyncio.sleep(60)


_scheduler: TaskScheduler | None = None


def get_scheduler() -> TaskScheduler:
    global _scheduler
    if _scheduler is None:
        from .chain import get_chain_executor
        from .executor import get_executor

        _scheduler = TaskScheduler(
            executor_factory=get_executor,
            chain_executor_factory=get_chain_executor,
        )
    return _scheduler
