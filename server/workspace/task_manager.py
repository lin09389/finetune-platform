"""
任务管理器
提供任务的 CRUD 操作、状态管理、分配通知和进度追踪
"""
import asyncio
import json
import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import Optional

from core.config import settings
from core.db_manager import get_db_pool
from workspace.models import (
    SubTask,
    Task,
    TaskCreate,
    TaskNotification,
    TaskPriority,
    TaskProgress,
    TaskStatistics,
    TaskStatus,
    TaskUpdate,
)

logger = logging.getLogger(__name__)


class NotificationManager:
    """
    通知管理器

    功能：
    - 管理任务相关通知
    - 支持通知订阅/推送
    - 通知持久化存储
    """

    def __init__(self, db_path: Path):
        self._notifications: dict[str, list[TaskNotification]] = defaultdict(list)
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._notification_queue: Queue = Queue()
        self._db_path = db_path
        self._lock = threading.RLock()

        self._init_database()
        self._load_notifications()

    def _init_database(self):
        """初始化通知数据库表"""
        db_pool = get_db_pool(str(self._db_path))

        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_notifications (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    read INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    recipient TEXT
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_notifications_task ON task_notifications(task_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON task_notifications(recipient)
            """)

    def _load_notifications(self):
        """从数据库加载通知"""
        db_pool = get_db_pool(str(self._db_path))

        rows = db_pool.execute_query(
            "SELECT * FROM task_notifications ORDER BY created_at DESC LIMIT 100"
        )

        with self._lock:
            for row in rows:
                notification = TaskNotification(
                    id=row['id'],
                    task_id=row['task_id'],
                    type=row['type'],
                    title=row['title'],
                    message=row['message'],
                    read=bool(row['read']),
                    created_at=row['created_at'],
                    recipient=row['recipient'],
                )
                self._notifications[row['recipient'] or 'all'].append(notification)

    def _save_notification(self, notification: TaskNotification):
        """保存通知到数据库"""
        db_pool = get_db_pool(str(self._db_path))

        db_pool.execute_update("""
            INSERT INTO task_notifications
            (id, task_id, type, title, message, read, created_at, recipient)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                type=excluded.type,
                title=excluded.title,
                message=excluded.message,
                read=excluded.read,
                recipient=excluded.recipient
        """, (
            notification.id,
            notification.task_id,
            notification.type,
            notification.title,
            notification.message,
            int(notification.read),
            notification.created_at,
            notification.recipient,
        ))

    def create_notification(
        self,
        task_id: str,
        notification_type: str,
        title: str,
        message: str,
        recipient: str | None = None,
    ) -> TaskNotification:
        """创建通知"""
        notification = TaskNotification(
            task_id=task_id,
            type=notification_type,
            title=title,
            message=message,
            recipient=recipient,
        )

        with self._lock:
            self._notifications[recipient or 'all'].append(notification)

        self._save_notification(notification)
        self._notify_subscribers(notification)

        logger.info(f"通知已创建：{notification.id}, 类型：{notification_type}")
        return notification

    def get_notifications(
        self,
        recipient: str | None = None,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[TaskNotification]:
        """获取通知列表"""
        with self._lock:
            notifications = self._notifications.get(recipient or 'all', [])

        if unread_only:
            notifications = [n for n in notifications if not n.read]

        return notifications[:limit]

    def mark_as_read(self, notification_id: str) -> bool:
        """标记通知为已读"""
        with self._lock:
            for _recipient, notifications in self._notifications.items():
                for notification in notifications:
                    if notification.id == notification_id:
                        notification.read = True
                        self._save_notification(notification)
                        return True
        return False

    def mark_all_as_read(self, recipient: str | None = None) -> int:
        """标记所有通知为已读"""
        count = 0
        with self._lock:
            notifications = self._notifications.get(recipient or 'all', [])
            for notification in notifications:
                if not notification.read:
                    notification.read = True
                    self._save_notification(notification)
                    count += 1
        return count

    def subscribe(self, recipient: str, callback: Callable):
        """订阅通知"""
        with self._lock:
            if callback not in self._subscribers[recipient]:
                self._subscribers[recipient].append(callback)

    def unsubscribe(self, recipient: str, callback: Callable):
        """取消订阅"""
        with self._lock:
            if callback in self._subscribers[recipient]:
                self._subscribers[recipient].remove(callback)

    def _notify_subscribers(self, notification: TaskNotification):
        """通知订阅者"""
        recipients = [notification.recipient] if notification.recipient else ['all']

        for recipient in recipients:
            callbacks = self._subscribers.get(recipient, [])
            for callback in callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.create_task(callback(notification))
                    else:
                        callback(notification)
                except Exception as e:
                    logger.error(f"通知订阅者失败：{e}")


class TaskManager:
    """
    任务管理器

    功能：
    - 任务 CRUD 操作
    - 任务状态管理
    - 任务分配和通知
    - 任务进度追踪
    - 任务统计
    """

    _instance: Optional['TaskManager'] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._tasks: dict[str, Task] = {}
        self._tasks_lock = threading.RLock()
        self._storage_dir = settings.base_dir / "data" / "workspaces"
        self._db_path = self._storage_dir / "tasks.db"
        self._initialized = True

        self._ensure_storage()
        self._init_database()
        self._notification_manager = NotificationManager(self._db_path)
        self._load_tasks()

        logger.info(f"任务管理器已初始化，存储目录：{self._storage_dir}")

    def _ensure_storage(self):
        """确保存储目录存在"""
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def _init_database(self):
        """初始化数据库表"""
        db_pool = get_db_pool(str(self._db_path))

        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    project_id TEXT,
                    status TEXT DEFAULT 'pending',
                    priority TEXT DEFAULT 'normal',
                    due_date TEXT,
                    assignee TEXT,
                    tags TEXT,
                    subtasks TEXT,
                    progress INTEGER DEFAULT 0,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    created_by TEXT
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date)
            """)
            logger.debug("任务数据库表已初始化")

    def _load_tasks(self):
        """从数据库加载任务"""
        db_pool = get_db_pool(str(self._db_path))

        rows = db_pool.execute_query("SELECT * FROM tasks WHERE status != ?", ("cancelled",))

        with self._tasks_lock:
            for row in rows:
                subtasks_data = json.loads(row['subtasks']) if row['subtasks'] else []
                subtasks = [SubTask(**st) for st in subtasks_data]

                task = Task(
                    id=row['id'],
                    title=row['title'],
                    description=row['description'],
                    project_id=row['project_id'],
                    status=row['status'],
                    priority=row['priority'],
                    due_date=row['due_date'],
                    assignee=row['assignee'],
                    tags=json.loads(row['tags']) if row['tags'] else [],
                    subtasks=subtasks,
                    progress=row['progress'] or 0,
                    metadata=json.loads(row['metadata']) if row['metadata'] else {},
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    started_at=row['started_at'],
                    completed_at=row['completed_at'],
                    created_by=row['created_by'],
                )
                self._tasks[task.id] = task

        logger.info(f"已加载 {len(self._tasks)} 个任务")

    def _save_task(self, task: Task):
        """保存任务到数据库"""
        db_pool = get_db_pool(str(self._db_path))

        subtasks_data = [st.model_dump() for st in task.subtasks]

        db_pool.execute_update("""
            INSERT INTO tasks
            (id, title, description, project_id, status, priority, due_date, assignee,
             tags, subtasks, progress, metadata, created_at, updated_at, started_at, completed_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                description=excluded.description,
                project_id=excluded.project_id,
                status=excluded.status,
                priority=excluded.priority,
                due_date=excluded.due_date,
                assignee=excluded.assignee,
                tags=excluded.tags,
                subtasks=excluded.subtasks,
                progress=excluded.progress,
                metadata=excluded.metadata,
                updated_at=excluded.updated_at,
                started_at=excluded.started_at,
                completed_at=excluded.completed_at,
                created_by=excluded.created_by
        """, (
            task.id,
            task.title,
            task.description,
            task.project_id,
            task.status,
            task.priority,
            task.due_date,
            task.assignee,
            json.dumps(task.tags),
            json.dumps(subtasks_data),
            task.progress,
            json.dumps(task.metadata),
            task.created_at,
            task.updated_at,
            task.started_at,
            task.completed_at,
            task.created_by,
        ))

    def create_task(self, data: TaskCreate, created_by: str | None = None) -> Task:
        """创建任务"""
        task = Task(
            title=data.title,
            description=data.description,
            project_id=data.project_id,
            priority=data.priority,
            due_date=data.due_date,
            assignee=data.assignee,
            tags=data.tags,
            subtasks=data.subtasks,
            metadata=data.metadata,
            created_by=created_by,
        )

        with self._tasks_lock:
            self._tasks[task.id] = task

        self._save_task(task)

        if task.assignee:
            self._notification_manager.create_notification(
                task_id=task.id,
                notification_type="task_assigned",
                title=f"新任务分配：{task.title}",
                message=f"您被分配了一个新任务：{task.title}",
                recipient=task.assignee,
            )

        logger.info(f"任务已创建：{task.id}, 标题：{task.title}")
        return task

    def get_task(self, task_id: str) -> Task | None:
        """获取任务"""
        with self._tasks_lock:
            return self._tasks.get(task_id)

    def list_tasks(
        self,
        project_id: str | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        assignee: str | None = None,
        tags: list[str] | None = None,
        search: str | None = None,
        overdue: bool | None = None,
    ) -> list[Task]:
        """
        列出任务

        Args:
            project_id: 按项目筛选
            status: 按状态筛选
            priority: 按优先级筛选
            assignee: 按负责人筛选
            tags: 按标签筛选
            search: 搜索标题或描述
            overdue: 筛选逾期任务
        """
        with self._tasks_lock:
            tasks = list(self._tasks.values())

        if project_id:
            tasks = [t for t in tasks if t.project_id == project_id]

        if status:
            tasks = [t for t in tasks if t.status == status.value]

        if priority:
            tasks = [t for t in tasks if t.priority == priority.value]

        if assignee:
            tasks = [t for t in tasks if t.assignee == assignee]

        if tags:
            tasks = [t for t in tasks if any(tag in t.tags for tag in tags)]

        if search:
            search_lower = search.lower()
            tasks = [
                t for t in tasks
                if search_lower in t.title.lower() or
                   (t.description and search_lower in t.description.lower())
            ]

        if overdue is not None:
            now = datetime.now()
            if overdue:
                tasks = [
                    t for t in tasks
                    if t.due_date and
                       datetime.fromisoformat(t.due_date) < now and
                       t.status not in [TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value]
                ]
            else:
                tasks = [
                    t for t in tasks
                    if not t.due_date or
                       datetime.fromisoformat(t.due_date) >= now or
                       t.status in [TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value]
                ]

        return sorted(tasks, key=lambda t: (t.priority, t.updated_at), reverse=True)

    def update_task(self, task_id: str, data: TaskUpdate) -> Task | None:
        """更新任务"""
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if not task:
                return None

            old_assignee = task.assignee
            old_status = task.status

            update_data = data.model_dump(exclude_unset=True)

            for key, value in update_data.items():
                if hasattr(task, key):
                    setattr(task, key, value)

            if data.status and data.status != old_status:
                self._handle_status_change(task, old_status, data.status)

            task.updated_at = datetime.now().isoformat()

            self._save_task(task)

            if data.assignee and data.assignee != old_assignee:
                self._notification_manager.create_notification(
                    task_id=task.id,
                    notification_type="task_reassigned",
                    title=f"任务重新分配：{task.title}",
                    message=f"任务已重新分配给您：{task.title}",
                    recipient=data.assignee,
                )

        logger.info(f"任务已更新：{task_id}")
        return task

    def _handle_status_change(self, task: Task, old_status: str, new_status: str):
        """处理任务状态变更"""
        now = datetime.now().isoformat()

        if new_status == TaskStatus.IN_PROGRESS.value:
            task.started_at = now
            self._notification_manager.create_notification(
                task_id=task.id,
                notification_type="task_started",
                title=f"任务开始：{task.title}",
                message=f"任务已开始执行：{task.title}",
                recipient=task.created_by,
            )

        elif new_status == TaskStatus.COMPLETED.value:
            task.completed_at = now
            task.progress = 100
            self._notification_manager.create_notification(
                task_id=task.id,
                notification_type="task_completed",
                title=f"任务完成：{task.title}",
                message=f"任务已完成：{task.title}",
                recipient=task.created_by,
            )

        elif new_status == TaskStatus.CANCELLED.value:
            task.completed_at = now
            if task.assignee:
                self._notification_manager.create_notification(
                    task_id=task.id,
                    notification_type="task_cancelled",
                    title=f"任务取消：{task.title}",
                    message=f"任务已取消：{task.title}",
                    recipient=task.assignee,
                )

    def delete_task(self, task_id: str, hard: bool = False) -> bool:
        """
        删除任务

        Args:
            task_id: 任务ID
            hard: 是否硬删除（物理删除）
        """
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if not task:
                return False

            if hard:
                del self._tasks[task_id]
                db_pool = get_db_pool(str(self._db_path))
                db_pool.execute_update("DELETE FROM tasks WHERE id = ?", (task_id,))
                logger.info(f"任务已硬删除：{task_id}")
            else:
                task.status = TaskStatus.CANCELLED.value
                task.updated_at = datetime.now().isoformat()
                self._save_task(task)
                logger.info(f"任务已软删除：{task_id}")

        return True

    def update_progress(self, task_id: str, progress: int, message: str | None = None) -> TaskProgress | None:
        """更新任务进度"""
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if not task:
                return None

            task.progress = min(100, max(0, progress))
            task.updated_at = datetime.now().isoformat()

            if task.progress == 100 and task.status != TaskStatus.COMPLETED.value:
                task.status = TaskStatus.COMPLETED.value
                task.completed_at = datetime.now().isoformat()
                self._handle_status_change(task, task.status, TaskStatus.COMPLETED.value)

            self._save_task(task)

        task_progress = TaskProgress(
            task_id=task_id,
            progress=task.progress,
            message=message,
        )

        if message:
            self._notification_manager.create_notification(
                task_id=task_id,
                notification_type="progress_update",
                title=f"进度更新：{task.title}",
                message=message,
                recipient=task.created_by,
            )

        logger.info(f"任务进度已更新：{task_id}, 进度：{progress}%")
        return task_progress

    def update_subtask(self, task_id: str, subtask_id: str, completed: bool) -> Task | None:
        """更新子任务状态"""
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if not task:
                return None

            for subtask in task.subtasks:
                if subtask.id == subtask_id:
                    subtask.completed = completed
                    subtask.completed_at = datetime.now().isoformat() if completed else None
                    break

            completed_count = sum(1 for st in task.subtasks if st.completed)
            if task.subtasks:
                task.progress = int((completed_count / len(task.subtasks)) * 100)

            task.updated_at = datetime.now().isoformat()
            self._save_task(task)

        logger.info(f"子任务已更新：{subtask_id}, 任务：{task_id}")
        return task

    def assign_task(self, task_id: str, assignee: str) -> Task | None:
        """分配任务"""
        return self.update_task(task_id, TaskUpdate(assignee=assignee))

    def get_statistics(self, project_id: str | None = None) -> TaskStatistics:
        """获取任务统计信息"""
        tasks = self.list_tasks(project_id=project_id)

        now = datetime.now()

        stats = TaskStatistics(project_id=project_id)
        stats.total_tasks = len(tasks)

        for task in tasks:
            if task.status == TaskStatus.PENDING.value:
                stats.pending_tasks += 1
            elif task.status == TaskStatus.IN_PROGRESS.value:
                stats.in_progress_tasks += 1
            elif task.status == TaskStatus.COMPLETED.value:
                stats.completed_tasks += 1
            elif task.status == TaskStatus.CANCELLED.value:
                stats.cancelled_tasks += 1

            if task.due_date:
                due_date = datetime.fromisoformat(task.due_date)
                if due_date < now and task.status not in [TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value]:
                    stats.overdue_tasks += 1

            if task.priority in [TaskPriority.HIGH.value, TaskPriority.URGENT.value]:
                stats.high_priority_tasks += 1

        if stats.total_tasks > 0:
            stats.completion_rate = (stats.completed_tasks / stats.total_tasks) * 100

        return stats

    def get_notifications(
        self,
        recipient: str | None = None,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[TaskNotification]:
        """获取通知"""
        return self._notification_manager.get_notifications(recipient, unread_only, limit)

    def mark_notification_read(self, notification_id: str) -> bool:
        """标记通知为已读"""
        return self._notification_manager.mark_as_read(notification_id)

    def mark_all_notifications_read(self, recipient: str | None = None) -> int:
        """标记所有通知为已读"""
        return self._notification_manager.mark_all_as_read(recipient)

    def subscribe_notifications(self, recipient: str, callback: Callable):
        """订阅通知"""
        self._notification_manager.subscribe(recipient, callback)

    def unsubscribe_notifications(self, recipient: str, callback: Callable):
        """取消订阅通知"""
        self._notification_manager.unsubscribe(recipient, callback)


_task_manager: TaskManager | None = None
_manager_lock = threading.Lock()


def get_task_manager() -> TaskManager:
    """获取任务管理器实例"""
    global _task_manager
    with _manager_lock:
        if _task_manager is None:
            _task_manager = TaskManager()
        return _task_manager
