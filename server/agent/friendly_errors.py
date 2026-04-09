"""
友好错误信息模块
提供用户友好的错误消息和解决建议
"""
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ErrorCategory(str, Enum):
    """错误类别"""
    FILE_NOT_FOUND = "file_not_found"
    FILE_ACCESS_DENIED = "file_access_denied"
    FILE_TOO_LARGE = "file_too_large"
    FILE_ALREADY_EXISTS = "file_already_exists"
    INVALID_PATH = "invalid_path"
    UNSAFE_PATH = "unsafe_path"
    UNSAFE_OPERATION = "unsafe_operation"
    OPERATION_DENIED = "operation_denied"
    OPERATION_FAILED = "operation_failed"
    INVALID_INPUT = "invalid_input"
    MISSING_PARAMETER = "missing_parameter"
    TIMEOUT = "timeout"
    RESOURCE_BUSY = "resource_busy"
    PERMISSION_DENIED = "permission_denied"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class FriendlyError:
    """友好错误信息"""
    code: str
    category: ErrorCategory
    title: str
    message: str
    solutions: list[str]
    related_commands: list[str] = None

    def __post_init__(self):
        if self.related_commands is None:
            self.related_commands = []


ERROR_SOLUTIONS: dict[str, FriendlyError] = {
    "file_not_found": FriendlyError(
        code="FILE_001",
        category=ErrorCategory.FILE_NOT_FOUND,
        title="文件不存在",
        message="找不到您指定的文件",
        solutions=[
            "请检查文件名是否正确，注意大小写",
            "请确认文件路径是否正确",
            "您可以使用'列出当前目录'查看可用文件",
            "如果是新文件，请使用'创建文件'命令"
        ],
        related_commands=["列出当前目录", "创建文件"]
    ),

    "file_access_denied": FriendlyError(
        code="FILE_002",
        category=ErrorCategory.FILE_ACCESS_DENIED,
        title="无法访问文件",
        message="没有权限访问该文件或文件被占用",
        solutions=[
            "请检查文件是否被其他程序打开",
            "请确认您有读取该文件的权限",
            "尝试关闭可能占用该文件的应用程序"
        ]
    ),

    "file_too_large": FriendlyError(
        code="FILE_003",
        category=ErrorCategory.FILE_TOO_LARGE,
        title="文件过大",
        message="文件大小超过限制，无法处理",
        solutions=[
            "当前文件大小限制为 10MB",
            "请尝试处理较小的文件",
            "如果是文本文件，可以分段读取"
        ]
    ),

    "file_already_exists": FriendlyError(
        code="FILE_004",
        category=ErrorCategory.FILE_ALREADY_EXISTS,
        title="文件已存在",
        message="指定位置已有同名文件",
        solutions=[
            "请使用不同的文件名",
            "如需覆盖，请先删除原文件",
            "您可以使用'读取文件'查看现有文件内容"
        ],
        related_commands=["删除文件", "读取文件"]
    ),

    "invalid_path": FriendlyError(
        code="PATH_001",
        category=ErrorCategory.INVALID_PATH,
        title="路径无效",
        message="指定的路径格式不正确",
        solutions=[
            "请检查路径格式是否正确",
            "Windows 路径示例: C:\\Users\\用户名\\Desktop\\file.txt",
            "相对路径示例: ./folder/file.txt 或 folder/file.txt"
        ]
    ),

    "unsafe_path": FriendlyError(
        code="SAFE_001",
        category=ErrorCategory.UNSAFE_PATH,
        title="安全限制",
        message="出于安全考虑，无法访问该路径",
        solutions=[
            "仅允许访问以下位置：",
            "  - 桌面目录",
            "  - 文档目录",
            "  - 下载目录",
            "  - 当前工作目录",
            "请将文件移动到以上位置后再操作"
        ]
    ),

    "unsafe_operation": FriendlyError(
        code="SAFE_002",
        category=ErrorCategory.UNSAFE_OPERATION,
        title="操作需要确认",
        message="此操作可能影响系统或数据安全",
        solutions=[
            "请在确认后重新执行",
            "确认操作详情后再继续",
            "如不需要，可以取消操作"
        ]
    ),

    "operation_denied": FriendlyError(
        code="SAFE_003",
        category=ErrorCategory.OPERATION_DENIED,
        title="操作被禁止",
        message="该操作被安全策略禁止",
        solutions=[
            "此操作类型已被系统禁止执行",
            "请联系管理员了解详情",
            "您可以使用其他替代操作"
        ]
    ),

    "operation_failed": FriendlyError(
        code="OP_001",
        category=ErrorCategory.OPERATION_FAILED,
        title="操作失败",
        message="执行操作时发生错误",
        solutions=[
            "请稍后重试",
            "检查输入参数是否正确",
            "如果问题持续，请联系技术支持"
        ]
    ),

    "invalid_input": FriendlyError(
        code="INPUT_001",
        category=ErrorCategory.INVALID_INPUT,
        title="输入无效",
        message="提供的输入参数不正确",
        solutions=[
            "请检查输入格式是否正确",
            "参考示例格式重新输入",
            "使用'帮助'命令查看正确用法"
        ]
    ),

    "missing_parameter": FriendlyError(
        code="INPUT_002",
        category=ErrorCategory.MISSING_PARAMETER,
        title="缺少参数",
        message="操作缺少必要的参数",
        solutions=[
            "请提供完整的操作参数",
            "参考示例格式重新输入",
            "例如: '读取 test.txt' 而不是 '读取'"
        ]
    ),

    "timeout": FriendlyError(
        code="TIME_001",
        category=ErrorCategory.TIMEOUT,
        title="操作超时",
        message="操作执行时间过长",
        solutions=[
            "请稍后重试",
            "可能是系统资源紧张，请关闭其他程序",
            "如果是大文件操作，请耐心等待"
        ]
    ),

    "resource_busy": FriendlyError(
        code="RES_001",
        category=ErrorCategory.RESOURCE_BUSY,
        title="资源占用",
        message="所需资源正被其他进程使用",
        solutions=[
            "请稍后重试",
            "关闭可能占用资源的应用程序",
            "检查是否有重复的操作请求"
        ]
    ),

    "permission_denied": FriendlyError(
        code="PERM_001",
        category=ErrorCategory.PERMISSION_DENIED,
        title="权限不足",
        message="当前权限无法执行此操作",
        solutions=[
            "请联系管理员获取相应权限",
            "确认您的账户有执行此操作的权限",
            "尝试使用其他操作方式"
        ]
    ),

    "unknown_error": FriendlyError(
        code="UNK_001",
        category=ErrorCategory.UNKNOWN_ERROR,
        title="未知错误",
        message="发生未知错误",
        solutions=[
            "请稍后重试",
            "如果问题持续，请联系技术支持",
            "提供错误详情以便排查问题"
        ]
    ),
}


