import logging
import os
from typing import Any

from ..interfaces.base_permission import BasePermissionController
from ..types import PermissionLevel, PermissionResult
from .rbac import (
    Role,
    SensitivityLevel,
    get_action_permissions,
    get_action_sensitivity,
    get_applicable_path_rules,
    get_role_definition,
    get_role_permissions,
    is_sensitive_operation,
    match_path_pattern,
)
from .role_manager import RoleManager, get_role_manager

logger = logging.getLogger(__name__)


class PermissionChecker(BasePermissionController):
    def __init__(self, role_manager: RoleManager | None = None):
        self.role_manager = role_manager or get_role_manager()
        self._verification_required_actions: set[str] = {
            "file_delete",
            "process_stop",
            "service_stop",
            "service_restart",
            "env_write",
            "admin_operation",
        }
        self._elevation_required_actions: set[str] = {
            "admin_operation",
            "service_control",
        }

    async def check_permission(
        self, user_role: str, action: str, params: dict[str, Any]
    ) -> PermissionResult:
        try:
            role = Role(user_role)
        except ValueError:
            return PermissionResult(
                level=PermissionLevel.DENIED,
                reason=f"Invalid role: {user_role}",
                denied_actions=[action],
            )

        role_permissions = get_role_permissions(role)
        action_permissions = get_action_permissions(action)

        if not action_permissions:
            return PermissionResult(
                level=PermissionLevel.DENIED,
                reason=f"Unknown action: {action}",
                denied_actions=[action],
            )

        missing_permissions = action_permissions - role_permissions
        if missing_permissions:
            return PermissionResult(
                level=PermissionLevel.DENIED,
                reason=f"Missing required permissions: {missing_permissions}",
                denied_actions=[action],
                metadata={"missing_permissions": [p.value for p in missing_permissions]},
            )

        if "path" in params:
            path_result = self._check_path_permission(role, params["path"], action)
            if path_result.level != PermissionLevel.ALLOWED:
                return path_result

        if is_sensitive_operation(action):
            sensitivity = get_action_sensitivity(action)
            if sensitivity in (SensitivityLevel.HIGH, SensitivityLevel.CRITICAL):
                return PermissionResult(
                    level=PermissionLevel.REQUIRES_VERIFICATION,
                    reason=f"Action '{action}' requires verification due to high sensitivity",
                    required_verification="two_factor",
                    allowed_actions=[],
                    denied_actions=[],
                    metadata={"sensitivity": sensitivity.value},
                )

        if action in self._elevation_required_actions and role != Role.ADMIN:
            return PermissionResult(
                level=PermissionLevel.REQUIRES_ELEVATION,
                reason=f"Action '{action}' requires elevated privileges",
                required_verification="role_elevation",
                allowed_actions=[],
                denied_actions=[],
            )

        return PermissionResult(
            level=PermissionLevel.ALLOWED,
            reason="Permission granted",
            allowed_actions=[action],
        )

    async def require_verification(self, action: str, params: dict[str, Any]) -> bool:
        if action in self._verification_required_actions:
            return True

        if "path" in params:
            path = params["path"]
            rules = get_applicable_path_rules(path)
            for rule in rules:
                if rule.sensitivity in (SensitivityLevel.HIGH, SensitivityLevel.CRITICAL):
                    return True

        sensitivity = get_action_sensitivity(action)
        return sensitivity in (SensitivityLevel.HIGH, SensitivityLevel.CRITICAL)

    async def get_allowed_paths(self, user_role: str) -> list[str]:
        try:
            role = Role(user_role)
        except ValueError:
            return []

        role_def = get_role_definition(role)
        if not role_def:
            return []

        return role_def.allowed_path_patterns

    def get_role_permissions(self, user_role: str) -> dict[str, Any]:
        try:
            role = Role(user_role)
        except ValueError:
            return {}

        permissions = get_role_permissions(role)
        role_def = get_role_definition(role)

        return {
            "role": role.value,
            "permissions": [p.value for p in permissions],
            "max_file_size_mb": role_def.max_file_size_mb if role_def else 10,
            "max_execution_time_seconds": role_def.max_execution_time_seconds if role_def else 60,
            "max_concurrent_operations": role_def.max_concurrent_operations if role_def else 3,
            "allowed_paths": role_def.allowed_path_patterns if role_def else [],
            "denied_paths": role_def.denied_path_patterns if role_def else [],
        }

    def get_risk_level(self, action: str) -> str:
        sensitivity = get_action_sensitivity(action)
        return sensitivity.value

    def _check_path_permission(
        self, role: Role, path: str, action: str
    ) -> PermissionResult:
        role_def = get_role_definition(role)
        if not role_def:
            return PermissionResult(
                level=PermissionLevel.DENIED,
                reason=f"Role definition not found: {role}",
                denied_actions=[action],
            )

        normalized_path = os.path.normpath(path)

        for denied_pattern in role_def.denied_path_patterns:
            if match_path_pattern(normalized_path, denied_pattern):
                return PermissionResult(
                    level=PermissionLevel.DENIED,
                    reason=f"Path '{path}' is denied by rule: {denied_pattern}",
                    denied_actions=[action],
                    metadata={"denied_pattern": denied_pattern},
                )

        if role_def.allowed_path_patterns:
            allowed = False
            for allowed_pattern in role_def.allowed_path_patterns:
                if match_path_pattern(normalized_path, allowed_pattern):
                    allowed = True
                    break

            if not allowed:
                return PermissionResult(
                    level=PermissionLevel.DENIED,
                    reason=f"Path '{path}' is not in allowed paths",
                    denied_actions=[action],
                    metadata={"allowed_patterns": role_def.allowed_path_patterns},
                )

        rules = get_applicable_path_rules(normalized_path)
        role_permissions = get_role_permissions(role)

        for rule in rules:
            required_permissions = set(rule.permissions)
            if not required_permissions.issubset(role_permissions):
                missing = required_permissions - role_permissions
                return PermissionResult(
                    level=PermissionLevel.DENIED,
                    reason=f"Path rule requires additional permissions: {missing}",
                    denied_actions=[action],
                    metadata={
                        "rule": rule.path_pattern,
                        "sensitivity": rule.sensitivity.value,
                        "missing_permissions": [p.value for p in missing],
                    },
                )

            if rule.sensitivity in (SensitivityLevel.HIGH, SensitivityLevel.CRITICAL):
                return PermissionResult(
                    level=PermissionLevel.REQUIRES_VERIFICATION,
                    reason=f"Path '{path}' requires verification due to sensitivity: {rule.sensitivity.value}",
                    required_verification="two_factor",
                    metadata={"path_rule": rule.path_pattern, "sensitivity": rule.sensitivity.value},
                )

        return PermissionResult(
            level=PermissionLevel.ALLOWED,
            reason="Path access granted",
            allowed_actions=[action],
        )

    def check_resource_limits(
        self,
        user_role: str,
        file_size: int | None = None,
        execution_time: int | None = None,
        concurrent_ops: int | None = None,
    ) -> dict[str, Any]:
        try:
            role = Role(user_role)
        except ValueError:
            return {"allowed": False, "reason": "Invalid role"}

        role_def = get_role_definition(role)
        if not role_def:
            return {"allowed": False, "reason": "Role definition not found"}

        violations = []

        if file_size is not None:
            max_size_bytes = role_def.max_file_size_mb * 1024 * 1024
            if file_size > max_size_bytes:
                violations.append({
                    "type": "file_size",
                    "requested": file_size,
                    "limit": max_size_bytes,
                    "message": f"File size exceeds limit of {role_def.max_file_size_mb}MB",
                })

        if execution_time is not None:
            if execution_time > role_def.max_execution_time_seconds:
                violations.append({
                    "type": "execution_time",
                    "requested": execution_time,
                    "limit": role_def.max_execution_time_seconds,
                    "message": f"Execution time exceeds limit of {role_def.max_execution_time_seconds}s",
                })

        if concurrent_ops is not None:
            if concurrent_ops > role_def.max_concurrent_operations:
                violations.append({
                    "type": "concurrent_operations",
                    "requested": concurrent_ops,
                    "limit": role_def.max_concurrent_operations,
                    "message": f"Concurrent operations exceed limit of {role_def.max_concurrent_operations}",
                })

        return {
            "allowed": len(violations) == 0,
            "violations": violations,
            "limits": {
                "max_file_size_mb": role_def.max_file_size_mb,
                "max_execution_time_seconds": role_def.max_execution_time_seconds,
                "max_concurrent_operations": role_def.max_concurrent_operations,
            },
        }

    def check_user_permission(
        self, user_id: str, action: str, params: dict[str, Any]
    ) -> PermissionResult:
        role = self.role_manager.get_user_role(user_id)
        import asyncio
        return asyncio.run(self.check_permission(role.value, action, params))

    def get_user_allowed_paths(self, user_id: str) -> list[str]:
        role = self.role_manager.get_user_role(user_id)
        import asyncio
        return asyncio.run(self.get_allowed_paths(role.value))


_permission_checker: PermissionChecker | None = None


def get_permission_checker() -> PermissionChecker:
    global _permission_checker
    if _permission_checker is None:
        _permission_checker = PermissionChecker()
    return _permission_checker
