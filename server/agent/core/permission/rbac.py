from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Set
from pydantic import BaseModel, Field
from dataclasses import dataclass, field


class Permission(str, Enum):
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    PROCESS_MANAGE = "process_manage"
    SERVICE_CONTROL = "service_control"
    ENVIRONMENT_ACCESS = "environment_access"
    ADMIN = "admin"
    NETWORK_ACCESS = "network_access"
    COMMAND_EXECUTE = "command_execute"
    GPU_ACCESS = "gpu_access"


class Role(str, Enum):
    ADMIN = "admin"
    POWER_USER = "power_user"
    STANDARD_USER = "standard_user"
    GUEST = "guest"


class SensitivityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class PathAccessRule:
    path_pattern: str
    permissions: FrozenSet[Permission]
    sensitivity: SensitivityLevel = SensitivityLevel.LOW
    description: str = ""


class RoleDefinition(BaseModel):
    role: Role
    permissions: Set[Permission] = Field(default_factory=set)
    inherits_from: Optional[Role] = None
    max_file_size_mb: int = 10
    max_execution_time_seconds: int = 60
    max_concurrent_operations: int = 3
    allowed_path_patterns: List[str] = Field(default_factory=list)
    denied_path_patterns: List[str] = Field(default_factory=list)
    description: str = ""


ROLE_PERMISSIONS: Dict[Role, RoleDefinition] = {
    Role.ADMIN: RoleDefinition(
        role=Role.ADMIN,
        permissions=set(Permission),
        max_file_size_mb=1024,
        max_execution_time_seconds=3600,
        max_concurrent_operations=100,
        allowed_path_patterns=["*"],
        description="Full system access with all permissions",
    ),
    Role.POWER_USER: RoleDefinition(
        role=Role.POWER_USER,
        permissions={
            Permission.FILE_READ,
            Permission.FILE_WRITE,
            Permission.FILE_DELETE,
            Permission.PROCESS_MANAGE,
            Permission.NETWORK_ACCESS,
            Permission.COMMAND_EXECUTE,
            Permission.GPU_ACCESS,
        },
        inherits_from=Role.STANDARD_USER,
        max_file_size_mb=200,
        max_execution_time_seconds=300,
        max_concurrent_operations=20,
        allowed_path_patterns=["/workspace/*", "/home/*", "/tmp/*", "/data/*"],
        denied_path_patterns=["/etc/*", "/root/*", "/var/log/*"],
        description="Elevated permissions for advanced operations",
    ),
    Role.STANDARD_USER: RoleDefinition(
        role=Role.STANDARD_USER,
        permissions={
            Permission.FILE_READ,
            Permission.FILE_WRITE,
            Permission.NETWORK_ACCESS,
            Permission.COMMAND_EXECUTE,
        },
        inherits_from=Role.GUEST,
        max_file_size_mb=50,
        max_execution_time_seconds=120,
        max_concurrent_operations=10,
        allowed_path_patterns=["/workspace/*", "/home/*", "/tmp/*"],
        denied_path_patterns=["/etc/*", "/root/*"],
        description="Standard user with read/write capabilities",
    ),
    Role.GUEST: RoleDefinition(
        role=Role.GUEST,
        permissions={
            Permission.FILE_READ,
        },
        max_file_size_mb=5,
        max_execution_time_seconds=30,
        max_concurrent_operations=3,
        allowed_path_patterns=["/workspace/public/*", "/tmp/*"],
        denied_path_patterns=["/etc/*", "/root/*", "/home/*"],
        description="Limited read-only access",
    ),
}

