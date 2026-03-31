"""
CUA 安全控制模块
"""
import asyncio
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .config import get_cua_config
from .exceptions import EmergencyStopError, PermissionDeniedError, RateLimitExceededError
from .models import AuditLog, OperationResult, OperationType, PermissionLevel


@dataclass
class RateLimitConfig:
    max_count: int
    window_seconds: int
    timestamps: list[datetime] = field(default_factory=list)


class PermissionManager:
    def __init__(self):
        self._permission_level: PermissionLevel = PermissionLevel.INTERACTIVE
        self._operation_permissions: dict[OperationType, PermissionLevel] = {
            OperationType.SCREENSHOT: PermissionLevel.READ_ONLY,
            OperationType.MOUSE_CLICK: PermissionLevel.INTERACTIVE,
            OperationType.MOUSE_MOVE: PermissionLevel.INTERACTIVE,
            OperationType.MOUSE_DRAG: PermissionLevel.INTERACTIVE,
            OperationType.MOUSE_SCROLL: PermissionLevel.INTERACTIVE,
            OperationType.KEYBOARD_TYPE: PermissionLevel.INTERACTIVE,
            OperationType.KEYBOARD_HOTKEY: PermissionLevel.INTERACTIVE,
            OperationType.WINDOW_FOCUS: PermissionLevel.INTERACTIVE,
            OperationType.WINDOW_MINIMIZE: PermissionLevel.FULL_CONTROL,
            OperationType.WINDOW_MAXIMIZE: PermissionLevel.FULL_CONTROL,
            OperationType.WINDOW_CLOSE: PermissionLevel.FULL_CONTROL,
        }
        self._permission_hierarchy: dict[PermissionLevel, int] = {
            PermissionLevel.READ_ONLY: 0,
            PermissionLevel.INTERACTIVE: 1,
            PermissionLevel.FULL_CONTROL: 2,
        }

    def set_permission_level(self, level: PermissionLevel) -> None:
        self._permission_level = level

    def get_permission_level(self) -> PermissionLevel:
        return self._permission_level

    def check_permission(self, operation: OperationType) -> bool:
        required_level = self._operation_permissions.get(operation, PermissionLevel.FULL_CONTROL)
        current_level_value = self._permission_hierarchy.get(self._permission_level, 0)
        required_level_value = self._permission_hierarchy.get(required_level, 0)
        return current_level_value >= required_level_value

    def get_required_permission(self, operation: OperationType) -> PermissionLevel:
        return self._operation_permissions.get(operation, PermissionLevel.FULL_CONTROL)

    def set_operation_permission(self, operation: OperationType, level: PermissionLevel) -> None:
        self._operation_permissions[operation] = level

    def get_all_operation_permissions(self) -> dict[OperationType, PermissionLevel]:
        return self._operation_permissions.copy()


