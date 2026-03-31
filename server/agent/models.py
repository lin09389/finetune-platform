"""
Agent 统一模型定义
定义所有执行器共用的结果类型和参数模型
"""
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ResultStatus(str, Enum):
    """执行结果状态"""
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    PENDING = "pending"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class OperationCategory(str, Enum):
    """操作类别"""
    FILE = "file"
    CUA = "cua"
    APP = "app"
    SYSTEM = "system"
    BROWSER = "browser"


@dataclass
class OperationResult:
    """
    统一操作结果类型
    
    所有执行器应返回此类型或其子类
    """
    success: bool
    action: str
    description: str
    status: ResultStatus = ResultStatus.SUCCESS
    data: dict[str, Any] | None = None
    error: str | None = None
    error_code: str | None = None
    feedback: str = ""
    duration_ms: float = 0.0
    need_confirm: bool = False
    category: OperationCategory = OperationCategory.FILE
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if not self.feedback:
            self.feedback = self._generate_feedback()
        if self.success and self.status == ResultStatus.SUCCESS:
            pass
        elif not self.success and self.status == ResultStatus.SUCCESS:
            self.status = ResultStatus.FAILURE

    def _generate_feedback(self) -> str:
        """生成反馈消息"""
        if self.success:
            return f"✅ {self.description}成功"
        else:
            return f"❌ {self.description}失败: {self.error or '未知错误'}"

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "action": self.action,
            "description": self.description,
            "status": self.status.value,
            "data": self.data,
            "error": self.error,
            "error_code": self.error_code,
            "feedback": self.feedback,
            "duration_ms": self.duration_ms,
            "need_confirm": self.need_confirm,
            "category": self.category.value,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def success_result(
        cls,
        action: str,
        description: str,
        data: dict[str, Any] = None,
        feedback: str = "",
        duration_ms: float = 0.0,
        category: OperationCategory = OperationCategory.FILE,
    ) -> "OperationResult":
        """创建成功结果"""
        return cls(
            success=True,
            action=action,
            description=description,
            status=ResultStatus.SUCCESS,
            data=data,
            feedback=feedback,
            duration_ms=duration_ms,
            category=category,
        )

    @classmethod
    def failure_result(
        cls,
        action: str,
        description: str,
        error: str,
        error_code: str = None,
        feedback: str = "",
        duration_ms: float = 0.0,
        category: OperationCategory = OperationCategory.FILE,
    ) -> "OperationResult":
        """创建失败结果"""
        return cls(
            success=False,
            action=action,
            description=description,
            status=ResultStatus.FAILURE,
            error=error,
            error_code=error_code,
            feedback=feedback or f"❌ {description}失败: {error}",
            duration_ms=duration_ms,
            category=category,
        )


@dataclass
class FileResult(OperationResult):
    """文件操作结果"""
    file_path: str | None = None
    file_size: int | None = None
    content: str | None = None
    is_directory: bool = False
    category: OperationCategory = field(default=OperationCategory.FILE, init=False)

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result.update({
            "file_path": self.file_path,
            "file_size": self.file_size,
            "content": self.content[:1000] if self.content and len(self.content) > 1000 else self.content,
            "is_directory": self.is_directory,
        })
        return result


@dataclass
class CUAResult(OperationResult):
    """CUA操作结果"""
    coordinates: tuple | None = None
    screenshot_path: str | None = None
    ocr_text: str | None = None
    window_title: str | None = None
    category: OperationCategory = field(default=OperationCategory.CUA, init=False)

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result.update({
            "coordinates": self.coordinates,
            "screenshot_path": self.screenshot_path,
            "ocr_text": self.ocr_text,
            "window_title": self.window_title,
        })
        return result


@dataclass
class AppResult(OperationResult):
    """应用操作结果"""
    app_name: str | None = None
    process_id: int | None = None
    category: OperationCategory = field(default=OperationCategory.APP, init=False)

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result.update({
            "app_name": self.app_name,
            "process_id": self.process_id,
        })
        return result


@dataclass
class BatchResult(OperationResult):
    """批量操作结果"""
    total_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    results: list[OperationResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_count == 0:
            return 0.0
        return self.success_count / self.total_count * 100

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result.update({
            "total_count": self.total_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": round(self.success_rate, 2),
            "results": [r.to_dict() for r in self.results],
        })
        return result


@dataclass
class OperationParams:
    """操作参数基类"""
    pass


@dataclass
class FileParams(OperationParams):
    """文件操作参数"""
    file_path: str = ""
    content: str = ""
    mode: str = "write"
    encoding: str = "utf-8"
    use_recycle_bin: bool = True
    page: int = 1
    page_size: int = 100


@dataclass
class CUAParams(OperationParams):
    """CUA操作参数"""
    x: int = 0
    y: int = 0
    button: str = "left"
    clicks: int = 1
    text: str = ""
    keys: list[str] = field(default_factory=list)
    title: str = ""
    monitor: int = 0


@dataclass
class AppParams(OperationParams):
    """应用操作参数"""
    app_name: str = ""
    url: str = ""
    args: list[str] = field(default_factory=list)


class OperationTimer:
    """操作计时器"""

    def __init__(self):
        self._start_time = None
        self._end_time = None

    def __enter__(self):
        self._start_time = time.perf_counter()
        return self

    def __exit__(self, *args):
        self._end_time = time.perf_counter()

    @property
    def duration_ms(self) -> float:
        if self._start_time is None:
            return 0.0
        end = self._end_time or time.perf_counter()
        return (end - self._start_time) * 1000


def timed_operation(func):
    """操作计时装饰器"""
    import functools

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        timer = OperationTimer()
        with timer:
            result = await func(*args, **kwargs)
        if hasattr(result, 'duration_ms'):
            result.duration_ms = timer.duration_ms
        return result

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        timer = OperationTimer()
        with timer:
            result = func(*args, **kwargs)
        if hasattr(result, 'duration_ms'):
            result.duration_ms = timer.duration_ms
        return result

    import asyncio
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper
