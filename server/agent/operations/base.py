"""
操作处理器基类
定义统一的操作处理接口，实现单一职责原则
"""
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class OperationStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failed"
    FAILED = "failed"
    PARTIAL = "partial"
    PENDING = "pending"
    CANCELLED = "cancelled"


@dataclass
class OperationResult:
    """操作结果"""
    success: bool
    status: OperationStatus = OperationStatus.SUCCESS
    message: str = ""
    data: dict[str, Any] | None = None
    error: str | None = None
    error_code: str | None = None
    operation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, message: str = "操作成功", data: dict[str, Any] | None = None) -> 'OperationResult':
        """创建成功结果"""
        return cls(
            success=True,
            status=OperationStatus.SUCCESS,
            message=message,
            data=data,
        )

    @classmethod
    def fail(
        cls,
        error: str,
        error_code: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> 'OperationResult':
        """创建失败结果"""
        return cls(
            success=False,
            status=OperationStatus.FAILURE,
            error=error,
            error_code=error_code,
            data=data,
        )

    @classmethod
    def partial(
        cls,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> 'OperationResult':
        """创建部分成功结果"""
        return cls(
            success=True,
            status=OperationStatus.PARTIAL,
            message=message,
            data=data,
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "status": self.status.value,
            "message": self.message,
            "data": self.data,
            "error": self.error,
            "error_code": self.error_code,
            "operation_id": self.operation_id,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


@dataclass
class OperationContext:
    """操作上下文"""
    workspace: str
    user_id: str | None = None
    session_id: str | None = None
    permissions: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    timeout: int = 300
    dry_run: bool = False

    def has_permission(self, permission: str) -> bool:
        """检查是否有权限"""
        return permission in self.permissions or "*" in self.permissions

    def require_permission(self, permission: str) -> None:
        """要求权限，无权限则抛出异常"""
        if not self.has_permission(permission):
            raise PermissionError(f"缺少权限: {permission}")


class OperationHandler(ABC):
    """
    操作处理器抽象基类

    实现单一职责原则：每个处理器只负责一类操作
    实现开闭原则：通过继承扩展新的操作类型
    """

    def __init__(self, context: OperationContext | None = None):
        self.context = context
        self._logger = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")

    @abstractmethod
    async def execute(self, action: str, params: dict[str, Any]) -> OperationResult:
        """
        执行操作

        Args:
            action: 操作类型
            params: 操作参数

        Returns:
            操作结果
        """
        pass

    @abstractmethod
    def get_supported_actions(self) -> list[str]:
        """
        获取支持的操作类型列表

        Returns:
            操作类型列表
        """
        pass

    def supports(self, action: str) -> bool:
        """
        检查是否支持指定操作

        Args:
            action: 操作类型

        Returns:
            是否支持
        """
        return action in self.get_supported_actions()

    def validate_params(self, action: str, params: dict[str, Any]) -> str | None:
        """
        验证操作参数

        Args:
            action: 操作类型
            params: 操作参数

        Returns:
            错误信息，None 表示验证通过
        """
        return None

    def get_action_description(self, action: str) -> str:
        """
        获取操作描述

        Args:
            action: 操作类型

        Returns:
            操作描述
        """
        descriptions = self.get_action_descriptions()
        return descriptions.get(action, f"执行 {action} 操作")

    def get_action_descriptions(self) -> dict[str, str]:
        """
        获取所有操作的描述

        Returns:
            操作描述字典
        """
        return {}

    def set_context(self, context: OperationContext) -> None:
        """设置操作上下文"""
        self.context = context

    async def pre_execute(self, action: str, params: dict[str, Any]) -> OperationResult | None:
        """
        执行前钩子

        Args:
            action: 操作类型
            params: 操作参数

        Returns:
            如果返回非 None，则跳过实际执行
        """
        return None

    async def post_execute(
        self,
        action: str,
        params: dict[str, Any],
        result: OperationResult
    ) -> OperationResult:
        """
        执行后钩子

        Args:
            action: 操作类型
            params: 操作参数
            result: 执行结果

        Returns:
            处理后的结果
        """
        return result

    async def run(self, action: str, params: dict[str, Any]) -> OperationResult:
        """
        运行操作（模板方法）

        包含完整的执行流程：验证 -> 预处理 -> 执行 -> 后处理

        Args:
            action: 操作类型
            params: 操作参数

        Returns:
            操作结果
        """
        import time
        start_time = time.time()

        if not self.supports(action):
            return OperationResult.fail(
                error=f"不支持的操作: {action}",
                error_code="UNSUPPORTED_ACTION"
            )

        validation_error = self.validate_params(action, params)
        if validation_error:
            return OperationResult.fail(
                error=validation_error,
                error_code="INVALID_PARAMS"
            )

        pre_result = await self.pre_execute(action, params)
        if pre_result is not None:
            return pre_result

        try:
            result = await self.execute(action, params)
        except PermissionError as e:
            result = OperationResult.fail(
                error=str(e),
                error_code="PERMISSION_DENIED"
            )
        except Exception as e:
            self._logger.error(f"操作执行错误 [{action}]: {e}", exc_info=True)
            result = OperationResult.fail(
                error=str(e),
                error_code="EXECUTION_ERROR"
            )

        result = await self.post_execute(action, params, result)

        result.duration_ms = (time.time() - start_time) * 1000

        self._logger.debug(
            f"操作完成: {action} "
            f"(status={result.status.value}, duration={result.duration_ms:.2f}ms)"
        )

        return result


class CompositeOperationHandler(OperationHandler):
    """
    组合操作处理器

    将多个操作处理器组合在一起
    """

    def __init__(self, handlers: list[OperationHandler], context: OperationContext | None = None):
        super().__init__(context)
        self._handlers = handlers
        self._action_map: dict[str, OperationHandler] = {}

        for handler in handlers:
            for action in handler.get_supported_actions():
                self._action_map[action] = handler

    def add_handler(self, handler: OperationHandler) -> None:
        """添加处理器"""
        self._handlers.append(handler)
        for action in handler.get_supported_actions():
            self._action_map[action] = handler

    def remove_handler(self, handler: OperationHandler) -> None:
        """移除处理器"""
        if handler in self._handlers:
            self._handlers.remove(handler)
            for action in handler.get_supported_actions():
                if self._action_map.get(action) == handler:
                    del self._action_map[action]

    async def execute(self, action: str, params: dict[str, Any]) -> OperationResult:
        """执行操作"""
        handler = self._action_map.get(action)
        if handler:
            if self.context:
                handler.set_context(self.context)
            return await handler.run(action, params)

        return OperationResult.fail(
            error=f"未找到操作处理器: {action}",
            error_code="HANDLER_NOT_FOUND"
        )

    def get_supported_actions(self) -> list[str]:
        """获取所有支持的操作"""
        return list(self._action_map.keys())

    def get_handler_for_action(self, action: str) -> OperationHandler | None:
        """获取指定操作对应的处理器"""
        return self._action_map.get(action)
