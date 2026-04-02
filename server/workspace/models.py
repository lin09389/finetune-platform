"""
工作空间数据模型
定义项目、文件和版本相关的数据结构
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectStatus(str, Enum):
    """项目状态"""
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class FileType(str, Enum):
    """文件类型"""
    CODE = "code"
    DATA = "data"
    MODEL = "model"
    CONFIG = "config"
    DOCUMENT = "document"
    OTHER = "other"


FILE_TYPE_EXTENSIONS = {
    FileType.CODE: [".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c", ".go", ".rs", ".rb", ".php", ".swift", ".kt"],
    FileType.DATA: [".json", ".jsonl", ".csv", ".xml", ".yaml", ".yml", ".parquet", ".arrow"],
    FileType.MODEL: [".bin", ".pt", ".pth", ".ckpt", ".safetensors", ".onnx", ".h5", ".pkl"],
    FileType.CONFIG: [".env", ".ini", ".toml", ".cfg", ".conf", ".properties"],
    FileType.DOCUMENT: [".md", ".txt", ".rst", ".pdf", ".doc", ".docx"],
}


class ProjectCreate(BaseModel):
    """创建项目请求"""
    name: str = Field(..., min_length=1, max_length=100, description="项目名称")
    description: str | None = Field(default=None, max_length=500, description="项目描述")
    tags: list[str] = Field(default_factory=list, description="项目标签")
    metadata: dict[str, Any] = Field(default_factory=dict, description="项目元数据")


class ProjectUpdate(BaseModel):
    """更新项目请求"""
    name: str | None = Field(default=None, min_length=1, max_length=100, description="项目名称")
    description: str | None = Field(default=None, max_length=500, description="项目描述")
    tags: list[str] | None = Field(default=None, description="项目标签")
    metadata: dict[str, Any] | None = Field(default=None, description="项目元数据")
    status: ProjectStatus | None = Field(default=None, description="项目状态")


class Project(BaseModel):
    """项目信息"""
    id: str = Field(default_factory=lambda: f"proj_{uuid.uuid4().hex[:8]}", description="项目ID")
    name: str = Field(..., description="项目名称")
    description: str | None = Field(default=None, description="项目描述")
    tags: list[str] = Field(default_factory=list, description="项目标签")
    status: ProjectStatus = Field(default=ProjectStatus.ACTIVE, description="项目状态")
    metadata: dict[str, Any] = Field(default_factory=dict, description="项目元数据")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="创建时间")
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="更新时间")
    file_count: int = Field(default=0, description="文件数量")
    total_size: int = Field(default=0, description="总大小（字节）")

    model_config = ConfigDict(use_enum_values=True)


class FileVersion(BaseModel):
    """文件版本信息"""
    version_id: str = Field(default_factory=lambda: f"v_{uuid.uuid4().hex[:8]}", description="版本ID")
    file_id: str = Field(..., description="文件ID")
    version_number: int = Field(..., ge=1, description="版本号")
    content_hash: str = Field(..., description="内容哈希")
    size: int = Field(..., ge=0, description="文件大小（字节）")
    message: str | None = Field(default=None, description="版本说明")
    author: str | None = Field(default=None, description="作者")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="创建时间")
    metadata: dict[str, Any] = Field(default_factory=dict, description="版本元数据")


class FileMetadata(BaseModel):
    """文件元数据"""
    encoding: str | None = Field(default="utf-8", description="文件编码")
    language: str | None = Field(default=None, description="编程语言")
    lines: int | None = Field(default=None, description="行数")
    checksum: str | None = Field(default=None, description="校验和")


class FileInfo(BaseModel):
    """文件信息"""
    id: str = Field(default_factory=lambda: f"file_{uuid.uuid4().hex[:8]}", description="文件ID")
    project_id: str = Field(..., description="所属项目ID")
    path: str = Field(..., description="文件路径（相对路径）")
    name: str = Field(..., description="文件名")
    file_type: FileType = Field(default=FileType.OTHER, description="文件类型")
    size: int = Field(default=0, description="文件大小（字节）")
    content_hash: str | None = Field(default=None, description="内容哈希")
    current_version: int = Field(default=1, description="当前版本号")
    version_count: int = Field(default=1, description="版本总数")
    metadata: FileMetadata = Field(default_factory=FileMetadata, description="文件元数据")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="创建时间")
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="更新时间")
    tags: list[str] = Field(default_factory=list, description="文件标签")

    model_config = ConfigDict(use_enum_values=True)


class ProjectStatistics(BaseModel):
    """项目统计信息"""
    project_id: str = Field(..., description="项目ID")
    total_files: int = Field(default=0, description="文件总数")
    total_size: int = Field(default=0, description="总大小（字节）")
    file_types: dict[str, int] = Field(default_factory=dict, description="文件类型分布")
    version_count: int = Field(default=0, description="版本总数")
    latest_activity: str | None = Field(default=None, description="最近活动时间")


class FileVersionDiff(BaseModel):
    """文件版本差异"""
    version_from: int = Field(..., description="起始版本")
    version_to: int = Field(..., description="目标版本")
    additions: int = Field(default=0, description="新增行数")
    deletions: int = Field(default=0, description="删除行数")
    changes: list[dict[str, Any]] = Field(default_factory=list, description="变更详情")


class FileUploadResult(BaseModel):
    """文件上传结果"""
    file_id: str = Field(..., description="文件ID")
    path: str = Field(..., description="文件路径")
    size: int = Field(..., description="文件大小")
    version: int = Field(default=1, description="版本号")
    is_new: bool = Field(default=True, description="是否新文件")
    message: str = Field(default="上传成功", description="消息")


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """任务优先级"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class SubTask(BaseModel):
    """子任务"""
    id: str = Field(default_factory=lambda: f"sub_{uuid.uuid4().hex[:8]}", description="子任务ID")
    title: str = Field(..., description="子任务标题")
    completed: bool = Field(default=False, description="是否完成")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="创建时间")
    completed_at: str | None = Field(default=None, description="完成时间")


