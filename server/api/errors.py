"""
统一错误处理 - 参�?Ollama 错误处理模式
提供一致的错误响应格式
"""
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any
from enum import Enum


class ErrorCode(str, Enum):
    MODEL_NOT_FOUND = "model_not_found"
    MODEL_LOAD_FAILED = "model_load_failed"
    SESSION_NOT_FOUND = "session_not_found"
    COLLECTION_NOT_FOUND = "collection_not_found"
    DOCUMENT_NOT_FOUND = "document_not_found"
    MEMORY_NOT_FOUND = "memory_not_found"
    ENTITY_NOT_FOUND = "entity_not_found"
    
    OLLAMA_NOT_RUNNING = "ollama_not_running"
    OLLAMA_UNAVAILABLE = "ollama_unavailable"
    
    CONTEXT_TOO_LONG = "context_too_long"
    MALICIOUS_INPUT = "malicious_input"
    INVALID_INPUT = "invalid_input"
    RATE_LIMITED = "rate_limited"
    
    INFERENCE_FAILED = "inference_failed"
    EMBEDDING_FAILED = "embedding_failed"
    UPLOAD_FAILED = "upload_failed"
    PROCESSING_FAILED = "processing_failed"
    
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    
    INTERNAL_ERROR = "internal_error"
    SERVICE_UNAVAILABLE = "service_unavailable"


ERROR_MESSAGES: Dict[str, str] = {
    ErrorCode.MODEL_NOT_FOUND: "模型不存在，请检查模型名称或先下载模�?,
    ErrorCode.MODEL_LOAD_FAILED: "模型加载失败，请检查模型文件是否完�?,
    ErrorCode.SESSION_NOT_FOUND: "会话不存�?,
    ErrorCode.COLLECTION_NOT_FOUND: "知识库集合不存在",
    ErrorCode.DOCUMENT_NOT_FOUND: "文档不存�?,
    ErrorCode.MEMORY_NOT_FOUND: "记忆不存�?,
    ErrorCode.ENTITY_NOT_FOUND: "实体不存�?,
    
    ErrorCode.OLLAMA_NOT_RUNNING: "Ollama 服务未运行，请先启动 Ollama",
    ErrorCode.OLLAMA_UNAVAILABLE: "Ollama 服务暂时不可用，请稍后重�?,
    
    ErrorCode.CONTEXT_TOO_LONG: "上下文长度超出限制，请减少对话历�?,
    ErrorCode.MALICIOUS_INPUT: "检测到潜在的恶意输入，请修改内容后重试",
    ErrorCode.INVALID_INPUT: "输入内容无效，请检查后重试",
    ErrorCode.RATE_LIMITED: "请求过于频繁，请稍后重试",
    
    ErrorCode.INFERENCE_FAILED: "推理生成失败，请稍后重试",
    ErrorCode.EMBEDDING_FAILED: "文本嵌入失败",
    ErrorCode.UPLOAD_FAILED: "文件上传失败",
    ErrorCode.PROCESSING_FAILED: "处理失败",
    
    ErrorCode.UNAUTHORIZED: "未授权访�?,
    ErrorCode.FORBIDDEN: "禁止访问",
    
    ErrorCode.INTERNAL_ERROR: "服务器内部错�?,
    ErrorCode.SERVICE_UNAVAILABLE: "服务暂时不可�?,
}


class APIError(Exception):
    """API 错误基类"""
    
    def __init__(
        self,
        code: str,
        message: Optional[str] = None,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None
    ):
        self.code = code if isinstance(code, str) else code.value
        self.message = message or ERROR_MESSAGES.get(self.code, f"操作失败: {self.code}")
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details
            }
        }
    
    def to_http_exception(self) -> HTTPException:
        return HTTPException(
            status_code=self.status_code,
            detail=self.to_dict()
        )


class ModelNotFoundError(APIError):
    def __init__(self, model_id: str, message: Optional[str] = None):
        super().__init__(
            code=ErrorCode.MODEL_NOT_FOUND,
            message=message,
            status_code=404,
            details={"model_id": model_id}
        )


class ModelLoadFailedError(APIError):
    def __init__(self, model_id: str, reason: Optional[str] = None):
        super().__init__(
            code=ErrorCode.MODEL_LOAD_FAILED,
            status_code=500,
            details={"model_id": model_id, "reason": reason}
        )


class SessionNotFoundError(APIError):
    def __init__(self, session_id: str):
        super().__init__(
            code=ErrorCode.SESSION_NOT_FOUND,
            status_code=404,
            details={"session_id": session_id}
        )


class CollectionNotFoundError(APIError):
    def __init__(self, collection_id: str):
        super().__init__(
            code=ErrorCode.COLLECTION_NOT_FOUND,
            status_code=404,
            details={"collection_id": collection_id}
        )


class DocumentNotFoundError(APIError):
    def __init__(self, document_id: str):
        super().__init__(
            code=ErrorCode.DOCUMENT_NOT_FOUND,
            status_code=404,
            details={"document_id": document_id}
        )


class MemoryNotFoundError(APIError):
    def __init__(self, memory_id: str):
        super().__init__(
            code=ErrorCode.MEMORY_NOT_FOUND,
            status_code=404,
            details={"memory_id": memory_id}
        )


