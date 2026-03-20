"""
Permission check decorators
"""
import functools
import asyncio
from typing import Callable, Optional, Union, Any
from .models import Permission, Role, get_permission_for_operation
from .manager import get_rbac_manager


def require_permission(permission: Union[Permission, str]):
    """
    Permission check decorator
    
    Usage:
        @require_permission(Permission.FILE_READ)
        async def read_file(path: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            user_id = kwargs.get("user_id") or (args[0] if args else None)
            
            if user_id is None:
                raise PermissionError("Cannot determine user identity")
            
            perm = permission if isinstance(permission, Permission) else Permission(permission)
            manager = get_rbac_manager()
            
            if not await manager.has_permission(user_id, perm):
                raise PermissionError(f"Insufficient permission: requires {perm.value}")
            
            return await func(*args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            user_id = kwargs.get("user_id") or (args[0] if args else None)
            
            if user_id is None:
                raise PermissionError("Cannot determine user identity")
            
            perm = permission if isinstance(permission, Permission) else Permission(permission)
            manager = get_rbac_manager()
            
            loop = asyncio.get_event_loop()
            if not loop.run_until_complete(manager.has_permission(user_id, perm)):
                raise PermissionError(f"Insufficient permission: requires {perm.value}")
            
            return func(*args, **kwargs)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def require_role(role: Union[Role, str]):
    """
    Role check decorator
    
    Usage:
        @require_role(Role.ADMIN)
        async def admin_operation():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            user_id = kwargs.get("user_id") or (args[0] if args else None)
            
            if user_id is None:
                raise PermissionError("Cannot determine user identity")
            
            required_role = role if isinstance(role, Role) else Role(role)
            manager = get_rbac_manager()
            user_role = await manager.get_user_role(user_id)
            
            role_hierarchy = {
                Role.GUEST: 0,
                Role.STANDARD_USER: 1,
                Role.POWER_USER: 2,
                Role.ADMIN: 3,
            }
            
            if role_hierarchy.get(user_role, 0) < role_hierarchy.get(required_role, 0):
                raise PermissionError(f"Insufficient role: requires {required_role.value}")
            
            return await func(*args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            user_id = kwargs.get("user_id") or (args[0] if args else None)
            
            if user_id is None:
                raise PermissionError("Cannot determine user identity")
            
            required_role = role if isinstance(role, Role) else Role(role)
            manager = get_rbac_manager()
            
            loop = asyncio.get_event_loop()
            user_role = loop.run_until_complete(manager.get_user_role(user_id))
            
            role_hierarchy = {
                Role.GUEST: 0,
                Role.STANDARD_USER: 1,
                Role.POWER_USER: 2,
                Role.ADMIN: 3,
            }
            
            if role_hierarchy.get(user_role, 0) < role_hierarchy.get(required_role, 0):
                raise PermissionError(f"Insufficient role: requires {required_role.value}")
            
            return func(*args, **kwargs)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def require_admin(func: Callable) -> Callable:
    """Admin permission decorator"""
    return require_role(Role.ADMIN)(func)


async def check_permission(user_id: str, operation: str) -> bool:
    """
    Check if user has permission to execute specified operation
    
    Args:
        user_id: User ID
        operation: Operation type
    
    Returns:
        Whether has permission
    """
    permission = get_permission_for_operation(operation)
    if permission is None:
        return False
    
    manager = get_rbac_manager()
    return await manager.has_permission(user_id, permission)


class PermissionChecker:
    """Permission checker class"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self._manager = get_rbac_manager()
    
    async def check(self, permission: Union[Permission, str]) -> bool:
        """Check permission"""
        perm = permission if isinstance(permission, Permission) else Permission(permission)
        return await self._manager.has_permission(self.user_id, perm)
    
    async def check_operation(self, operation: str) -> bool:
        """Check operation permission"""
        return await check_permission(self.user_id, operation)
    
    async def require(self, permission: Union[Permission, str]) -> None:
        """Require permission, raise exception if no permission"""
        if not await self.check(permission):
            perm = permission if isinstance(permission, Permission) else Permission(permission)
            raise PermissionError(f"Insufficient permission: requires {perm.value}")
    
    async def get_role(self) -> Role:
        """Get current role"""
        return await self._manager.get_user_role(self.user_id)
    
    async def get_permissions(self) -> set:
        """Get all permissions"""
        return await self._manager.get_user_permissions(self.user_id)