class TaskCreate(BaseModel):
    """创建任务请求"""
    title: str = Field(..., min_length=1, max_length=200, description="任务标题")
    description: str | None = Field(default=None, max_length=2000, description="任务描述")
    project_id: str | None = Field(default=None, description="所属项目ID")
    priority: TaskPriority = Field(default=TaskPriority.NORMAL, description="任务优先级")
    due_date: str | None = Field(default=None, description="截止日期 (ISO格式)")
    assignee: str | None = Field(default=None, description="负责人")
    tags: list[str] = Field(default_factory=list, description="任务标签")
    subtasks: list[SubTask] = Field(default_factory=list, description="子任务列表")
    metadata: dict[str, Any] = Field(default_factory=dict, description="任务元数据")


class TaskUpdate(BaseModel):
    """更新任务请求"""
    title: str | None = Field(default=None, min_length=1, max_length=200, description="任务标题")
    description: str | None = Field(default=None, max_length=2000, description="任务描述")
    status: TaskStatus | None = Field(default=None, description="任务状态")
    priority: TaskPriority | None = Field(default=None, description="任务优先级")
    due_date: str | None = Field(default=None, description="截止日期 (ISO格式)")
    assignee: str | None = Field(default=None, description="负责人")
    tags: list[str] | None = Field(default=None, description="任务标签")
    subtasks: list[SubTask] | None = Field(default=None, description="子任务列表")
    progress: int | None = Field(default=None, ge=0, le=100, description="进度百分比")
    metadata: dict[str, Any] | None = Field(default=None, description="任务元数据")


class Task(BaseModel):
    """任务信息"""
    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}", description="任务ID")
    title: str = Field(..., description="任务标题")
    description: str | None = Field(default=None, description="任务描述")
    project_id: str | None = Field(default=None, description="所属项目ID")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="任务状态")
    priority: TaskPriority = Field(default=TaskPriority.NORMAL, description="任务优先级")
    due_date: str | None = Field(default=None, description="截止日期")
    assignee: str | None = Field(default=None, description="负责人")
    tags: list[str] = Field(default_factory=list, description="任务标签")
    subtasks: list[SubTask] = Field(default_factory=list, description="子任务列表")
    progress: int = Field(default=0, ge=0, le=100, description="进度百分比")
    metadata: dict[str, Any] = Field(default_factory=dict, description="任务元数据")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="创建时间")
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="更新时间")
    started_at: str | None = Field(default=None, description="开始时间")
    completed_at: str | None = Field(default=None, description="完成时间")
    created_by: str | None = Field(default=None, description="创建者")

    model_config = ConfigDict(use_enum_values=True)


class TaskNotification(BaseModel):
    """任务通知"""
    id: str = Field(default_factory=lambda: f"notif_{uuid.uuid4().hex[:8]}", description="通知ID")
    task_id: str = Field(..., description="关联任务ID")
    type: str = Field(..., description="通知类型")
    title: str = Field(..., description="通知标题")
    message: str = Field(..., description="通知内容")
    read: bool = Field(default=False, description="是否已读")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="创建时间")
    recipient: str | None = Field(default=None, description="接收者")


class TaskProgress(BaseModel):
    """任务进度更新"""
    task_id: str = Field(..., description="任务ID")
    progress: int = Field(..., ge=0, le=100, description="进度百分比")
    message: str | None = Field(default=None, description="进度消息")
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="更新时间")


class TaskStatistics(BaseModel):
    """任务统计信息"""
    project_id: str | None = Field(default=None, description="项目ID")
    total_tasks: int = Field(default=0, description="任务总数")
    pending_tasks: int = Field(default=0, description="待处理任务数")
    in_progress_tasks: int = Field(default=0, description="进行中任务数")
    completed_tasks: int = Field(default=0, description="已完成任务数")
    cancelled_tasks: int = Field(default=0, description="已取消任务数")
    overdue_tasks: int = Field(default=0, description="逾期任务数")
    high_priority_tasks: int = Field(default=0, description="高优先级任务数")
    completion_rate: float = Field(default=0.0, description="完成率")
