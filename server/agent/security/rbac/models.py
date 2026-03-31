"""
角色和权限模型定义
"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Permission(str, Enum):
    """权限类型"""
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    FILE_EXECUTE = "file_execute"

    DIRECTORY_LIST = "directory_list"
    DIRECTORY_CREATE = "directory_create"
    DIRECTORY_DELETE = "directory_delete"

    PROCESS_LIST = "process_list"
    PROCESS_VIEW = "process_view"
    PROCESS_KILL = "process_kill"

    SERVICE_LIST = "service_list"
    SERVICE_VIEW = "service_view"
    SERVICE_START = "service_start"
    SERVICE_STOP = "service_stop"
    SERVICE_RESTART = "service_restart"

    ENVIRONMENT_READ = "environment_read"
    ENVIRONMENT_WRITE = "environment_write"

    NETWORK_CONNECT = "network_connect"
    NETWORK_LISTEN = "network_listen"

    APP_LAUNCH = "app_launch"
    APP_CLOSE = "app_close"
    WINDOW_MANAGE = "window_manage"

    CLIPBOARD_READ = "clipboard_read"
    CLIPBOARD_WRITE = "clipboard_write"

    HARDWARE_MONITOR = "hardware_monitor"
    SYSTEM_INFO = "system_info"

    ADMIN = "admin"
    AUDIT_VIEW = "audit_view"
    AUDIT_EXPORT = "audit_export"
    ROLE_MANAGE = "role_manage"
    USER_MANAGE = "user_manage"


class Role(str, Enum):
    """角色类型"""
    ADMIN = "admin"
    POWER_USER = "power_user"
    STANDARD_USER = "standard_user"
    GUEST = "guest"


class ResourceType(str, Enum):
    """资源类型"""
    FILE = "file"
    DIRECTORY = "directory"
    PROCESS = "process"
    SERVICE = "service"
    ENVIRONMENT = "environment"
    NETWORK = "network"
    APPLICATION = "application"
    CLIPBOARD = "clipboard"
    HARDWARE = "hardware"
    SYSTEM = "system"


class OperationType(str, Enum):
    """操作类型"""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"
    LIST = "list"
    CREATE = "create"
    MANAGE = "manage"
    MONITOR = "monitor"


class ResourcePermission(BaseModel):
    """资源权限"""
    resource_type: ResourceType
    allowed_operations: set[OperationType] = Field(default_factory=set)
    denied_operations: set[OperationType] = Field(default_factory=set)
    path_patterns: list[str] = Field(default_factory=list)
    excluded_paths: list[str] = Field(default_factory=list)


class PermissionSet(BaseModel):
    """权限集合"""
    permissions: set[Permission] = Field(default_factory=set)
    resource_permissions: list[ResourcePermission] = Field(default_factory=list)
    max_file_size: int = 10 * 1024 * 1024
    max_execution_time: int = 60
    max_concurrent_tasks: int = 3
    allowed_network_hosts: list[str] = Field(default_factory=list)
    denied_network_hosts: list[str] = Field(default_factory=list)


class RoleDefinition(BaseModel):
    """角色定义"""
    role: Role
    name: str
    description: str
    permission_set: PermissionSet
    inherits_from: Role | None = None
    is_system: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


DEFAULT_ROLE_DEFINITIONS: dict[Role, RoleDefinition] = {
    Role.ADMIN: RoleDefinition(
        role=Role.ADMIN,
        name="Administrator",
        description="Full access permissions",
        permission_set=PermissionSet(
            permissions=set(Permission),
            max_file_size=1024 * 1024 * 1024,
            max_execution_time=3600,
            max_concurrent_tasks=100,
        ),
        is_system=True,
    ),
    Role.POWER_USER: RoleDefinition(
        role=Role.POWER_USER,
        name="Power User",
        description="Advanced operation permissions",
        permission_set=PermissionSet(
            permissions={
                Permission.FILE_READ, Permission.FILE_WRITE, Permission.FILE_DELETE,
                Permission.DIRECTORY_LIST, Permission.DIRECTORY_CREATE, Permission.DIRECTORY_DELETE,
                Permission.PROCESS_LIST, Permission.PROCESS_VIEW, Permission.PROCESS_KILL,
                Permission.SERVICE_LIST, Permission.SERVICE_VIEW,
                Permission.ENVIRONMENT_READ,
                Permission.NETWORK_CONNECT,
                Permission.APP_LAUNCH, Permission.APP_CLOSE, Permission.WINDOW_MANAGE,
                Permission.CLIPBOARD_READ, Permission.CLIPBOARD_WRITE,
                Permission.HARDWARE_MONITOR, Permission.SYSTEM_INFO,
            },
            max_file_size=200 * 1024 * 1024,
            max_execution_time=300,
            max_concurrent_tasks=10,
        ),
        inherits_from=Role.STANDARD_USER,
        is_system=True,
    ),
    Role.STANDARD_USER: RoleDefinition(
        role=Role.STANDARD_USER,
        name="Standard User",
        description="Standard operation permissions",
        permission_set=PermissionSet(
            permissions={
                Permission.FILE_READ, Permission.FILE_WRITE,
                Permission.DIRECTORY_LIST, Permission.DIRECTORY_CREATE,
                Permission.PROCESS_LIST, Permission.PROCESS_VIEW,
                Permission.SERVICE_LIST, Permission.SERVICE_VIEW,
                Permission.ENVIRONMENT_READ,
                Permission.APP_LAUNCH,
                Permission.CLIPBOARD_READ, Permission.CLIPBOARD_WRITE,
                Permission.HARDWARE_MONITOR, Permission.SYSTEM_INFO,
            },
            max_file_size=50 * 1024 * 1024,
            max_execution_time=120,
            max_concurrent_tasks=5,
        ),
        inherits_from=Role.GUEST,
        is_system=True,
    ),
    Role.GUEST: RoleDefinition(
        role=Role.GUEST,
        name="Guest",
        description="Read-only permissions",
        permission_set=PermissionSet(
            permissions={
                Permission.FILE_READ,
                Permission.DIRECTORY_LIST,
                Permission.PROCESS_LIST,
                Permission.SERVICE_LIST,
                Permission.ENVIRONMENT_READ,
                Permission.HARDWARE_MONITOR, Permission.SYSTEM_INFO,
            },
            max_file_size=5 * 1024 * 1024,
            max_execution_time=30,
            max_concurrent_tasks=1,
        ),
        is_system=True,
    ),
}


def get_role_definition(role: Role) -> RoleDefinition:
    """获取角色定义"""
    return DEFAULT_ROLE_DEFINITIONS.get(role, DEFAULT_ROLE_DEFINITIONS[Role.GUEST])


def get_permission_for_operation(operation: str) -> Permission | None:
    """根据操作类型获取所需权限"""
    operation_permission_map = {
        "file_read": Permission.FILE_READ,
        "file_write": Permission.FILE_WRITE,
        "file_delete": Permission.FILE_DELETE,
        "file_create": Permission.FILE_WRITE,
        "file_copy": Permission.FILE_READ,
        "file_move": Permission.FILE_WRITE,
        "file_rename": Permission.FILE_WRITE,
        "file_list": Permission.DIRECTORY_LIST,
        "directory_create": Permission.DIRECTORY_CREATE,
        "directory_delete": Permission.DIRECTORY_DELETE,
        "process_list": Permission.PROCESS_LIST,
        "process_view": Permission.PROCESS_VIEW,
        "process_kill": Permission.PROCESS_KILL,
        "service_list": Permission.SERVICE_LIST,
        "service_view": Permission.SERVICE_VIEW,
        "service_start": Permission.SERVICE_START,
        "service_stop": Permission.SERVICE_STOP,
        "service_restart": Permission.SERVICE_RESTART,
        "environment_read": Permission.ENVIRONMENT_READ,
        "environment_write": Permission.ENVIRONMENT_WRITE,
        "app_open": Permission.APP_LAUNCH,
        "app_close": Permission.APP_CLOSE,
        "window_list": Permission.WINDOW_MANAGE,
        "clipboard_read": Permission.CLIPBOARD_READ,
        "clipboard_write": Permission.CLIPBOARD_WRITE,
        "hardware_monitor": Permission.HARDWARE_MONITOR,
        "system_info": Permission.SYSTEM_INFO,
    }
    return operation_permission_map.get(operation)
