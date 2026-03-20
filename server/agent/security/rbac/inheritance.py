"""
权限继承机制
"""
from typing import Dict, List, Optional, Set
from .models import Role, RoleDefinition, Permission, DEFAULT_ROLE_DEFINITIONS


class RoleInheritance:
    """角色继承关系"""
    
    INHERITANCE_TREE: Dict[Role, Optional[Role]] = {
        Role.ADMIN: Role.POWER_USER,
        Role.POWER_USER: Role.STANDARD_USER,
        Role.STANDARD_USER: Role.GUEST,
        Role.GUEST: None,
    }
    
    @classmethod
    def get_parent(cls, role: Role) -> Optional[Role]:
        """获取父角色"""
        return cls.INHERITANCE_TREE.get(role)
    
    @classmethod
    def get_ancestors(cls, role: Role) -> List[Role]:
        """获取所有祖先角色"""
        ancestors = []
        current = cls.get_parent(role)
        while current:
            ancestors.append(current)
            current = cls.get_parent(current)
        return ancestors
    
    @classmethod
    def get_children(cls, role: Role) -> List[Role]:
        """获取子角色"""
        return [r for r, parent in cls.INHERITANCE_TREE.items() if parent == role]
    
    @classmethod
    def get_descendants(cls, role: Role) -> List[Role]:
        """获取所有后代角色"""
        descendants = []
        children = cls.get_children(role)
        for child in children:
            descendants.append(child)
            descendants.extend(cls.get_descendants(child))
        return descendants
    
    @classmethod
    def is_ancestor_of(cls, ancestor: Role, descendant: Role) -> bool:
        """判断是否为祖先角色"""
        return ancestor in cls.get_ancestors(descendant)
    
    @classmethod
    def is_descendant_of(cls, descendant: Role, ancestor: Role) -> bool:
        """判断是否为后代角色"""
        return descendant in cls.get_descendants(ancestor)


class PermissionInheritance:
    """权限继承"""
    
    @classmethod
    def inherit_permissions(cls, role: Role) -> Set[Permission]:
        """继承权限"""
        role_def = DEFAULT_ROLE_DEFINITIONS.get(role)
        if not role_def:
            return set()
        
        permissions = role_def.permission_set.permissions.copy()
        
        parent = RoleInheritance.get_parent(role)
        if parent:
            parent_permissions = cls.inherit_permissions(parent)
            permissions.update(parent_permissions)
        
        return permissions
    
    @classmethod
    def get_effective_permissions(cls, role: Role, custom_permissions: Optional[Set[Permission]] = None) -> Set[Permission]:
        """获取有效权限（含继承和自定义）"""
        permissions = cls.inherit_permissions(role)
        
        if custom_permissions:
            permissions.update(custom_permissions)
        
        return permissions
    
    @classmethod
    def get_permission_sources(cls, role: Role) -> Dict[Permission, Role]:
        """获取权限来源"""
        sources = {}
        
        for perm in cls.inherit_permissions(role):
            current_role = role
            while current_role:
                role_def = DEFAULT_ROLE_DEFINITIONS.get(current_role)
                if role_def and perm in role_def.permission_set.permissions:
                    sources[perm] = current_role
                    break
                current_role = RoleInheritance.get_parent(current_role)
        
        return sources


class InheritanceResolver:
    """继承解析器"""
    
    def __init__(self):
        self._role_inheritance = RoleInheritance()
        self._permission_inheritance = PermissionInheritance()
    
    def resolve_role_permissions(self, role: Role) -> Set[Permission]:
        """解析角色权限"""
        return self._permission_inheritance.inherit_permissions(role)
    
    def resolve_role_hierarchy(self, role: Role) -> List[Role]:
        """解析角色层级"""
        hierarchy = [role]
        hierarchy.extend(self._role_inheritance.get_ancestors(role))
        return hierarchy
    
    def get_role_level(self, role: Role) -> int:
        """获取角色层级"""
        levels = {
            Role.GUEST: 0,
            Role.STANDARD_USER: 1,
            Role.POWER_USER: 2,
            Role.ADMIN: 3,
        }
        return levels.get(role, 0)
    
    def compare_roles(self, role1: Role, role2: Role) -> int:
        """比较角色级别"""
        level1 = self.get_role_level(role1)
        level2 = self.get_role_level(role2)
        return level1 - level2
    
    def is_higher_role(self, role1: Role, role2: Role) -> bool:
        """判断 role1 是否高于 role2"""
        return self.compare_roles(role1, role2) > 0
    
    def can_manage_role(self, manager_role: Role, target_role: Role) -> bool:
        """判断是否可以管理目标角色"""
        if manager_role == Role.ADMIN:
            return True
        
        return self.is_higher_role(manager_role, target_role)
    
    def get_permission_inheritance_chain(self, role: Role, permission: Permission) -> List[Role]:
        """获取权限继承链"""
        chain = []
        current = role
        
        while current:
            role_def = DEFAULT_ROLE_DEFINITIONS.get(current)
            if role_def and permission in role_def.permission_set.permissions:
                chain.append(current)
            current = self._role_inheritance.get_parent(current)
        
        return chain
