"""Unified executor entrypoint for agent operations."""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .engine.queue_manager import QueueManager, TaskInfo, TaskPriority
from .engine.resource_limiter import ResourceConfig, ResourceLimiter
from .engine.sandbox_executor import SandboxConfig, SandboxExecutor, SandboxLevel
from .interfaces import AgentException, ErrorCode, OperationContext, UnifiedResult

logger = logging.getLogger(__name__)


@dataclass
class ExecutorConfig:
    workspace: str = "."
    timeout: int = 300
    max_concurrent_tasks: int = 5
    default_timeout: float = 60.0
    max_retries: int = 3
    sandbox_level: SandboxLevel = SandboxLevel.STANDARD
    enable_safety_check: bool = True
    enable_audit_log: bool = False
    allowed_extensions: list[str] | None = None
    max_file_size: int = 100 * 1024 * 1024
    allowed_commands: list[str] | None = None


class OperationHandler:
    def __init__(self, context: OperationContext | None = None):
        self.context = context

    async def execute(self, action: str, params: dict[str, Any]) -> UnifiedResult:
        raise NotImplementedError

    def get_supported_actions(self) -> list[str]:
        return []

    def set_context(self, context: OperationContext) -> None:
        self.context = context


class CompositeOperationHandler(OperationHandler):
    def __init__(self, handlers: list[OperationHandler], context: OperationContext | None = None):
        super().__init__(context)
        self._handlers: list[OperationHandler] = []
        self._action_map: dict[str, OperationHandler] = {}
        for handler in handlers:
            self.add_handler(handler)

    def add_handler(self, handler: OperationHandler) -> None:
        self._handlers.append(handler)
        for action in handler.get_supported_actions():
            self._action_map[action] = handler

    def remove_handler(self, handler: OperationHandler) -> None:
        if handler not in self._handlers:
            return
        self._handlers.remove(handler)
        for action in handler.get_supported_actions():
            if self._action_map.get(action) is handler:
                del self._action_map[action]

    async def execute(self, action: str, params: dict[str, Any]) -> UnifiedResult:
        handler = self._action_map.get(action)
        if not handler:
            return UnifiedResult.fail(
                action=action,
                error=f"Handler not found: {action}",
                error_code=ErrorCode.HANDLER_NOT_FOUND,
            )

        if self.context:
            handler.set_context(self.context)
        return await handler.execute(action, params)

    async def run(self, action: str, params: dict[str, Any]) -> UnifiedResult:
        if action not in self._action_map:
            return UnifiedResult.fail(
                action=action,
                error=f"Unsupported action: {action}",
                error_code="UNSUPPORTED_ACTION",
            )
        return await self.execute(action, params)

    def get_supported_actions(self) -> list[str]:
        return list(self._action_map.keys())

    def get_handler_for_action(self, action: str) -> OperationHandler | None:
        return self._action_map.get(action)


