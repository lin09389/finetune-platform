"""
错误处理和提示模板
功能：
- 统一错误格式
- 友好错误消息
- 错误代码映射
- 错误恢复建议
"""
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from fastapi import HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ErrorCode(str, Enum):
    """错误代码"""
    UNKNOWN_ERROR = "E0000"
    INVALID_REQUEST = "E0001"
    RESOURCE_NOT_FOUND = "E0002"
    PERMISSION_DENIED = "E0003"
    RATE_LIMITED = "E0004"
    
    MODEL_NOT_FOUND = "E1001"
    MODEL_LOAD_FAILED = "E1002"
    MODEL_DOWNLOAD_FAILED = "E1003"
    MODEL_ALREADY_EXISTS = "E1004"
    MODEL_FORMAT_UNSUPPORTED = "E1005"
    
    TRAINING_NOT_FOUND = "E2001"
    TRAINING_ALREADY_RUNNING = "E2002"
    TRAINING_FAILED = "E2003"
    TRAINING_QUEUE_FULL = "E2004"
    DATASET_NOT_FOUND = "E2005"
    DATASET_INVALID = "E2006"
    
    INFERENCE_FAILED = "E3001"
    CONTEXT_TOO_LONG = "E3002"
    GENERATION_TIMEOUT = "E3003"
    
    CUDA_NOT_AVAILABLE = "E4001"
    CUDA_OUT_OF_MEMORY = "E4002"
    CUDA_DRIVER_ERROR = "E4003"
    
    CONFIG_INVALID = "E5001"
    CONFIG_MISSING = "E5002"
    ENV_VAR_MISSING = "E5003"
    
    FILE_NOT_FOUND = "E6001"
    FILE_TOO_LARGE = "E6002"
    FILE_TYPE_INVALID = "E6003"
    FILE_UPLOAD_FAILED = "E6004"


@dataclass
class ErrorDetail:
    """错误详情"""
    code: ErrorCode
    message: str
    detail: str = ""
    suggestions: List[str] = field(default_factory=list)
    documentation_url: Optional[str] = None
    recoverable: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "detail": self.detail,
            "suggestions": self.suggestions,
            "documentation_url": self.documentation_url,
            "recoverable": self.recoverable,
        }


