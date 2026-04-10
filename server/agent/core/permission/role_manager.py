import json
import logging
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from .rbac import (
    ROLE_PERMISSIONS,
    Permission,
    Role,
    RoleDefinition,
    get_role_definition,
    get_role_permissions,
)

logger = logging.getLogger(__name__)


class UserRoleAssignment(BaseModel):
    user_id: str
    role: Role
    assigned_at: datetime = Field(default_factory=datetime.now)
    assigned_by: str | None = None
    expires_at: datetime | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class RoleManager:
    DEFAULT_ROLE: Role = Role.STANDARD_USER

    def __init__(self, storage_path: Path | None = None):
        self.storage_path = storage_path or Path("data/role_assignments")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self._assignments: dict[str, UserRoleAssignment] = {}
        self._custom_roles: dict[Role, RoleDefinition] = {}
        self._load_assignments()

    def assign_role(
        self,
        user_id: str,
        role: Role,
        assigned_by: str | None = None,
        expires_at: datetime | None = None,
        metadata: dict[str, str] | None = None,
    ) -> UserRoleAssignment:
        assignment = UserRoleAssignment(
            user_id=user_id,
            role=role,
            assigned_by=assigned_by,
            expires_at=expires_at,
            metadata=metadata or {},
        )

        self._assignments[user_id] = assignment
        self._save_assignment(assignment)

        logger.info(f"Assigned role {role.value} to user {user_id}")
        return assignment

    def get_user_role(self, user_id: str) -> Role:
        assignment = self._assignments.get(user_id)

        if assignment:
            if assignment.expires_at and datetime.now() > assignment.expires_at:
                self.remove_role(user_id)
                return self.DEFAULT_ROLE
            return assignment.role

        return self.DEFAULT_ROLE

    def get_user_permissions(self, user_id: str) -> set[Permission]:
        role = self.get_user_role(user_id)
        return get_role_permissions(role)

    def remove_role(self, user_id: str) -> bool:
        if user_id in self._assignments:
            del self._assignments[user_id]
            self._delete_assignment(user_id)
            logger.info(f"Removed role assignment for user {user_id}")
            return True
        return False

    def get_assignment(self, user_id: str) -> UserRoleAssignment | None:
        assignment = self._assignments.get(user_id)
        if assignment and assignment.expires_at and datetime.now() > assignment.expires_at:
            self.remove_role(user_id)
            return None
        return assignment

    def list_assignments(self, role: Role | None = None) -> list[UserRoleAssignment]:
        assignments = list(self._assignments.values())

        valid_assignments = []
        for assignment in assignments:
            if assignment.expires_at and datetime.now() > assignment.expires_at:
                self.remove_role(assignment.user_id)
                continue
            valid_assignments.append(assignment)

        if role:
            valid_assignments = [a for a in valid_assignments if a.role == role]

        return valid_assignments

    def create_custom_role(self, definition: RoleDefinition) -> bool:
        if definition.role in ROLE_PERMISSIONS:
            logger.warning(f"Cannot override built-in role: {definition.role}")
            return False

        self._custom_roles[definition.role] = definition
        logger.info(f"Created custom role: {definition.role}")
        return True

    def get_role_definition(self, role: Role) -> RoleDefinition | None:
        if role in self._custom_roles:
            return self._custom_roles[role]
        return get_role_definition(role)

    def get_inheritance_chain(self, role: Role) -> list[Role]:
        chain = [role]
        current_role: Role | None = role

        while current_role is not None:
            role_def = self.get_role_definition(current_role)
            if role_def and role_def.inherits_from:
                chain.append(role_def.inherits_from)
                current_role = role_def.inherits_from
            else:
                break

        return chain

    def elevate_role(
        self,
        user_id: str,
        new_role: Role,
        duration_minutes: int | None = None,
        approved_by: str | None = None,
    ) -> UserRoleAssignment | None:
        current_role = self.get_user_role(user_id)

        if not self._can_elevate_to(current_role, new_role):
            logger.warning(
                f"Cannot elevate user {user_id} from {current_role} to {new_role}"
            )
            return None

        expires_at = None
        if duration_minutes:
            from datetime import timedelta
            expires_at = datetime.now() + timedelta(minutes=duration_minutes)

        return self.assign_role(
            user_id=user_id,
            role=new_role,
            assigned_by=approved_by,
            expires_at=expires_at,
            metadata={"elevated_from": current_role.value},
        )

    def _can_elevate_to(self, current: Role, target: Role) -> bool:
        role_hierarchy = {
            Role.GUEST: 0,
            Role.STANDARD_USER: 1,
            Role.POWER_USER: 2,
            Role.ADMIN: 3,
        }
        return role_hierarchy.get(target, 0) > role_hierarchy.get(current, 0)

    def _save_assignment(self, assignment: UserRoleAssignment) -> None:
        file_path = self.storage_path / f"{assignment.user_id}.json"
        try:
            data = assignment.model_dump()
            data["assigned_at"] = assignment.assigned_at.isoformat()
            if assignment.expires_at:
                data["expires_at"] = assignment.expires_at.isoformat()

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save role assignment: {e}")

    def _delete_assignment(self, user_id: str) -> None:
        file_path = self.storage_path / f"{user_id}.json"
        if file_path.exists():
            file_path.unlink()

    def _load_assignments(self) -> None:
        if not self.storage_path.exists():
            return

        for file_path in self.storage_path.glob("*.json"):
            try:
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)

                data["assigned_at"] = datetime.fromisoformat(data["assigned_at"])
                if data.get("expires_at"):
                    data["expires_at"] = datetime.fromisoformat(data["expires_at"])

                assignment = UserRoleAssignment(**data)
                self._assignments[assignment.user_id] = assignment

            except Exception as e:
                logger.error(f"Failed to load assignment from {file_path}: {e}")

    def get_statistics(self) -> dict[str, int]:
        stats = {role.value: 0 for role in Role}

        for assignment in self._assignments.values():
            if assignment.expires_at and datetime.now() > assignment.expires_at:
                continue
            stats[assignment.role.value] = stats.get(assignment.role.value, 0) + 1

        return stats


_role_manager: RoleManager | None = None


def get_role_manager() -> RoleManager:
    global _role_manager
    if _role_manager is None:
        _role_manager = RoleManager()
    return _role_manager
