from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .interfaces.types import (
    ExecutionResult,
    ExecutionStatus,
    FileResult,
    OperationContext,
    OperationResult,
    TaskResult,
    UnifiedResult,
    ValidationResult,
)


class IntentType(str, Enum):
    FILE_OPERATION = "file_operation"
    SYSTEM_CONTROL = "system_control"
    APPLICATION = "application"
    NETWORK = "network"
    CLIPBOARD = "clipboard"
    SCREENSHOT = "screenshot"
    UNKNOWN = "unknown"


class PermissionLevel(str, Enum):
    ALLOWED = "allowed"
    DENIED = "denied"
    REQUIRES_VERIFICATION = "requires_verification"
    REQUIRES_ELEVATION = "requires_elevation"


class ErrorCode(str, Enum):
    PARSE_ERROR = "parse_error"
    PERMISSION_DENIED = "permission_denied"
    EXECUTION_ERROR = "execution_error"
    VALIDATION_ERROR = "validation_error"
    TIMEOUT_ERROR = "timeout_error"
    RESOURCE_NOT_FOUND = "resource_not_found"
    INTERNAL_ERROR = "internal_error"
    SERVICE_UNAVAILABLE = "service_unavailable"


class ParseResult(BaseModel):
    intent: IntentType = Field(default=IntentType.UNKNOWN)
    action: str = Field(default="")
    params: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    raw_message: str = Field(default="")
    alternatives: list["ParseResult"] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PermissionResult(BaseModel):
    level: PermissionLevel = Field(default=PermissionLevel.ALLOWED)
    reason: str = Field(default="")
    required_verification: str | None = Field(default=None)
    allowed_actions: list[str] = Field(default_factory=list)
    denied_actions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FormattedResult(BaseModel):
    success: bool = Field(default=True)
    message: str = Field(default="")
    data: Any = Field(default=None)
    suggestions: list[str] = Field(default_factory=list)
    follow_up_actions: list[str] = Field(default_factory=list)


class ErrorResult(BaseModel):
    error_code: ErrorCode = Field(default=ErrorCode.INTERNAL_ERROR)
    message: str = Field(default="")
    details: dict[str, Any] = Field(default_factory=dict)
    recoverable: bool = Field(default=True)
    recovery_suggestions: list[str] = Field(default_factory=list)


class ProgressInfo(BaseModel):
    task_id: str
    progress: float = Field(ge=0.0, le=1.0)
    status: str = ""
    message: str = ""
    current_step: int = 0
    total_steps: int = 0
    eta_seconds: float | None = None


class ModuleInfo(BaseModel):
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    dependencies: list[str] = Field(default_factory=list)
    supported_actions: list[str] = Field(default_factory=list)


ParseResult.model_rebuild()

__all__ = [
    "IntentType",
    "PermissionLevel",
    "ErrorCode",
    "ParseResult",
    "PermissionResult",
    "FormattedResult",
    "ErrorResult",
    "ProgressInfo",
    "ModuleInfo",
    "UnifiedResult",
    "ExecutionResult",
    "OperationResult",
    "FileResult",
    "TaskResult",
    "OperationContext",
    "ExecutionStatus",
    "ValidationResult",
]
