"""
角色分配管理
"""
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from .models import Role, RoleDefinition, Permission, get_role_definition, DEFAULT_ROLE_DEFINITIONS


class RoleAssignment(BaseModel):
    """角色分配记录"""
    user_id: str
    role: Role
    assigned_by: Optional[str] = None
    assigned_at: datetime = Field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    is_active: bool = True
    metadata: Dict = Field(default_factory=dict)


class RBACManager:
    """RBAC 管理器"""
    
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path("data/rbac")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self._assignments: Dict[str, RoleAssignment] = {}
        self._custom_roles: Dict[Role, RoleDefinition] = {}
        self._lock = asyncio.Lock()
        
        self._load_assignments()
    
    def _load_assignments(self):
        """加载角色分配记录"""
        assignments_file = self.storage_path / "assignments.json"
        if assignments_file.exists():
            try:
                with open(assignments_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data.get("assignments", []):
                        assignment = RoleAssignment(**item)
                        if assignment.expires_at and datetime.now() > assignment.expires_at:
                            continue
                        self._assignments[assignment.user_id] = assignment
            except Exception:
                pass
    
    def _save_assignments(self):
        """保存角色分配记录"""
        assignments_file = self.storage_path / "assignments.json"
        try:
            data = {
                "assignments": [
                    a.model_dump(mode="json") 
                    for a in self._assignments.values()
                ]
            }
            with open(assignments_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        except Exception:
            pass
    
    async def assign_role(
        self,
        user_id: str,
        role: Role,
        assigned_by: Optional[str] = None,
        expires_in_hours: Optional[int] = None,
    ) -> RoleAssignment:
        """分配角色"""
        async with self._lock:
            expires_at = None
            if expires_in_hours:
                expires_at = datetime.now() + timedelta(hours=expires_in_hours)
            
            assignment = RoleAssignment(
                user_id=user_id,
                role=role,
                assigned_by=assigned_by,
                expires_at=expires_at,
            )
            
            self._assignments[user_id] = assignment
            self._save_assignments()
            
            return assignment
    
    async def get_user_role(self, user_id: str) -> Role:
        """获取用户角色"""
        assignment = self._assignments.get(user_id)
        
        if assignment:
            if assignment.expires_at and datetime.now() > assignment.expires_at:
                del self._assignments[user_id]
                self._save_assignments()
                return Role.GUEST
            if assignment.is_active:
                return assignment.role
        
        return Role.GUEST
    
    async def get_user_permissions(self, user_id: str) -> Set[Permission]:
        """获取用户权限（含继承）"""
        role = await self.get_user_role(user_id)
        role_def = self._get_role_definition_with_inheritance(role)
        return role_def.permission_set.permissions.copy()
    
    def _get_role_definition_with_inheritance(self, role: Role) -> RoleDefinition:
        """获取角色定义（含继承）"""
        if role in self._custom_roles:
            role_def = self._custom_roles[role]
        else:
            role_def = DEFAULT_ROLE_DEFINITIONS.get(role, DEFAULT_ROLE_DEFINITIONS[Role.GUEST])
        
        if role_def.inherits_from:
            parent_def = self._get_role_definition_with_inheritance(role_def.inherits_from)
            combined_permissions = parent_def.permission_set.permissions | role_def.permission_set.permissions
            
            new_permission_set = role_def.permission_set.model_copy()
            new_permission_set.permissions = combined_permissions
            
            return RoleDefinition(
                role=role_def.role,
                name=role_def.name,
                description=role_def.description,
                permission_set=new_permission_set,
                inherits_from=role_def.inherits_from,
                is_system=role_def.is_system,
            )
        
        return role_def
    
    async def has_permission(self, user_id: str, permission: Permission) -> bool:
        """检查用户是否有指定权限"""
        permissions = await self.get_user_permissions(user_id)
        return Permission.ADMIN in permissions or permission in permissions
    
    async def revoke_role(self, user_id: str) -> bool:
        """撤销角色"""
        async with self._lock:
            if user_id in self._assignments:
                del self._assignments[user_id]
                self._save_assignments()
                return True
            return False
    
    async def elevate_role(
        self,
        user_id: str,
        new_role: Role,
        duration_hours: int = 1,
        assigned_by: Optional[str] = None,
    ) -> Optional[RoleAssignment]:
        """临时提升角色"""
        current_role = await self.get_user_role(user_id)
        
        role_order = [Role.GUEST, Role.STANDARD_USER, Role.POWER_USER, Role.ADMIN]
        current_index = role_order.index(current_role)
        new_index = role_order.index(new_role)
        
        if new_index <= current_index:
            return None
        
        return await self.assign_role(
            user_id=user_id,
            role=new_role,
            assigned_by=assigned_by,
            expires_in_hours=duration_hours,
        )
    
    async def get_all_assignments(self) -> List[RoleAssignment]:
        """获取所有角色分配"""
        return list(self._assignments.values())
    
    async def get_users_by_role(self, role: Role) -> List[str]:
        """获取指定角色的所有用户"""
        return [
            user_id for user_id, assignment in self._assignments.items()
            if assignment.role == role and assignment.is_active
        ]
    
    async def cleanup_expired(self) -> int:
        """清理过期分配"""
        async with self._lock:
            expired_count = 0
            expired_users = [
                user_id for user_id, assignment in self._assignments.items()
                if assignment.expires_at and datetime.now() > assignment.expires_at
            ]
            
            for user_id in expired_users:
                del self._assignments[user_id]
                expired_count += 1
            
            if expired_count > 0:
                self._save_assignments()
            
            return expired_count


_rbac_manager: Optional[RBACManager] = None


def get_rbac_manager() -> RBACManager:
    """获取 RBAC 管理器单例"""
    global _rbac_manager
    if _rbac_manager is None:
        _rbac_manager = RBACManager()
    return _rbac_manager
