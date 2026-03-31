from abc import ABC, abstractmethod
from typing import Any

from ..types import ExecutionResult, ValidationResult


class BaseExecutor(ABC):
    @abstractmethod
    async def execute(self, action: str, params: dict[str, Any]) -> ExecutionResult:
        pass

    @abstractmethod
    async def validate_params(self, action: str, params: dict[str, Any]) -> ValidationResult:
        pass

    @abstractmethod
    def get_supported_actions(self) -> list[str]:
        pass

    def get_action_description(self, action: str) -> str:
        return ""

    def get_required_params(self, action: str) -> list[str]:
        return []

    def get_optional_params(self, action: str) -> list[str]:
        return []