ERROR_MAPPINGS: Dict[ErrorCode, ErrorDetail] = {
    ErrorCode.UNKNOWN_ERROR: ErrorDetail(
        code=ErrorCode.UNKNOWN_ERROR,
        message="发生未知错误",
        detail="服务器遇到了一个未预期的错误",
        suggestions=[
            "请稍后重试",
            "如果问题持续存在，请联系技术支持",
        ],
        recoverable=True,
    ),
    ErrorCode.INVALID_REQUEST: ErrorDetail(
        code=ErrorCode.INVALID_REQUEST,
        message="请求参数无效",
        detail="请求的参数格式或值不正确",
        suggestions=[
            "检查请求参数格式是否正确",
            "参考 API 文档确认参数要求",
        ],
        documentation_url="/docs",
        recoverable=True,
    ),
    ErrorCode.RESOURCE_NOT_FOUND: ErrorDetail(
        code=ErrorCode.RESOURCE_NOT_FOUND,
        message="资源不存在",
        detail="请求的资源未找到",
        suggestions=[
            "检查资源 ID 是否正确",
            "确认资源是否已被删除",
        ],
        recoverable=True,
    ),
    ErrorCode.PERMISSION_DENIED: ErrorDetail(
        code=ErrorCode.PERMISSION_DENIED,
        message="权限不足",
        detail="您没有权限执行此操作",
        suggestions=[
            "检查您的账户权限",
            "联系管理员获取必要权限",
        ],
        recoverable=False,
    ),
    ErrorCode.RATE_LIMITED: ErrorDetail(
        code=ErrorCode.RATE_LIMITED,
        message="请求过于频繁",
        detail="您已超过请求频率限制",
        suggestions=[
            "等待一段时间后重试",
            "减少请求频率",
        ],
        recoverable=True,
    ),
    ErrorCode.MODEL_NOT_FOUND: ErrorDetail(
        code=ErrorCode.MODEL_NOT_FOUND,
        message="模型不存在",
        detail="指定的模型未找到",
        suggestions=[
            "检查模型名称或 ID 是否正确",
            "使用 /models 端点查看可用模型",
            "如果模型未下载，请先下载模型",
        ],
        documentation_url="/docs#/models",
        recoverable=True,
    ),
    ErrorCode.MODEL_LOAD_FAILED: ErrorDetail(
        code=ErrorCode.MODEL_LOAD_FAILED,
        message="模型加载失败",
        detail="无法加载指定的模型",
        suggestions=[
            "检查模型文件是否完整",
            "确认有足够的 GPU 内存",
            "尝试使用量化版本减少内存占用",
            "检查模型格式是否受支持",
        ],
        recoverable=True,
    ),
    ErrorCode.MODEL_DOWNLOAD_FAILED: ErrorDetail(
        code=ErrorCode.MODEL_DOWNLOAD_FAILED,
        message="模型下载失败",
        detail="无法下载指定的模型",
        suggestions=[
            "检查网络连接",
            "确认 HuggingFace 镜像配置正确",
            "检查代理设置",
            "确认磁盘空间充足",
        ],
        recoverable=True,
    ),
    ErrorCode.CUDA_OUT_OF_MEMORY: ErrorDetail(
        code=ErrorCode.CUDA_OUT_OF_MEMORY,
        message="GPU 内存不足",
        detail="显存不足以完成操作",
        suggestions=[
            "减少批处理大小 (batch_size)",
            "启用梯度检查点 (gradient_checkpointing)",
            "使用量化模型 (int4/int8)",
            "减少最大序列长度 (max_length)",
            "关闭其他 GPU 应用程序",
        ],
        recoverable=True,
    ),
    ErrorCode.CUDA_NOT_AVAILABLE: ErrorDetail(
        code=ErrorCode.CUDA_NOT_AVAILABLE,
        message="CUDA 不可用",
        detail="未检测到可用的 CUDA 设备",
        suggestions=[
            "确认已安装 NVIDIA GPU 驱动",
            "检查 CUDA 工具包是否正确安装",
            "使用 CPU 模式运行（性能较低）",
        ],
        recoverable=False,
    ),
    ErrorCode.TRAINING_NOT_FOUND: ErrorDetail(
        code=ErrorCode.TRAINING_NOT_FOUND,
        message="训练任务不存在",
        detail="指定的训练任务未找到",
        suggestions=[
            "检查任务 ID 是否正确",
            "使用 /training/history 查看历史任务",
        ],
        recoverable=True,
    ),
    ErrorCode.TRAINING_ALREADY_RUNNING: ErrorDetail(
        code=ErrorCode.TRAINING_ALREADY_RUNNING,
        message="已有训练任务运行中",
        detail="同一时间只能运行一个训练任务",
        suggestions=[
            "等待当前训练完成",
            "停止当前训练后重新开始",
            "使用 /training/status 查看当前状态",
        ],
        recoverable=True,
    ),
    ErrorCode.DATASET_NOT_FOUND: ErrorDetail(
        code=ErrorCode.DATASET_NOT_FOUND,
        message="数据集不存在",
        detail="指定的数据集未找到",
        suggestions=[
            "检查数据集 ID 是否正确",
            "使用 /datasets 端点查看可用数据集",
            "上传数据集后再试",
        ],
        recoverable=True,
    ),
    ErrorCode.DATASET_INVALID: ErrorDetail(
        code=ErrorCode.DATASET_INVALID,
        message="数据集格式无效",
        detail="数据集格式不符合要求",
        suggestions=[
            "确认数据集为 JSONL 格式",
            "每行应包含 'input' 和 'output' 字段",
            "检查文件编码是否为 UTF-8",
        ],
        documentation_url="/docs#/datasets",
        recoverable=True,
    ),
    ErrorCode.INFERENCE_FAILED: ErrorDetail(
        code=ErrorCode.INFERENCE_FAILED,
        message="推理失败",
        detail="模型推理过程中发生错误",
        suggestions=[
            "检查输入内容是否有效",
            "减少输入长度",
            "检查模型是否正确加载",
        ],
        recoverable=True,
    ),
    ErrorCode.CONTEXT_TOO_LONG: ErrorDetail(
        code=ErrorCode.CONTEXT_TOO_LONG,
        message="上下文过长",
        detail="输入超过了模型的最大长度限制",
        suggestions=[
            "减少输入文本长度",
            "清除部分对话历史",
            "使用支持更长上下文的模型",
        ],
        recoverable=True,
    ),
    ErrorCode.FILE_TOO_LARGE: ErrorDetail(
        code=ErrorCode.FILE_TOO_LARGE,
        message="文件过大",
        detail="上传的文件超过了大小限制",
        suggestions=[
            "压缩文件后重试",
            "分割文件为多个小文件",
            "联系管理员调整上传限制",
        ],
        recoverable=True,
    ),
    ErrorCode.FILE_TYPE_INVALID: ErrorDetail(
        code=ErrorCode.FILE_TYPE_INVALID,
        message="文件类型无效",
        detail="上传的文件类型不支持",
        suggestions=[
            "检查文件扩展名",
            "确认支持的文件类型",
        ],
        recoverable=True,
    ),
    ErrorCode.CONFIG_INVALID: ErrorDetail(
        code=ErrorCode.CONFIG_INVALID,
        message="配置无效",
        detail="配置参数值不正确",
        suggestions=[
            "检查配置文件格式",
            "确认所有必需参数已设置",
            "参考文档确认参数范围",
        ],
        recoverable=True,
    ),
}


