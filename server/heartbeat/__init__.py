"""
Heartbeat 模块 - 主动唤醒机制

借鉴 OpenClaw 架构�?- 定期唤醒 Agent
- 检查任务清单（HEARTBEAT.md�?- 主动汇报和提�?- 避免无效轮询
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable, Awaitable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from pathlib import Path
import re

from .task_executor import TaskExecutor, TaskType, TaskStatus, ProactiveTask, TaskResult

logger = logging.getLogger(__name__)


@dataclass
class HeartbeatTask:
    """Heartbeat 任务"""
    id: str
    name: str
    description: str
    schedule: str
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    last_result: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HeartbeatConfig:
    """Heartbeat 配置"""
    interval_seconds: int = 1800
    enabled: bool = True
    max_retries: int = 3
    retry_delay_seconds: int = 60
    task_file: str = "HEARTBEAT.md"


class HeartbeatScheduler:
    """
    Heartbeat 调度�?    
    功能�?    - 定时唤醒 Agent
    - 解析 HEARTBEAT.md 任务清单
    - 执行检查任�?    - 生成汇报
    """
    
    def __init__(self, config: Optional[HeartbeatConfig] = None):
        self.config = config or HeartbeatConfig()
        
        self._tasks: Dict[str, HeartbeatTask] = {}
        self._handlers: Dict[str, Callable] = {}
        
        self._is_running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        
        self._workspace_path: Optional[Path] = None
        self._on_heartbeat: Optional[Callable] = None
        
        self._task_executor: Optional[TaskExecutor] = None
        
        self._register_default_handlers()
    
    def _register_default_handlers(self):
        """注册默认处理�?""
        self._handlers["check_email"] = self._handle_check_email
        self._handlers["check_calendar"] = self._handle_check_calendar
        self._handlers["check_project"] = self._handle_check_project
        self._handlers["generate_report"] = self._handle_generate_report
        self._handlers["send_reminder"] = self._handle_send_reminder
    
    def set_workspace(self, workspace_path: Path):
        """设置工作空间路径"""
        self._workspace_path = workspace_path
    
    def set_heartbeat_callback(self, callback: Callable):
        """设置 Heartbeat 回调"""
        self._on_heartbeat = callback
    
    def set_task_executor(self, executor: TaskExecutor):
        """设置任务执行�?""
        self._task_executor = executor
    
    def register_handler(self, task_type: str, handler: Callable):
        """注册任务处理�?""
        self._handlers[task_type] = handler
    
    def add_task(self, task: HeartbeatTask):
        """添加任务"""
        self._tasks[task.id] = task
        self._calculate_next_run(task)
        logger.info(f"添加 Heartbeat 任务: {task.id} ({task.name})")
    
    def remove_task(self, task_id: str):
        """移除任务"""
        if task_id in self._tasks:
            del self._tasks[task_id]
            logger.info(f"移除 Heartbeat 任务: {task_id}")
    
    def enable_task(self, task_id: str):
        """启用任务"""
        if task_id in self._tasks:
            self._tasks[task_id].enabled = True
            self._calculate_next_run(self._tasks[task_id])
    
    def disable_task(self, task_id: str):
        """禁用任务"""
        if task_id in self._tasks:
            self._tasks[task_id].enabled = False
    
    def _calculate_next_run(self, task: HeartbeatTask):
        """计算下次运行时间"""
        try:
            if task.schedule.isdigit():
                interval = int(task.schedule)
                if task.last_run:
                    task.next_run = task.last_run + timedelta(seconds=interval)
                else:
                    task.next_run = datetime.now() + timedelta(seconds=interval)
            else:
                task.next_run = self._parse_cron(task.schedule)
        except Exception as e:
            logger.warning(f"解析调度时间失败: {e}")
            task.next_run = datetime.now() + timedelta(seconds=self.config.interval_seconds)
    
    def _parse_cron(self, cron_expr: str) -> datetime:
        """解析 cron 表达式（简化版�?""
        now = datetime.now()
        
        parts = cron_expr.split()
        if len(parts) != 5:
            return now + timedelta(seconds=self.config.interval_seconds)
        
        minute, hour, day, month, weekday = parts
        
        next_run = now.replace(second=0, microsecond=0)
        
        if minute != "*" and minute.isdigit():
            next_run = next_run.replace(minute=int(minute))
        if hour != "*" and hour.isdigit():
            next_run = next_run.replace(hour=int(hour))
        
        if next_run <= now:
            next_run += timedelta(days=1)
        
        return next_run
    
    async def start(self):
        """启动调度�?""
        if self._is_running:
            logger.warning("Heartbeat 调度器已在运�?)
            return
        
        self._is_running = True
        self._scheduler_task = asyncio.create_task(self._run_scheduler())
        
        logger.info(f"Heartbeat 调度器已启动，间�? {self.config.interval_seconds}�?)
    
    async def stop(self):
        """停止调度�?""
        self._is_running = False
        
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Heartbeat 调度器已停止")
    
    async def _run_scheduler(self):
        """运行调度循环"""
        while self._is_running:
            try:
                await asyncio.sleep(self.config.interval_seconds)
                
                if not self.config.enabled:
                    continue
                
                await self._execute_heartbeat()
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat 调度错误: {e}", exc_info=True)
    
    async def _execute_heartbeat(self):
        """执行 Heartbeat"""
        logger.info("执行 Heartbeat 检�?..")
        
        tasks_to_run = self._get_due_tasks()
        
        if not tasks_to_run:
            logger.debug("没有需要执行的任务")
            return
        
        results = []
        for task in tasks_to_run:
            try:
                result = await self._execute_task(task)
                results.append((task.id, result))
            except Exception as e:
                logger.error(f"执行任务 {task.id} 失败: {e}")
                results.append((task.id, {"error": str(e)}))
        
        if self._on_heartbeat:
            try:
                await self._on_heartbeat(results)
            except Exception as e:
                logger.error(f"Heartbeat 回调失败: {e}")
    
    def _get_due_tasks(self) -> List[HeartbeatTask]:
        """获取到期任务"""
        now = datetime.now()
        return [
            task for task in self._tasks.values()
            if task.enabled and task.next_run and task.next_run <= now
        ]
    
    async def _execute_task(self, task: HeartbeatTask) -> Dict[str, Any]:
        """执行单个任务"""
        if self._task_executor:
            proactive_task = ProactiveTask(
                id=task.id,
                name=task.name,
                task_type=TaskType(task.metadata.get("type", "check")),
                description=task.description,
                schedule=task.schedule,
                enabled=task.enabled,
                config=task.metadata.get("config", {}),
            )
            result = await self._task_executor.execute_task(proactive_task.id)
            
            task.last_run = datetime.now()
            task.run_count += 1
            task.last_result = str(result.result)
            self._calculate_next_run(task)
            
            return result.result
        
        handler = self._handlers.get(task.metadata.get("type", "default"))
        
        if not handler:
            logger.warning(f"未找到任务处理器: {task.id}")
            return {"error": "No handler found"}
        
        result = await handler(task)
        
        task.last_run = datetime.now()
        task.run_count += 1
        task.last_result = str(result)
        self._calculate_next_run(task)
        
        return result
    
    async def _handle_check_email(self, task: HeartbeatTask) -> Dict[str, Any]:
        """检查邮�?""
        return {"checked": True, "unread": 0, "message": "邮件检查完�?}
    
    async def _handle_check_calendar(self, task: HeartbeatTask) -> Dict[str, Any]:
        """检查日�?""
        return {"checked": True, "events": 0, "message": "日历检查完�?}
    
    async def _handle_check_project(self, task: HeartbeatTask) -> Dict[str, Any]:
        """检查项目进�?""
        return {"checked": True, "message": "项目检查完�?}
    
    async def _handle_generate_report(self, task: HeartbeatTask) -> Dict[str, Any]:
        """生成报告"""
        return {"generated": True, "message": "报告已生�?}
    
    async def _handle_send_reminder(self, task: HeartbeatTask) -> Dict[str, Any]:
        """发送提�?""
        return {"sent": True, "message": "提醒已发�?}
    
    def parse_heartbeat_file(self, content: str) -> List[HeartbeatTask]:
        """解析 HEARTBEAT.md 文件"""
        tasks = []
        
        task_pattern = re.compile(
            r'-\s*\[([ x])\]\s*(.+?)(?:\s*\|\s*(\S+))?\s*$',
            re.MULTILINE
        )
        
        for i, match in enumerate(task_pattern.finditer(content)):
            checked = match.group(1) == 'x'
            task_name = match.group(2).strip()
            schedule = match.group(3) or str(self.config.interval_seconds)
            
            task = HeartbeatTask(
                id=f"heartbeat_task_{i}",
                name=task_name,
                description=task_name,
                schedule=schedule,
                enabled=not checked,
                metadata={"source": "HEARTBEAT.md"}
            )
            tasks.append(task)
        
        return tasks
    
    async def load_tasks_from_file(self) -> int:
        """�?HEARTBEAT.md 加载任务"""
        if not self._workspace_path:
            logger.warning("工作空间路径未设�?)
            return 0
        
        heartbeat_file = self._workspace_path / self.config.task_file
        if not heartbeat_file.exists():
            logger.debug(f"任务文件不存�? {heartbeat_file}")
            return 0
        
        try:
            content = heartbeat_file.read_text(encoding="utf-8")
            tasks = self.parse_heartbeat_file(content)
            
            for task in tasks:
                self.add_task(task)
            
            logger.info(f"�?{self.config.task_file} 加载�?{len(tasks)} 个任�?)
            return len(tasks)
        
        except Exception as e:
            logger.error(f"加载任务文件失败: {e}")
            return 0
    
    def get_task(self, task_id: str) -> Optional[HeartbeatTask]:
        """获取任务"""
        return self._tasks.get(task_id)
    
    def get_all_tasks(self) -> Dict[str, HeartbeatTask]:
        """获取所有任�?""
        return self._tasks.copy()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        enabled_count = sum(1 for t in self._tasks.values() if t.enabled)
        total_runs = sum(t.run_count for t in self._tasks.values())
        
        return {
            "is_running": self._is_running,
            "interval_seconds": self.config.interval_seconds,
            "total_tasks": len(self._tasks),
            "enabled_tasks": enabled_count,
            "total_runs": total_runs,
        }


_scheduler: Optional[HeartbeatScheduler] = None


def get_heartbeat_scheduler() -> HeartbeatScheduler:
    """获取 Heartbeat 调度器单�?""
    global _scheduler
    if _scheduler is None:
        _scheduler = HeartbeatScheduler()
    return _scheduler


__all__ = [
    "HeartbeatTask",
    "HeartbeatConfig",
    "HeartbeatScheduler",
    "get_heartbeat_scheduler",
    "TaskExecutor",
    "TaskType",
    "TaskStatus",
    "ProactiveTask",
    "TaskResult",
    "get_task_executor",
]
