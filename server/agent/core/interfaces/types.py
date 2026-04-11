"""
统一类型定义
合并 ExecutionResult, OperationResult, FileResult, TaskResult
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AgentException(Exception):
    """Agent 基础异常"""
    def __init__(self, message: str, error_code: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "AGENT_ERROR"
        self.details = details or {}


class ValidationException(AgentException):
    """验证异常"""
    def __init__(self, message: str, field: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message, "VALIDATION_ERROR", details)
        self.field = field


class PermissionException(AgentException):
    """权限异常"""
    def __init__(self, message: str, resource: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message, "PERMISSION_DENIED", details)
        self.resource = resource


class ResourceNotFoundException(AgentException):
    """资源未找到异常"""
    def __init__(self, resource_type: str, resource_id: str, details: dict[str, Any] | None = None):
        super().__init__(f"{resource_type} 不存在: {resource_id}", "RESOURCE_NOT_FOUND", details)
        self.resource_type = resource_type
        self.resource_id = resource_id


class OperationTimeoutException(AgentException):
    """操作超时异常"""
    def __init__(self, operation: str, timeout_seconds: float, details: dict[str, Any] | None = None):
        super().__init__(f"操作超时: {operation} (超过 {timeout_seconds} 秒)", "TIMEOUT_ERROR", details)
        self.operation = operation
        self.timeout_seconds = timeout_seconds


class UnsupportedActionException(AgentException):
    """不支持的操作异常"""
    def __init__(self, action: str, available_actions: list[str] | None = None, details: dict[str, Any] | None = None):
        super().__init__(f"不支持的操作: {action}", "UNSUPPORTED_ACTION", details)
        self.action = action
        self.available_actions = available_actions or []


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    PENDING = "pending"
    CANCELLED = "cancelled"
    RUNNING = "running"


class ErrorCode(str, Enum):
    PARSE_ERROR = "parse_error"
    PERMISSION_DENIED = "permission_denied"
    EXECUTION_ERROR = "execution_error"
    VALIDATION_ERROR = "validation_error"
    TIMEOUT_ERROR = "timeout_error"
    RESOURCE_NOT_FOUND = "resource_not_found"
    INTERNAL_ERROR = "internal_error"
    UNSUPPORTED_ACTION = "unsupported_action"
    INVALID_PARAMS = "invalid_params"
    FILE_NOT_FOUND = "file_not_found"
    FILE_EXISTS = "file_exists"
    NOT_A_FILE = "not_a_file"
    NOT_A_DIR = "not_a_dir"
    DIR_NOT_FOUND = "dir_not_found"
    SOURCE_NOT_FOUND = "source_not_found"
    PATH_NOT_FOUND = "path_not_found"
    HANDLER_NOT_FOUND = "handler_not_found"
    NOT_IMPLEMENTED = "not_implemented"


@dataclass
class UnifiedResult:
    success: bool
    status: ExecutionStatus = ExecutionStatus.SUCCESS
    action: str = ""
    message: str = ""
    data: dict[str, Any] | None = None
    error: str | None = None
    error_code: ErrorCode | None = None
    output: Any = None
    feedback: str = ""
    operation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(
        cls,
        action: str = "",
        message: str = "操作成功",
        data: dict[str, Any] | None = None,
        feedback: str = "",
        output: Any = None,
    ) -> "UnifiedResult":
        return cls(
            success=True,
            status=ExecutionStatus.SUCCESS,
            action=action,
            message=message,
            data=data,
            feedback=feedback or message,
            output=output,
        )

    @classmethod
    def fail(
        cls,
        action: str = "",
        error: str = "操作失败",
        error_code: ErrorCode | None = None,
        data: dict[str, Any] | None = None,
        feedback: str = "",
    ) -> "UnifiedResult":
        return cls(
            success=False,
            status=ExecutionStatus.FAILED,
            action=action,
            error=error,
            error_code=error_code or ErrorCode.EXECUTION_ERROR,
            data=data,
            feedback=feedback or error,
        )

    @classmethod
    def partial(
        cls,
        action: str = "",
        message: str = "部分成功",
        data: dict[str, Any] | None = None,
        feedback: str = "",
    ) -> "UnifiedResult":
        return cls(
            success=True,
            status=ExecutionStatus.PARTIAL,
            action=action,
            message=message,
            data=data,
            feedback=feedback or message,
        )

    def to_dict(self) -> dict[str, Any]:
        error_code = None
        if self.error_code:
            error_code = self.error_code.value if hasattr(self.error_code, "value") else str(self.error_code)
        return {
            "success": self.success,
            "status": self.status.value,
            "action": self.action,
            "message": self.message,
            "data": self.data,
            "error": self.error,
            "error_code": error_code,
            "output": self.output,
            "feedback": self.feedback,
            "operation_id": self.operation_id,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }

    def to_api_response(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message or self.feedback,
            "data": self.data,
            "error": self.error,
        }


ExecutionResult = UnifiedResult
OperationResult = UnifiedResult
FileResult = UnifiedResult


@dataclass
class TaskResult:
    task_id: str
    task_type: str
    status: ExecutionStatus
    started_at: datetime
    completed_at: datetime | None = None
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    retries: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
            "retries": self.retries,
        }


@dataclass
class OperationContext:
    workspace: str = "."
    user_id: str | None = None
    session_id: str | None = None
    permissions: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    timeout: int = 300
    dry_run: bool = False

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions or "*" in self.permissions

    def require_permission(self, permission: str) -> None:
        if not self.has_permission(permission):
            raise PermissionError(f"缺少权限: {permission}")


class ValidationResult:
    def __init__(
        self,
        is_valid: bool = True,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
        sanitized_params: dict[str, Any] | None = None,
    ):
        self.is_valid = is_valid
        self.errors = errors or []
        self.warnings = warnings or []
        self.sanitized_params = sanitized_params or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "sanitized_params": self.sanitized_params,
        }