class AppException(Exception):
    """应用异常"""
    
    def __init__(
        self,
        code: ErrorCode,
        detail: str = "",
        suggestions: Optional[List[str]] = None,
    ):
        self.code = code
        self.detail = detail
        self.suggestions = suggestions or []
        
        error_info = ERROR_MAPPINGS.get(code)
        if error_info:
            self.message = error_info.message
            if not self.detail:
                self.detail = error_info.detail
            if not self.suggestions:
                self.suggestions = error_info.suggestions
        else:
            self.message = "发生错误"
    
    def to_response(self) -> Dict[str, Any]:
        """转换为响应格式"""
        error_info = ERROR_MAPPINGS.get(self.code, ERROR_MAPPINGS[ErrorCode.UNKNOWN_ERROR])
        
        response = error_info.to_dict()
        
        if self.detail:
            response["detail"] = self.detail
        
        if self.suggestions:
            response["suggestions"] = self.suggestions
        
        return {
            "success": False,
            "error": response,
        }


def create_error_response(
    code: ErrorCode,
    detail: str = "",
    suggestions: Optional[List[str]] = None,
) -> JSONResponse:
    """创建错误响应"""
    exc = AppException(code, detail, suggestions)
    
    status_code = 400
    if code in [ErrorCode.RESOURCE_NOT_FOUND, ErrorCode.MODEL_NOT_FOUND, 
                ErrorCode.TRAINING_NOT_FOUND, ErrorCode.DATASET_NOT_FOUND,
                ErrorCode.FILE_NOT_FOUND]:
        status_code = 404
    elif code in [ErrorCode.PERMISSION_DENIED]:
        status_code = 403
    elif code in [ErrorCode.RATE_LIMITED]:
        status_code = 429
    elif code in [ErrorCode.UNKNOWN_ERROR]:
        status_code = 500
    
    return JSONResponse(
        status_code=status_code,
        content=exc.to_response(),
    )


def handle_exception(e: Exception) -> JSONResponse:
    """处理异常并返回友好错误响应"""
    if isinstance(e, AppException):
        return create_error_response(e.code, e.detail, e.suggestions)
    
    if isinstance(e, HTTPException):
        return JSONResponse(
            status_code=e.status_code,
            content={
                "success": False,
                "error": {
                    "code": ErrorCode.UNKNOWN_ERROR.value,
                    "message": str(e.detail),
                    "recoverable": True,
                },
            },
        )
    
    logger.exception(f"未处理的异常: {e}")
    
    return create_error_response(
        ErrorCode.UNKNOWN_ERROR,
        detail=str(e),
        suggestions=[
            "请稍后重试",
            "如果问题持续存在，请查看服务器日志",
        ],
    )


def get_error_suggestion(error_type: str) -> List[str]:
    """获取错误建议"""
    suggestions_map = {
        "cuda": [
            "检查 GPU 驱动是否正确安装",
            "确认 CUDA 版本兼容",
            "尝试减少 GPU 内存使用",
        ],
        "memory": [
            "关闭其他应用程序释放内存",
            "减少批处理大小",
            "使用量化模型",
        ],
        "network": [
            "检查网络连接",
            "确认代理设置正确",
            "尝试使用镜像源",
        ],
        "file": [
            "检查文件路径是否正确",
            "确认文件权限",
            "检查磁盘空间",
        ],
        "model": [
            "确认模型已正确下载",
            "检查模型格式是否受支持",
            "尝试重新加载模型",
        ],
    }
    
    return suggestions_map.get(error_type, ["请参考文档或联系技术支持"])