class EntityNotFoundError(APIError):
    def __init__(self, entity_id: str):
        super().__init__(
            code=ErrorCode.ENTITY_NOT_FOUND,
            status_code=404,
            details={"entity_id": entity_id}
        )


class OllamaNotRunningError(APIError):
    def __init__(self):
        super().__init__(
            code=ErrorCode.OLLAMA_NOT_RUNNING,
            status_code=503
        )


class OllamaUnavailableError(APIError):
    def __init__(self, reason: Optional[str] = None):
        super().__init__(
            code=ErrorCode.OLLAMA_UNAVAILABLE,
            status_code=503,
            details={"reason": reason}
        )


class ContextTooLongError(APIError):
    def __init__(self, current: int, max_length: int):
        super().__init__(
            code=ErrorCode.CONTEXT_TOO_LONG,
            message=f"上下文长度超出限制（当前: {current}, 最�? {max_length}�?,
            status_code=400,
            details={"current": current, "max_length": max_length}
        )


class MaliciousInputError(APIError):
    def __init__(self, pattern: Optional[str] = None):
        super().__init__(
            code=ErrorCode.MALICIOUS_INPUT,
            status_code=400,
            details={"detected_pattern": pattern} if pattern else {}
        )


class InvalidInputError(APIError):
    def __init__(self, field: str, reason: str):
        super().__init__(
            code=ErrorCode.INVALID_INPUT,
            message=f"输入无效: {field} - {reason}",
            status_code=400,
            details={"field": field, "reason": reason}
        )


class RateLimitedError(APIError):
    def __init__(self, retry_after: Optional[int] = None):
        super().__init__(
            code=ErrorCode.RATE_LIMITED,
            status_code=429,
            details={"retry_after": retry_after} if retry_after else {}
        )


class InferenceFailedError(APIError):
    def __init__(self, model_id: str, reason: Optional[str] = None):
        super().__init__(
            code=ErrorCode.INFERENCE_FAILED,
            status_code=500,
            details={"model_id": model_id, "reason": reason}
        )


class EmbeddingFailedError(APIError):
    def __init__(self, text_preview: str, reason: Optional[str] = None):
        super().__init__(
            code=ErrorCode.EMBEDDING_FAILED,
            status_code=500,
            details={"text_preview": text_preview[:100], "reason": reason}
        )


class UploadFailedError(APIError):
    def __init__(self, filename: str, reason: Optional[str] = None):
        super().__init__(
            code=ErrorCode.UPLOAD_FAILED,
            status_code=400,
            details={"filename": filename, "reason": reason}
        )


class ProcessingFailedError(APIError):
    def __init__(self, operation: str, reason: Optional[str] = None):
        super().__init__(
            code=ErrorCode.PROCESSING_FAILED,
            status_code=500,
            details={"operation": operation, "reason": reason}
        )


class UnauthorizedError(APIError):
    def __init__(self, message: Optional[str] = None):
        super().__init__(
            code=ErrorCode.UNAUTHORIZED,
            message=message or "未授权访�?,
            status_code=401
        )


class ForbiddenError(APIError):
    def __init__(self, message: Optional[str] = None):
        super().__init__(
            code=ErrorCode.FORBIDDEN,
            message=message or "禁止访问",
            status_code=403
        )


class InternalError(APIError):
    def __init__(self, reason: Optional[str] = None):
        super().__init__(
            code=ErrorCode.INTERNAL_ERROR,
            status_code=500,
            details={"reason": reason}
        )


class ServiceUnavailableError(APIError):
    def __init__(self, service: str, reason: Optional[str] = None):
        super().__init__(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            status_code=503,
            details={"service": service, "reason": reason}
        )


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """API 错误处理�?""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict()
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """HTTP 异常处理�?- 统一格式"""
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail
        )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "http_error",
                "message": str(exc.detail),
                "details": {}
            }
        }
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """通用异常处理�?""
    import logging
    logging.getLogger(__name__).error(f"未处理的异常: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": ErrorCode.INTERNAL_ERROR,
                "message": "服务器内部错�?,
                "details": {"type": type(exc).__name__}
            }
        }
    )


def parse_ollama_error(error_text: str) -> APIError:
    """解析 Ollama 错误信息并返回对应的 APIError"""
    error_lower = error_text.lower()
    
    if "model" in error_lower and ("not found" in error_lower or "does not exist" in error_lower):
        return ModelNotFoundError(model_id="unknown")
    if "connection" in error_lower or "refused" in error_lower:
        return OllamaNotRunningError()
    if "timeout" in error_lower:
        return OllamaUnavailableError(reason="timeout")
    if "context" in error_lower and ("length" in error_lower or "too long" in error_lower):
        return ContextTooLongError(current=0, max_length=0)
    
    return OllamaUnavailableError(reason=error_text)


def get_friendly_error(code: str, original_error: str = "") -> str:
    """获取友好的错误信�?""
    friendly_msg = ERROR_MESSAGES.get(code, f"操作失败: {code}")
    import logging
    if original_error and logging.getLogger(__name__).isEnabledFor(10):
        return f"{friendly_msg}（详情：{original_error}�?
    return friendly_msg
