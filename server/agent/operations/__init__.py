"""
Agent 操作处理器模块
实现单一职责原则，将 AgentExecutor 拆分为独立的操作处理器
"""
from .base import OperationContext, OperationHandler, OperationResult
from .cua_operations import CUAOperationHandler
from .file_operations import FileOperationHandler
from .system_operations import SystemOperationHandler

__all__ = [
    "OperationHandler",
    "OperationResult",
    "OperationContext",
    "FileOperationHandler",
    "CUAOperationHandler",
    "SystemOperationHandler",
]