def get_friendly_error(error_key: str, context: dict[str, Any] = None) -> FriendlyError:
    """
    获取友好错误信息

    Args:
        error_key: 错误键
        context: 上下文信息

    Returns:
        FriendlyError: 友好错误信息
    """
    context = context or {}

    error = ERROR_SOLUTIONS.get(error_key, ERROR_SOLUTIONS["unknown_error"])

    return error


def format_error_message(error_key: str, details: str = None, context: dict[str, Any] = None) -> str:
    """
    格式化错误消息

    Args:
        error_key: 错误键
        details: 详细信息
        context: 上下文信息

    Returns:
        str: 格式化后的错误消息
    """
    error = get_friendly_error(error_key, context)

    lines = [f"❌ {error.title}", "", error.message]

    if details:
        lines.append("")
        lines.append(f"详情: {details}")

    if error.solutions:
        lines.append("")
        lines.append("💡 建议:")
        for i, solution in enumerate(error.solutions, 1):
            lines.append(f"  {i}. {solution}")

    if error.related_commands:
        lines.append("")
        lines.append("📌 相关命令: " + " | ".join(error.related_commands))

    return "\n".join(lines)


def categorize_error(error_message: str) -> str:
    """
    根据错误消息自动分类

    Args:
        error_message: 原始错误消息

    Returns:
        str: 错误键
    """
    error_lower = error_message.lower()

    if "not found" in error_lower or "不存在" in error_lower or "no such file" in error_lower:
        return "file_not_found"
    if "permission" in error_lower or "权限" in error_lower or "access denied" in error_lower:
        return "file_access_denied"
    if "too large" in error_lower or "过大" in error_lower:
        return "file_too_large"
    if "already exists" in error_lower or "已存在" in error_lower:
        return "file_already_exists"
    if "invalid path" in error_lower or "路径无效" in error_lower:
        return "invalid_path"
    if "unsafe" in error_lower or "安全" in error_lower or "not in safe" in error_lower:
        return "unsafe_path"
    if "timeout" in error_lower or "超时" in error_lower:
        return "timeout"
    if "busy" in error_lower or "占用" in error_lower:
        return "resource_busy"
    if "denied" in error_lower or "禁止" in error_lower:
        return "operation_denied"

    return "unknown_error"


def create_error_response(
    error_key: str,
    details: str = None,
    context: dict[str, Any] = None,
    include_suggestions: bool = True
) -> dict[str, Any]:
    """
    创建错误响应

    Args:
        error_key: 错误键
        details: 详细信息
        context: 上下文信息
        include_suggestions: 是否包含建议

    Returns:
        Dict: 错误响应
    """
    error = get_friendly_error(error_key, context)

    response = {
        "success": False,
        "error": {
            "code": error.code,
            "category": error.category.value,
            "title": error.title,
            "message": error.message,
        }
    }

    if details:
        response["error"]["details"] = details

    if include_suggestions and error.solutions:
        response["suggestions"] = error.solutions

    if error.related_commands:
        response["related_commands"] = error.related_commands

    return response