class UnifiedExecutor:
    def __init__(self, config: ExecutorConfig | None = None, handlers: list[OperationHandler] | None = None):
        self.config = config or ExecutorConfig()
        self._context = OperationContext(workspace=self.config.workspace, timeout=self.config.timeout)
        self._composite_handler = CompositeOperationHandler(handlers=handlers or [], context=self._context)

        self._initialized = False
        self._execution_count = 0
        self._action_handlers: dict[str, Callable] = {}
        self._execution_log: list[dict[str, Any]] = []
        self._log_lock = asyncio.Lock()

        sandbox_config = SandboxConfig(
            level=self.config.sandbox_level,
            max_execution_time_seconds=int(self.config.default_timeout),
        )
        resource_config = ResourceConfig(
            max_execution_time_seconds=int(self.config.default_timeout),
            max_concurrent_tasks=self.config.max_concurrent_tasks,
        )

        self.resource_limiter = ResourceLimiter(resource_config)
        self.sandbox_executor = SandboxExecutor(sandbox_config, self.resource_limiter)
        self.queue_manager = QueueManager(
            max_concurrent=self.config.max_concurrent_tasks,
            default_timeout=self.config.default_timeout,
            default_max_retries=self.config.max_retries,
        )

    async def initialize(self) -> None:
        if self._initialized:
            return
        await self.sandbox_executor.initialize()
        await self.resource_limiter.start_monitoring()
        self.queue_manager.set_executor(self._execute_action)
        await self.queue_manager.start()
        self._initialized = True

    async def shutdown(self) -> None:
        if not self._initialized:
            return
        await self.queue_manager.stop()
        await self.sandbox_executor.cleanup()
        await self.resource_limiter.stop_monitoring()
        self._initialized = False

    def register_handler(self, handler: OperationHandler) -> None:
        handler.set_context(self._context)
        self._composite_handler.add_handler(handler)

    def register_action_handler(self, action: str, handler: Callable) -> None:
        self._action_handlers[action] = handler

    def unregister_action_handler(self, action: str) -> None:
        self._action_handlers.pop(action, None)

    def get_supported_actions(self) -> list[str]:
        return list(set(self._composite_handler.get_supported_actions() + list(self._action_handlers.keys())))

    async def execute(self, action: str, params: dict[str, Any]) -> UnifiedResult:
        if not self._initialized:
            await self.initialize()

        self._execution_count += 1
        started = time.time()

        try:
            if action in self._action_handlers:
                result = await self._action_handlers[action](action, params)
            else:
                result = await self._composite_handler.execute(action, params)

            result.action = action
            result.duration_ms = (time.time() - started) * 1000
            if self.config.enable_audit_log:
                await self._log_execution(action, params, result)
            return result

        except AgentException as e:
            return UnifiedResult.fail(action=action, error=e.message, error_code=ErrorCode.EXECUTION_ERROR, data=e.details)
        except Exception as e:
            logger.exception("Execution failed for %s", action)
            return UnifiedResult.fail(action=action, error=str(e), error_code=ErrorCode.INTERNAL_ERROR)

    async def _execute_action(self, action: str, params: dict[str, Any]) -> UnifiedResult:
        return await self.execute(action, params)

    async def _log_execution(self, action: str, params: dict[str, Any], result: UnifiedResult) -> None:
        async with self._log_lock:
            self._execution_log.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "action": action,
                    "params": params,
                    "success": result.success,
                    "error": result.error,
                    "duration_ms": result.duration_ms,
                }
            )
            if len(self._execution_log) > 1000:
                self._execution_log = self._execution_log[-500:]

    async def execute_batch(self, operations: list[dict[str, Any]]) -> list[UnifiedResult]:
        results: list[UnifiedResult] = []
        for op in operations:
            action = op.get("action")
            params = op.get("params", {})
            if not action:
                results.append(UnifiedResult.fail(error="Missing action", error_code=ErrorCode.VALIDATION_ERROR))
                continue
            results.append(await self.execute(action, params))
        return results

    async def execute_queued(
        self,
        action: str,
        params: dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not self._initialized:
            await self.initialize()
        return await self.queue_manager.enqueue(action=action, params=params, priority=priority, metadata=metadata)

    async def get_task_status(self, task_id: str) -> TaskInfo | None:
        return await self.queue_manager.get_task_status(task_id)

    async def get_task_result(self, task_id: str) -> dict[str, Any] | None:
        return await self.queue_manager.get_task_result(task_id)

    async def cancel_task(self, task_id: str) -> bool:
        return await self.queue_manager.cancel_task(task_id)

    async def wait_for_task(self, task_id: str, timeout: float | None = None) -> TaskInfo | None:
        return await self.queue_manager.wait_for_task(task_id, timeout)

    def get_execution_log(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._execution_log[-limit:]

    def get_stats(self) -> dict[str, Any]:
        return {
            "initialized": self._initialized,
            "execution_count": self._execution_count,
            "supported_actions_count": len(self.get_supported_actions()),
            "handlers_count": len(self._composite_handler._handlers),
            "queue": self.queue_manager.get_stats(),
            "resources": self.resource_limiter.get_stats(),
        }


_executor_instance: UnifiedExecutor | None = None


def get_executor() -> UnifiedExecutor:
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = create_executor()
    return _executor_instance


def create_executor(
    workspace: str = ".",
    enable_safety_check: bool = True,
    enable_audit_log: bool = False,
    **kwargs,
) -> UnifiedExecutor:
    config = ExecutorConfig(
        workspace=workspace,
        enable_safety_check=enable_safety_check,
        enable_audit_log=enable_audit_log,
        **kwargs,
    )
    executor = UnifiedExecutor(config=config)

    try:
        from agent.operations.cua.handler import CUAOperationHandler
        from agent.operations.file.handler import FileOperationHandler
        from agent.operations.system_operations import SystemOperationHandler

        executor.register_handler(FileOperationHandler(context=executor._context))
        executor.register_handler(CUAOperationHandler())
        executor.register_handler(SystemOperationHandler())
    except Exception as e:
        logger.warning("Failed to auto-register operation handlers: %s", e)

    return executor


def reset_executor() -> UnifiedExecutor:
    global _executor_instance
    _executor_instance = None
    return get_executor()


AgentExecutor = UnifiedExecutor
AgentExecutorNew = UnifiedExecutor
