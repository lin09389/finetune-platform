"""
向后兼容模块 - 此文件将在下一版本删除

请使用新的导入方式:
    from agent.core import UnifiedExecutor, ExecutionResult, get_executor
    from agent.core.executor import create_executor, ExecutorConfig
"""

from agent.core import (
    ExecutionResult,
    ExecutionStatus,
    OperationContext,
    OperationResult,
    UnifiedExecutor,
    get_executor,
)
from agent.core.executor import ExecutorConfig, create_executor

AgentExecutor = UnifiedExecutor

__all__ = [
    "AgentExecutor",
    "UnifiedExecutor",
    "ExecutionResult",
    "OperationResult",
    "OperationContext",
    "ExecutionStatus",
    "get_executor",
    "create_executor",
    "ExecutorConfig",
]
