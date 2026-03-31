import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from ..interfaces.base_executor import BaseExecutor
from ..types import ErrorCode, ExecutionResult, ExecutionStatus, ValidationResult
from .queue_manager import QueueManager, TaskInfo, TaskPriority, TaskStatus
from .resource_limiter import ResourceConfig, ResourceLimiter
from .sandbox_executor import SandboxConfig, SandboxExecutor, SandboxLevel

logger = logging.getLogger(__name__)


PARAM_ALIASES = {
    "file_path": ["path", "filepath", "file"],
    "content": ["text", "data", "body"],
    "app_name": ["app", "application", "name"],
    "directory": ["dir", "folder", "path"],
    "url": ["link", "uri", "website"],
    "pattern": ["glob", "filter", "match"],
    "source": ["src", "from", "origin"],
    "destination": ["dest", "to", "target"],
}


def normalize_params(params: dict[str, Any], action: str) -> dict[str, Any]:
    normalized = dict(params)

    for canonical_name, aliases in PARAM_ALIASES.items():
        if canonical_name in normalized:
            continue

        for alias in aliases:
            if alias in normalized:
                normalized[canonical_name] = normalized[alias]
                break

    return normalized


class ExecutorConfig:
    def __init__(
        self,
        max_concurrent_tasks: int = 5,
        default_timeout: float = 60.0,
        max_retries: int = 3,
        sandbox_level: SandboxLevel = SandboxLevel.STANDARD,
        enable_resource_monitoring: bool = True,
        log_executions: bool = True,
    ):
        self.max_concurrent_tasks = max_concurrent_tasks
        self.default_timeout = default_timeout
        self.max_retries = max_retries
        self.sandbox_level = sandbox_level
        self.enable_resource_monitoring = enable_resource_monitoring
        self.log_executions = log_executions


ACTION_HANDLERS: dict[str, str] = {
    "file_read": "file",
    "file_write": "file",
    "file_create": "file",
    "file_delete": "file",
    "file_append": "file",
    "command_execute": "command",
    "shell": "command",
    "process": "command",
}


