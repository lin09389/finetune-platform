"""
统一响应格式模块
提供标准化的API响应结构
"""
import time
import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    suggestion: str | None = None


class ResponseMetadata(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: str | None = None
    latency_ms: float | None = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class StandardResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error: ErrorDetail | None = None
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


def generate_request_id() -> str:
    return str(uuid.uuid4())[:8]


def success_response(
    data: Any,
    request_id: str | None = None,
    latency_ms: float | None = None
) -> StandardResponse:
    return StandardResponse(
        success=True,
        data=data,
        metadata=ResponseMetadata(
            request_id=request_id or generate_request_id(),
            latency_ms=latency_ms
        )
    )


def error_response(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    suggestion: str | None = None,
    request_id: str | None = None
) -> StandardResponse:
    return StandardResponse(
        success=False,
        error=ErrorDetail(
            code=code,
            message=message,
            details=details,
            suggestion=suggestion
        ),
        metadata=ResponseMetadata(
            request_id=request_id or generate_request_id()
        )
    )


class ResponseBuilder:
    """响应构建器，用于追踪请求耗时"""

    def __init__(self, request_id: str | None = None):
        self.request_id = request_id or generate_request_id()
        self.start_time = time.time()

    def success(self, data: Any) -> StandardResponse:
        latency_ms = (time.time() - self.start_time) * 1000
        return success_response(
            data=data,
            request_id=self.request_id,
            latency_ms=round(latency_ms, 2)
        )

    def error(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        suggestion: str | None = None
    ) -> StandardResponse:
        return error_response(
            code=code,
            message=message,
            details=details,
            suggestion=suggestion,
            request_id=self.request_id
        )

    def from_exception(
        self,
        exception: Exception,
        code: str = "INTERNAL_ERROR"
    ) -> StandardResponse:
        from api.errors import APIError

        if isinstance(exception, APIError):
            return self.error(
                code=exception.code,
                message=exception.message,
                details=exception.details,
                suggestion=getattr(exception, 'suggestion', None)
            )

        return self.error(
            code=code,
            message=str(exception),
            suggestion="请稍后重试或联系管理员"
        )


ERROR_CODES = {
    "SUCCESS": "操作成功",
    "INTERNAL_ERROR": "内部服务器错误",
    "INVALID_INPUT": "输入参数无效",
    "MODEL_NOT_FOUND": "模型不存在",
    "MODEL_LOAD_FAILED": "模型加载失败",
    "INFERENCE_FAILED": "推理失败",
    "RATE_LIMIT_EXCEEDED": "请求过于频繁",
    "AUTHENTICATION_FAILED": "认证失败",
    "AUTHORIZATION_FAILED": "权限不足",
    "RESOURCE_NOT_FOUND": "资源不存在",
    "RESOURCE_CONFLICT": "资源冲突",
    "SERVICE_UNAVAILABLE": "服务暂时不可用",
    "TIMEOUT": "请求超时",
    "CIRCUIT_BREAKER_OPEN": "熔断器开启，服务降级中",
    "CSRF_TOKEN_MISSING": "CSRF Token缺失",
    "CSRF_TOKEN_INVALID": "CSRF Token无效",
    "PROMPT_INJECTION_DETECTED": "检测到潜在的恶意输入",
    "FILE_TOO_LARGE": "文件大小超出限制",
    "FILE_TYPE_NOT_ALLOWED": "文件类型不允许",
    "SESSION_NOT_FOUND": "会话不存在",
    "SESSION_EXPIRED": "会话已过期",
    "KNOWLEDGE_BASE_NOT_FOUND": "知识库不存在",
    "EMBEDDING_FAILED": "文本嵌入失败",
    "VECTOR_SEARCH_FAILED": "向量检索失败",
}


def get_error_message(code: str) -> str:
    return ERROR_CODES.get(code, "未知错误")