DEFAULT_PATH_RULES: List[PathAccessRule] = [
    PathAccessRule(
        path_pattern="/etc/*",
        permissions=frozenset({Permission.ADMIN}),
        sensitivity=SensitivityLevel.CRITICAL,
        description="System configuration files",
    ),
    PathAccessRule(
        path_pattern="/root/*",
        permissions=frozenset({Permission.ADMIN}),
        sensitivity=SensitivityLevel.CRITICAL,
        description="Root user home directory",
    ),
    PathAccessRule(
        path_pattern="/var/log/*",
        permissions=frozenset({Permission.ADMIN, Permission.FILE_READ}),
        sensitivity=SensitivityLevel.HIGH,
        description="System log files",
    ),
    PathAccessRule(
        path_pattern="/workspace/*",
        permissions=frozenset({
            Permission.FILE_READ,
            Permission.FILE_WRITE,
            Permission.FILE_DELETE,
        }),
        sensitivity=SensitivityLevel.LOW,
        description="User workspace directory",
    ),
    PathAccessRule(
        path_pattern="/home/*",
        permissions=frozenset({
            Permission.FILE_READ,
            Permission.FILE_WRITE,
        }),
        sensitivity=SensitivityLevel.MEDIUM,
        description="User home directories",
    ),
    PathAccessRule(
        path_pattern="/tmp/*",
        permissions=frozenset({
            Permission.FILE_READ,
            Permission.FILE_WRITE,
            Permission.FILE_DELETE,
        }),
        sensitivity=SensitivityLevel.LOW,
        description="Temporary files directory",
    ),
    PathAccessRule(
        path_pattern="/data/*",
        permissions=frozenset({
            Permission.FILE_READ,
            Permission.FILE_WRITE,
            Permission.FILE_DELETE,
        }),
        sensitivity=SensitivityLevel.MEDIUM,
        description="Data storage directory",
    ),
]

ACTION_PERMISSION_MAPPING: Dict[str, Set[Permission]] = {
    "file_read": {Permission.FILE_READ},
    "file_write": {Permission.FILE_WRITE},
    "file_delete": {Permission.FILE_DELETE},
    "file_create": {Permission.FILE_WRITE},
    "file_copy": {Permission.FILE_READ, Permission.FILE_WRITE},
    "file_move": {Permission.FILE_READ, Permission.FILE_WRITE, Permission.FILE_DELETE},
    "process_start": {Permission.PROCESS_MANAGE},
    "process_stop": {Permission.PROCESS_MANAGE},
    "process_list": {Permission.PROCESS_MANAGE},
    "service_start": {Permission.SERVICE_CONTROL},
    "service_stop": {Permission.SERVICE_CONTROL},
    "service_restart": {Permission.SERVICE_CONTROL},
    "env_read": {Permission.ENVIRONMENT_ACCESS},
    "env_write": {Permission.ENVIRONMENT_ACCESS},
    "command_execute": {Permission.COMMAND_EXECUTE},
    "network_access": {Permission.NETWORK_ACCESS},
    "gpu_access": {Permission.GPU_ACCESS},
    "admin_operation": {Permission.ADMIN},
}

SENSITIVE_OPERATIONS: Dict[str, SensitivityLevel] = {
    "file_delete": SensitivityLevel.HIGH,
    "process_stop": SensitivityLevel.HIGH,
    "service_stop": SensitivityLevel.HIGH,
    "service_restart": SensitivityLevel.MEDIUM,
    "env_write": SensitivityLevel.HIGH,
    "admin_operation": SensitivityLevel.CRITICAL,
    "file_write": SensitivityLevel.MEDIUM,
    "process_start": SensitivityLevel.MEDIUM,
}


def get_role_permissions(role: Role) -> Set[Permission]:
    permissions = set()
    current_role: Optional[Role] = role
    
    while current_role is not None:
        role_def = ROLE_PERMISSIONS.get(current_role)
        if role_def:
            permissions.update(role_def.permissions)
            current_role = role_def.inherits_from
        else:
            break
    
    return permissions


def get_role_definition(role: Role) -> Optional[RoleDefinition]:
    return ROLE_PERMISSIONS.get(role)


def get_action_permissions(action: str) -> Set[Permission]:
    return ACTION_PERMISSION_MAPPING.get(action, set())


def get_action_sensitivity(action: str) -> SensitivityLevel:
    return SENSITIVE_OPERATIONS.get(action, SensitivityLevel.LOW)


def is_sensitive_operation(action: str) -> bool:
    return action in SENSITIVE_OPERATIONS


def match_path_pattern(path: str, pattern: str) -> bool:
    import fnmatch
    if pattern == "*":
        return True
    return fnmatch.fnmatch(path, pattern)


def get_applicable_path_rules(path: str) -> List[PathAccessRule]:
    applicable_rules = []
    for rule in DEFAULT_PATH_RULES:
        if match_path_pattern(path, rule.path_pattern):
            applicable_rules.append(rule)
    return applicable_rules
