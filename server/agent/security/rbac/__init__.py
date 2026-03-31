"""
RBAC 权限系统模块

提供完整的基于角色的访问控制功能
"""
from .decorator import (
    check_permission,
    require_admin,
    require_permission,
    require_role,
)
from .inheritance import (
    InheritanceResolver,
    PermissionInheritance,
    RoleInheritance,
)
from .manager import (
    RBACManager,
    RoleAssignment,
    get_rbac_manager,
)
from .models import (
    OperationType,
    Permission,
    PermissionSet,
    ResourcePermission,
    ResourceType,
    Role,
    RoleDefinition,
)

__all__ = [
    "Permission",
    "Role",
    "ResourceType",
    "OperationType",
    "RoleDefinition",
    "PermissionSet",
    "ResourcePermission",
    "RBACManager",
    "RoleAssignment",
    "get_rbac_manager",
    "require_permission",
    "require_role",
    "require_admin",
    "check_permission",
    "RoleInheritance",
    "PermissionInheritance",
    "InheritanceResolver",
]