class SafetyController:
    SENSITIVE_OPERATIONS: dict[OperationType, list[str]] = {
        OperationType.KEYBOARD_HOTKEY: [
            "delete", "ctrl+delete", "shift+delete",
            "alt+f4", "ctrl+alt+delete",
            "win+r", "win+x", "ctrl+shift+esc",
        ],
        OperationType.WINDOW_CLOSE: [],
        OperationType.KEYBOARD_TYPE: [],
    }

    SENSITIVE_KEYWORDS: list[str] = [
        "format", "delete", "remove", "uninstall",
        "registry", "regedit", "taskkill", "shutdown",
        "restart", "reboot", "system32", "cmd", "powershell",
        "diskpart", "bcdedit", "bootsect", "takeown", "icacls",
        "net user", "net localgroup", "netsh", "ipconfig",
        "wmic", "psexec", "rmdir", "del /", "Remove-Item",
        "Invoke-Expression", "iex", "Start-Process",
        "New-Service", "Stop-Service", "docker", "kubectl",
        "chmod", "chown", "sudo", "su ", "rm -rf",
        "dd if", "mkfs", "fdisk", "parted",
        "wget", "curl", "Invoke-WebRequest",
        "drop table", "truncate table", "delete from",
        "password", "secret", "token", "api_key", "apikey",
        "credential", "private_key", "access_token",
    ]

    def __init__(self):
        self._permission_manager = PermissionManager()
        self._failsafe_enabled: bool = True
        self._emergency_stop_triggered: bool = False
        self._confirmation_callback: Callable | None = None
        self._audit_logs: list[AuditLog] = []
        self._audit_lock = asyncio.Lock()
        self._rate_limits: dict[OperationType, RateLimitConfig] = defaultdict(lambda: RateLimitConfig(max_count=100, window_seconds=60))
        self._rate_lock = asyncio.Lock()
        self._config = get_cua_config()
        self._initialize_from_config()

    def _initialize_from_config(self) -> None:
        self._permission_manager.set_permission_level(self._config.get_effective_permission())
        self._failsafe_enabled = self._config.failsafe_enabled

    def check_permission(self, operation: OperationType) -> bool:
        if self._emergency_stop_triggered:
            raise EmergencyStopError()
        return self._permission_manager.check_permission(operation)

    def set_permission_level(self, level: PermissionLevel) -> None:
        self._permission_manager.set_permission_level(level)

    def get_permission_level(self) -> PermissionLevel:
        return self._permission_manager.get_permission_level()

    def is_sensitive_operation(self, operation: OperationType, params: dict) -> bool:
        if operation == OperationType.KEYBOARD_HOTKEY:
            hotkey = params.get("hotkey", [])
            if isinstance(hotkey, list):
                hotkey_str = "+".join(str(k).lower() for k in hotkey)
                for sensitive in self.SENSITIVE_OPERATIONS.get(OperationType.KEYBOARD_HOTKEY, []):
                    if sensitive.lower() in hotkey_str:
                        return True
        if operation == OperationType.WINDOW_CLOSE:
            return True
        if operation == OperationType.KEYBOARD_TYPE:
            text = params.get("text", "")
            if isinstance(text, str):
                text_lower = text.lower()
                for keyword in self.SENSITIVE_KEYWORDS:
                    if keyword in text_lower:
                        return True
        return False

    async def request_confirmation(self, operation: OperationType, params: dict) -> bool:
        if self._confirmation_callback is None:
            return True
        try:
            if asyncio.iscoroutinefunction(self._confirmation_callback):
                return await self._confirmation_callback(operation, params)
            else:
                return self._confirmation_callback(operation, params)
        except Exception:
            return False

    def set_confirmation_callback(self, callback: Callable) -> None:
        self._confirmation_callback = callback

    async def log_operation(self, operation: OperationType, params: dict, result: OperationResult) -> None:
        if not self._config.audit_enabled:
            return
        async with self._audit_lock:
            log_entry = AuditLog(
                operation_type=operation,
                permission_level=self._permission_manager.get_permission_level(),
                parameters=params,
                result=result.success,
                duration_ms=result.duration_ms,
                error_message=result.error,
            )
            self._audit_logs.append(log_entry)

    async def get_audit_logs(self, limit: int = 100) -> list[AuditLog]:
        async with self._audit_lock:
            return self._audit_logs[-limit:]

    async def clear_audit_logs(self) -> None:
        async with self._audit_lock:
            self._audit_logs.clear()

    async def check_rate_limit(self, operation: OperationType) -> bool:
        async with self._rate_lock:
            config = self._rate_limits[operation]
            now = datetime.now()
            window_start = now - timedelta(seconds=config.window_seconds)
            config.timestamps = [ts for ts in config.timestamps if ts > window_start]
            if len(config.timestamps) >= config.max_count:
                oldest = min(config.timestamps)
                retry_after = int((oldest + timedelta(seconds=config.window_seconds) - now).total_seconds())
                raise RateLimitExceededError(
                    message="操作频率超限",
                    operation=operation.value,
                    retry_after=max(1, retry_after)
                )
            config.timestamps.append(now)
            return True

    def set_rate_limit(self, operation: OperationType, max_count: int, window_seconds: int) -> None:
        self._rate_limits[operation] = RateLimitConfig(
            max_count=max_count,
            window_seconds=window_seconds
        )

    def enable_failsafe(self, enabled: bool) -> None:
        self._failsafe_enabled = enabled

    def is_failsafe_enabled(self) -> bool:
        return self._failsafe_enabled

    def trigger_emergency_stop(self) -> None:
        self._emergency_stop_triggered = True

    def reset_emergency_stop(self) -> None:
        self._emergency_stop_triggered = False

    def is_emergency_stop_triggered(self) -> bool:
        return self._emergency_stop_triggered

    async def validate_operation(self, operation: OperationType, params: dict) -> bool:
        if self._emergency_stop_triggered:
            raise EmergencyStopError()
        if not self.check_permission(operation):
            required = self._permission_manager.get_required_permission(operation)
            raise PermissionDeniedError(
                message="权限不足",
                operation=operation.value,
                required_level=required.value
            )
        await self.check_rate_limit(operation)
        if self.is_sensitive_operation(operation, params):
            confirmed = await self.request_confirmation(operation, params)
            if not confirmed:
                raise PermissionDeniedError(
                    message="用户拒绝敏感操作",
                    operation=operation.value
                )
        return True

    def get_permission_manager(self) -> PermissionManager:
        return self._permission_manager


_safety_controller: SafetyController | None = None


def get_safety_controller() -> SafetyController:
    global _safety_controller
    if _safety_controller is None:
        _safety_controller = SafetyController()
    return _safety_controller


def reset_safety_controller() -> SafetyController:
    global _safety_controller
    _safety_controller = SafetyController()
    return _safety_controller
