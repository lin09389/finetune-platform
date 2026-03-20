"""
工作空间管理模块
提供项目管理、文件管理、版本控制和任务追踪功能
"""
from workspace.models import (
    Project,
    ProjectCreate,
    ProjectUpdate,
    FileVersion,
    FileInfo,
    FileMetadata,
    Task,
    TaskCreate,
    TaskUpdate,
    TaskStatus,
    TaskPriority,
    TaskNotification,
    TaskProgress,
    TaskStatistics,
    SubTask,
)
from workspace.project_manager import ProjectManager, get_project_manager
from workspace.file_manager import FileManager, get_file_manager
from workspace.version_control import VersionControl, get_version_control
from workspace.file_api import router as file_api_router
from workspace.task_manager import TaskManager, get_task_manager
from workspace.task_api import router as task_api_router

__all__ = [
    "Project",
    "ProjectCreate",
    "ProjectUpdate",
    "FileVersion",
    "FileInfo",
    "FileMetadata",
    "ProjectManager",
    "get_project_manager",
    "FileManager",
    "get_file_manager",
    "VersionControl",
    "get_version_control",
    "file_api_router",
    "Task",
    "TaskCreate",
    "TaskUpdate",
    "TaskStatus",
    "TaskPriority",
    "TaskNotification",
    "TaskProgress",
    "TaskStatistics",
    "SubTask",
    "TaskManager",
    "get_task_manager",
    "task_api_router",
]
