from abc import ABC, abstractmethod
from typing import Any

from ..types import PermissionResult


class BasePermissionController(ABC):
    @abstractmethod
    async def check_permission(
        self, user_role: str, action: str, params: dict[str, Any]
    ) -> PermissionResult:
        pass

    @abstractmethod
    async def require_verification(self, action: str, params: dict[str, Any]) -> bool:
        pass

    @abstractmethod
    async def get_allowed_paths(self, user_role: str) -> list[str]:
        pass

    def get_role_permissions(self, user_role: str) -> dict[str, Any]:
        return {}

    def get_risk_level(self, action: str) -> str:
        return "low"