class UnifiedExecutor(BaseExecutor):
    def __init__(
        self,
        config: ExecutorConfig | None = None,
        sandbox_config: SandboxConfig | None = None,
        resource_config: ResourceConfig | None = None,
    ):
        self.config = config or ExecutorConfig()

        self.sandbox_config = sandbox_config or SandboxConfig(
            level=self.config.sandbox_level,
            max_execution_time_seconds=int(self.config.default_timeout),
        )

        self.resource_config = resource_config or ResourceConfig(
            max_execution_time_seconds=int(self.config.default_timeout),
            max_concurrent_tasks=self.config.max_concurrent_tasks,
        )

        self.resource_limiter = ResourceLimiter(self.resource_config)
        self.sandbox_executor = SandboxExecutor(self.sandbox_config, self.resource_limiter)
        self.queue_manager = QueueManager(
            max_concurrent=self.config.max_concurrent_tasks,
            default_timeout=self.config.default_timeout,
            default_max_retries=self.config.max_retries,
        )

        self._initialized = False
        self._action_handlers: dict[str, Callable] = {}
        self._execution_log: list[dict[str, Any]] = []
        self._log_lock = asyncio.Lock()

    async def initialize(self) -> None:
        if self._initialized:
            return

        await self.sandbox_executor.initialize()
        await self.resource_limiter.start_monitoring()

        self.queue_manager.set_executor(self._execute_action)
        await self.queue_manager.start()

        self._initialized = True
        logger.info("UnifiedExecutor initialized")

    async def shutdown(self) -> None:
        if not self._initialized:
            return

        await self.queue_manager.stop()
        await self.sandbox_executor.cleanup()
        await self.resource_limiter.stop_monitoring()

        self._initialized = False
        logger.info("UnifiedExecutor shutdown")

    def register_action_handler(self, action: str, handler: Callable) -> None:
        self._action_handlers[action] = handler

    def unregister_action_handler(self, action: str) -> None:
        self._action_handlers.pop(action, None)

    async def execute(self, action: str, params: dict[str, Any]) -> ExecutionResult:
        if not self._initialized:
            await self.initialize()

        normalized_params = normalize_params(params, action)

        validation = await self.validate_params(action, normalized_params)
        if not validation.is_valid:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                action=action,
                error_code=ErrorCode.VALIDATION_ERROR,
                error_message="; ".join(validation.errors),
            )

        sanitized_params = validation.sanitized_params

        concurrent_check = await self.resource_limiter.check_concurrent_limit()
        if not concurrent_check.allowed:
            task_id = await self.queue_manager.enqueue(
                action=action,
                params=sanitized_params,
                priority=TaskPriority.NORMAL,
            )

            task_info = await self.queue_manager.wait_for_task(task_id)
            if task_info and task_info.status == TaskStatus.COMPLETED:
                return ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    action=action,
                    output=task_info.result,
                    metadata={"task_id": task_id, "queued": True},
                )
            elif task_info:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    action=action,
                    error_code=ErrorCode.EXECUTION_ERROR,
                    error_message=task_info.error_message,
                    metadata={"task_id": task_id, "queued": True},
                )
            else:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    action=action,
                    error_code=ErrorCode.INTERNAL_ERROR,
                    error_message="Task queue error",
                )

        return await self._execute_action(action, sanitized_params)

    async def _execute_action(self, action: str, params: dict[str, Any]) -> ExecutionResult:
        start_time = datetime.now()

        if self.config.log_executions:
            await self._log_execution(action, params, "started")

        try:
            handler = self._action_handlers.get(action)
            if handler:
                result = await handler(action, params)
            else:
                result = await self._route_action(action, params)

            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            result.execution_time_ms = execution_time
            result.action = action

            if self.config.log_executions:
                await self._log_execution(
                    action, params, "completed",
                    result.status.value, execution_time,
                )

            return result

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            logger.error(f"Execution failed: {action} - {e}")

            if self.config.log_executions:
                await self._log_execution(
                    action, params, "failed",
                    "error", execution_time, str(e),
                )

            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                action=action,
                error_code=ErrorCode.INTERNAL_ERROR,
                error_message=str(e),
                execution_time_ms=execution_time,
            )

    async def _route_action(self, action: str, params: dict[str, Any]) -> ExecutionResult:
        handler_type = ACTION_HANDLERS.get(action)

        if handler_type == "file":
            return await self._handle_file_action(action, params)
        elif handler_type == "command":
            return await self._handle_command_action(action, params)
        else:
            return await self._handle_custom_action(action, params)

    async def _handle_file_action(self, action: str, params: dict[str, Any]) -> ExecutionResult:
        operation_map = {
            "file_read": "read",
            "file_write": "write",
            "file_create": "create",
            "file_delete": "delete",
            "file_append": "append",
        }

        operation = operation_map.get(action, action.replace("file_", ""))
        path = params.get("path", params.get("file_path", ""))
        content = params.get("content")

        if content and isinstance(content, str):
            content = content.encode("utf-8")

        return await self.sandbox_executor.execute_file_operation(
            operation=operation,
            path=path,
            content=content,
        )

    async def _handle_command_action(self, action: str, params: dict[str, Any]) -> ExecutionResult:
        command = params.get("command", params.get("cmd", ""))
        cwd = params.get("cwd", params.get("working_dir"))
        env = params.get("env")
        timeout = params.get("timeout")

        return await self.sandbox_executor.execute_command(
            command=command,
            cwd=cwd,
            env=env,
            timeout=timeout,
        )

    async def _handle_custom_action(self, action: str, params: dict[str, Any]) -> ExecutionResult:
        return ExecutionResult(
            status=ExecutionStatus.FAILED,
            action=action,
            error_code=ErrorCode.VALIDATION_ERROR,
            error_message=f"Unknown action: {action}",
        )

    async def validate_params(self, action: str, params: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        sanitized_params = dict(params)

        handler_type = ACTION_HANDLERS.get(action)

        if handler_type == "file":
            path = params.get("path", params.get("file_path"))
            if not path:
                errors.append("Missing required parameter: path or file_path")
            elif not isinstance(path, str):
                errors.append("Path must be a string")
            else:
                path_check = self.sandbox_executor.check_path_access(
                    path,
                    write=(action != "file_read"),
                )
                if not path_check.allowed:
                    errors.append(path_check.reason)
                elif path_check.sanitized_value:
                    sanitized_params["path"] = path_check.sanitized_value

            if action in ("file_write", "file_create", "file_append"):
                content = params.get("content")
                if content is None:
                    errors.append("Missing required parameter: content")
                elif isinstance(content, str):
                    size_check = self.sandbox_executor.check_file_size(len(content.encode("utf-8")))
                    if not size_check.allowed:
                        errors.append(size_check.reason)

        elif handler_type == "command":
            command = params.get("command", params.get("cmd"))
            if not command:
                errors.append("Missing required parameter: command or cmd")
            elif not isinstance(command, str):
                errors.append("Command must be a string")
            else:
                cmd_check = self.sandbox_executor.check_command(command)
                if not cmd_check.allowed:
                    errors.append(cmd_check.reason)

                if cmd_check.risk_level in ("high", "critical"):
                    warnings.append(f"Command has {cmd_check.risk_level} risk level")

            timeout = params.get("timeout")
            if timeout is not None:
                if not isinstance(timeout, (int, float)) or timeout <= 0:
                    errors.append("Timeout must be a positive number")
                elif timeout > self.sandbox_config.max_execution_time_seconds:
                    warnings.append(f"Timeout exceeds maximum allowed ({self.sandbox_config.max_execution_time_seconds}s)")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            sanitized_params=sanitized_params,
        )

    def get_supported_actions(self) -> list[str]:
        base_actions = list(ACTION_HANDLERS.keys())
        custom_actions = list(self._action_handlers.keys())
        return list(set(base_actions + custom_actions))

    def get_action_description(self, action: str) -> str:
        descriptions = {
            "file_read": "Read content from a file",
            "file_write": "Write content to a file",
            "file_create": "Create a new file with content",
            "file_delete": "Delete a file",
            "file_append": "Append content to a file",
            "command_execute": "Execute a shell command",
            "shell": "Execute a shell command",
            "process": "Start a process",
        }
        return descriptions.get(action, f"Execute {action} action")

    def get_required_params(self, action: str) -> list[str]:
        handler_type = ACTION_HANDLERS.get(action)

        if handler_type == "file":
            if action in ("file_write", "file_create", "file_append"):
                return ["path", "content"]
            return ["path"]
        elif handler_type == "command":
            return ["command"]

        return []

    def get_optional_params(self, action: str) -> list[str]:
        handler_type = ACTION_HANDLERS.get(action)

        if handler_type == "file":
            return []
        elif handler_type == "command":
            return ["cwd", "env", "timeout"]

        return []

    async def execute_queued(
        self,
        action: str,
        params: dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not self._initialized:
            await self.initialize()

        validation = await self.validate_params(action, params)
        if not validation.is_valid:
            raise ValueError("; ".join(validation.errors))

        task_id = await self.queue_manager.enqueue(
            action=action,
            params=validation.sanitized_params,
            priority=priority,
            metadata=metadata,
        )

        return task_id

    async def get_task_status(self, task_id: str) -> TaskInfo | None:
        return await self.queue_manager.get_task_status(task_id)

    async def get_task_result(self, task_id: str) -> dict[str, Any] | None:
        return await self.queue_manager.get_task_result(task_id)

    async def cancel_task(self, task_id: str) -> bool:
        return await self.queue_manager.cancel_task(task_id)

    async def wait_for_task(
        self,
        task_id: str,
        timeout: float | None = None,
    ) -> TaskInfo | None:
        return await self.queue_manager.wait_for_task(task_id, timeout)

    async def _log_execution(
        self,
        action: str,
        params: dict[str, Any],
        status: str,
        result_status: str | None = None,
        execution_time_ms: float | None = None,
        error: str | None = None,
    ) -> None:
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "status": status,
            "result_status": result_status,
            "execution_time_ms": execution_time_ms,
            "error": error,
        }

        async with self._log_lock:
            self._execution_log.append(log_entry)

            if len(self._execution_log) > 1000:
                self._execution_log = self._execution_log[-500:]

    def get_execution_log(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._execution_log[-limit:]

    def get_stats(self) -> dict[str, Any]:
        queue_stats = self.queue_manager.get_stats()
        resource_stats = self.resource_limiter.get_stats()

        return {
            "initialized": self._initialized,
            "queue": queue_stats.model_dump(),
            "resources": resource_stats,
            "sandbox": self.sandbox_executor.get_config(),
            "execution_log_count": len(self._execution_log),
        }

    async def health_check(self) -> dict[str, Any]:
        issues: list[str] = []

        if not self._initialized:
            issues.append("Executor not initialized")

        resource_checks = await self.resource_limiter.check_all_limits()
        for name, check in resource_checks.items():
            if check.action.value in ("warn", "throttle"):
                issues.append(f"{name}: {check.message}")

        queue_length = self.queue_manager.get_queue_length()
        if queue_length > 50:
            issues.append(f"Queue backlog: {queue_length} tasks")

        return {
            "healthy": len(issues) == 0,
            "issues": issues,
            "stats": self.get_stats(),
        }
