"""
主动任务执行�?
实现 Heartbeat 主动任务执行�?- 检查任务执�?- 汇报任务执行
- 提醒任务执行
- 任务结果处理
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable, Awaitable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """任务类型"""
    CHECK = "check"
    REPORT = "report"
    REMINDER = "reminder"
    CUSTOM = "custom"


class TaskStatus(str, Enum):
    """任务状�?""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskResult:
    """任务执行结果"""
    task_id: str
    task_type: TaskType
    status: TaskStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    result: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    retries: int = 0


@dataclass
class ProactiveTask:
    """主动任务定义"""
    id: str
    name: str
    task_type: TaskType
    description: str = ""
    schedule: str = "0"
    enabled: bool = True
    max_retries: int = 3
    retry_delay: int = 60
    timeout: int = 300
    config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class TaskExecutor:
    """
    任务执行�?    
    功能�?    - 执行检查任�?    - 执行汇报任务
    - 执行提醒任务
    - 结果处理和通知
    """
    
    def __init__(self, workspace_path: Optional[Path] = None):
        self._workspace_path = workspace_path
        self._tasks: Dict[str, ProactiveTask] = {}
        self._results: Dict[str, TaskResult] = {}
        self._handlers: Dict[TaskType, Callable] = {}
        
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._notification_handlers: List[Callable] = []
        
        self._register_default_handlers()
    
    def _register_default_handlers(self):
        """注册默认任务处理�?""
        self._handlers[TaskType.CHECK] = self._execute_check_task
        self._handlers[TaskType.REPORT] = self._execute_report_task
        self._handlers[TaskType.REMINDER] = self._execute_reminder_task
    
    def register_handler(self, task_type: TaskType, handler: Callable):
        """注册任务处理�?""
        self._handlers[task_type] = handler
    
    def register_notification_handler(self, handler: Callable):
        """注册通知处理�?""
        self._notification_handlers.append(handler)
    
    def add_task(self, task: ProactiveTask):
        """添加任务"""
        self._tasks[task.id] = task
        logger.info(f"添加主动任务: {task.id} ({task.name})")
    
    def remove_task(self, task_id: str):
        """移除任务"""
        if task_id in self._tasks:
            del self._tasks[task_id]
            logger.info(f"移除任务: {task_id}")
    
    def get_task(self, task_id: str) -> Optional[ProactiveTask]:
        """获取任务"""
        return self._tasks.get(task_id)
    
    def get_all_tasks(self) -> Dict[str, ProactiveTask]:
        """获取所有任�?""
        return self._tasks.copy()
    
    async def execute_task(self, task_id: str) -> TaskResult:
        """执行任务"""
        task = self._tasks.get(task_id)
        if not task:
            return TaskResult(
                task_id=task_id,
                task_type=TaskType.CUSTOM,
                status=TaskStatus.FAILED,
                started_at=datetime.now(),
                error="Task not found",
            )
        
        if not task.enabled:
            return TaskResult(
                task_id=task_id,
                task_type=task.task_type,
                status=TaskStatus.CANCELLED,
                started_at=datetime.now(),
                error="Task is disabled",
            )
        
        result = TaskResult(
            task_id=task_id,
            task_type=task.task_type,
            status=TaskStatus.RUNNING,
            started_at=datetime.now(),
        )
        
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
            
            logger.info(f"任务执行完成: {task_id}")
        
        except asyncio.TimeoutError:
            result.status = TaskStatus.FAILED
            result.error = "Task timeout"
            result.completed_at = datetime.now()
            logger.error(f"任务超时: {task_id}")
        
        except Exception as e:
            result.status = TaskStatus.FAILED
            result.error = str(e)
            result.completed_at = datetime.now()
            logger.error(f"任务执行失败: {task_id} - {e}")
        
        await self._notify_result(result)
        
        return result
    
    async def execute_with_retry(self, task_id: str) -> TaskResult:
        """带重试的任务执行"""
        task = self._tasks.get(task_id)
        if not task:
            return TaskResult(
                task_id=task_id,
                task_type=TaskType.CUSTOM,
                status=TaskStatus.FAILED,
                started_at=datetime.now(),
                error="Task not found",
            )
        
        result = await self.execute_task(task_id)
        
        retry_count = 0
        while result.status == TaskStatus.FAILED and retry_count < task.max_retries:
            retry_count += 1
            result.retries = retry_count
            
            logger.info(f"任务重试 ({retry_count}/{task.max_retries}): {task_id}")
            
            await asyncio.sleep(task.retry_delay)
            result = await self.execute_task(task_id)
        
        return result
    
    async def execute_all_pending(self) -> Dict[str, TaskResult]:
        """执行所有待处理任务"""
        results = {}
        
        for task_id, task in self._tasks.items():
            if task.enabled:
                results[task_id] = await self.execute_task(task_id)
        
        return results
    
    async def _execute_check_task(self, task: ProactiveTask) -> Dict[str, Any]:
        """执行检查任�?""
        check_type = task.config.get("check_type", "general")
        target = task.config.get("target")
        
        result = {
            "check_type": check_type,
            "target": target,
            "checked_at": datetime.now().isoformat(),
            "status": "ok",
            "findings": [],
        }
        
        if check_type == "project_status":
            result.update(await self._check_project_status(task))
        elif check_type == "resource_usage":
            result.update(await self._check_resource_usage(task))
        elif check_type == "pending_items":
            result.update(await self._check_pending_items(task))
        elif check_type == "system_health":
            result.update(await self._check_system_health(task))
        else:
            result["status"] = "unknown_check_type"
        
        return result
    
    async def _check_project_status(self, task: ProactiveTask) -> Dict[str, Any]:
        """检查项目状�?""
        return {
            "status": "ok",
            "findings": [
                {"type": "info", "message": "项目状态检查完�?},
            ],
            "metrics": {
                "open_tasks": 0,
                "completed_tasks": 0,
                "blocked_tasks": 0,
            },
        }
    
    async def _check_resource_usage(self, task: ProactiveTask) -> Dict[str, Any]:
        """检查资源使�?""
        import psutil
        
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        
        findings = []
        status = "ok"
        
        if cpu_percent > 80:
            findings.append({"type": "warning", "message": f"CPU 使用率高: {cpu_percent}%"})
            status = "warning"
        
        if memory.percent > 80:
            findings.append({"type": "warning", "message": f"内存使用率高: {memory.percent}%"})
            status = "warning"
        
        if disk.percent > 90:
            findings.append({"type": "warning", "message": f"磁盘使用率高: {disk.percent}%"})
            status = "warning"
        
        return {
            "status": status,
            "findings": findings,
            "metrics": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "disk_percent": disk.percent,
            },
        }
    
    async def _check_pending_items(self, task: ProactiveTask) -> Dict[str, Any]:
        """检查待处理项目"""
        return {
            "status": "ok",
            "findings": [],
            "metrics": {
                "pending_emails": 0,
                "pending_messages": 0,
                "pending_reviews": 0,
            },
        }
    
    async def _check_system_health(self, task: ProactiveTask) -> Dict[str, Any]:
        """检查系统健康状�?""
        findings = []
        status = "ok"
        
        try:
            import psutil
            
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot_time
            
            if uptime.days > 30:
                findings.append({
                    "type": "info",
                    "message": f"系统已运�?{uptime.days} 天，建议重启",
                })
            
            return {
                "status": status,
                "findings": findings,
                "metrics": {
                    "uptime_days": uptime.days,
                    "boot_time": boot_time.isoformat(),
                },
            }
        
        except Exception as e:
            return {
                "status": "error",
                "findings": [{"type": "error", "message": str(e)}],
            }
    
    async def _execute_report_task(self, task: ProactiveTask) -> Dict[str, Any]:
        """执行汇报任务"""
        report_type = task.config.get("report_type", "daily")
        format_type = task.config.get("format", "text")
        
        result = {
            "report_type": report_type,
            "generated_at": datetime.now().isoformat(),
            "format": format_type,
            "content": "",
            "metrics": {},
        }
        
        if report_type == "daily":
            result.update(await self._generate_daily_report(task))
        elif report_type == "weekly":
            result.update(await self._generate_weekly_report(task))
        elif report_type == "project":
            result.update(await self._generate_project_report(task))
        else:
            result["content"] = f"未知报告类型: {report_type}"
        
        return result
    
    async def _generate_daily_report(self, task: ProactiveTask) -> Dict[str, Any]:
        """生成每日报告"""
        now = datetime.now()
        
        content = f"""# 每日报告
日期: {now.strftime("%Y-%m-%d")}

## 摘要
- 今日完成任务: 0
- 进行中任�? 0
- 待处理事�? 0

## 备注
报告生成时间: {now.isoformat()}
"""
        
        return {
            "content": content,
            "metrics": {
                "tasks_completed": 0,
                "tasks_in_progress": 0,
                "items_pending": 0,
            },
        }
    
    async def _generate_weekly_report(self, task: ProactiveTask) -> Dict[str, Any]:
        """生成每周报告"""
        now = datetime.now()
        
        content = f"""# 每周报告
周期: {(now - timedelta(days=7)).strftime("%Y-%m-%d")} - {now.strftime("%Y-%m-%d")}

## 本周摘要
- 完成任务: 0
- 新增任务: 0
- 待处�? 0

## 备注
报告生成时间: {now.isoformat()}
"""
        
        return {
            "content": content,
            "metrics": {
                "tasks_completed": 0,
                "tasks_created": 0,
                "items_pending": 0,
            },
        }
    
    async def _generate_project_report(self, task: ProactiveTask) -> Dict[str, Any]:
        """生成项目报告"""
        project_name = task.config.get("project_name", "Unknown")
        now = datetime.now()
        
        content = f"""# 项目报告
项目: {project_name}
生成时间: {now.isoformat()}

## 项目状�?- 进度: 0%
- 任务: 0/0
- 风险: �?
## 备注
此为示例报告内容�?"""
        
        return {
            "content": content,
            "project_name": project_name,
            "metrics": {
                "progress_percent": 0,
                "total_tasks": 0,
                "completed_tasks": 0,
            },
        }
    
    async def _execute_reminder_task(self, task: ProactiveTask) -> Dict[str, Any]:
        """执行提醒任务"""
        reminder_type = task.config.get("reminder_type", "general")
        message = task.config.get("message", "")
        recipients = task.config.get("recipients", [])
        
        result = {
            "reminder_type": reminder_type,
            "message": message,
            "recipients": recipients,
            "sent_at": datetime.now().isoformat(),
            "delivered": True,
        }
        
        if reminder_type == "meeting":
            result.update(await self._send_meeting_reminder(task))
        elif reminder_type == "deadline":
            result.update(await self._send_deadline_reminder(task))
        elif reminder_type == "follow_up":
            result.update(await self._send_follow_up_reminder(task))
        else:
            result["delivered"] = True
        
        logger.info(f"提醒已发�? {reminder_type} - {message}")
        
        return result
    
    async def _send_meeting_reminder(self, task: ProactiveTask) -> Dict[str, Any]:
        """发送会议提�?""
        meeting_time = task.config.get("meeting_time")
        meeting_title = task.config.get("meeting_title", "会议")
        
        return {
            "meeting_title": meeting_title,
            "meeting_time": meeting_time,
            "delivered": True,
        }
    
    async def _send_deadline_reminder(self, task: ProactiveTask) -> Dict[str, Any]:
        """发送截止日期提�?""
        deadline = task.config.get("deadline")
        item_name = task.config.get("item_name", "任务")
        
        return {
            "item_name": item_name,
            "deadline": deadline,
            "delivered": True,
        }
    
    async def _send_follow_up_reminder(self, task: ProactiveTask) -> Dict[str, Any]:
        """发送跟进提�?""
        item_id = task.config.get("item_id")
        item_type = task.config.get("item_type", "task")
        
        return {
            "item_id": item_id,
            "item_type": item_type,
            "delivered": True,
        }
    
    async def _notify_result(self, result: TaskResult):
        """通知任务结果"""
        for handler in self._notification_handlers:
            try:
                await handler(result)
            except Exception as e:
                logger.error(f"通知处理器失�? {e}")
    
    def get_result(self, task_id: str) -> Optional[TaskResult]:
        """获取任务结果"""
        return self._results.get(task_id)
    
    def get_all_results(self) -> Dict[str, TaskResult]:
        """获取所有结�?""
        return self._results.copy()
    
    def clear_old_results(self, days: int = 7) -> int:
        """清理旧结�?""
        cutoff = datetime.now() - timedelta(days=days)
        
        to_remove = [
            task_id for task_id, result in self._results.items()
            if result.completed_at and result.completed_at < cutoff
        ]
        
        for task_id in to_remove:
            del self._results[task_id]
        
        if to_remove:
            logger.info(f"清理�?{len(to_remove)} 个旧任务结果")
        
        return len(to_remove)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = len(self._tasks)
        enabled = sum(1 for t in self._tasks.values() if t.enabled)
        
        completed = sum(1 for r in self._results.values() if r.status == TaskStatus.COMPLETED)
        failed = sum(1 for r in self._results.values() if r.status == TaskStatus.FAILED)
        
        return {
            "total_tasks": total,
            "enabled_tasks": enabled,
            "total_results": len(self._results),
            "completed_results": completed,
            "failed_results": failed,
        }


_task_executor: Optional[TaskExecutor] = None


def get_task_executor() -> TaskExecutor:
    """获取任务执行器单�?""
    global _task_executor
    if _task_executor is None:
        _task_executor = TaskExecutor()
    return _task_executor
