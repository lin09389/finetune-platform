"""
RBAC 权限系统模块

提供完整的基于角色的访问控制功能
"""
from .models import (
    Permission,
    Role,
    ResourceType,
    OperationType,
    RoleDefinition,
    PermissionSet,
    ResourcePermission,
)
from .manager import (
    RBACManager,
    RoleAssignment,
    get_rbac_manager,
)
from .decorator import (
    require_permission,
    require_role,
    require_admin,
    check_permission,
)
from .inheritance import (
    RoleInheritance,
    PermissionInheritance,
    InheritanceResolver,
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
