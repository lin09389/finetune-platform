from abc import ABC, abstractmethod
from typing import Any

from ..types import ParseResult


class BaseParser(ABC):
    @abstractmethod
    async def parse(self, message: str, context: dict[str, Any] | None = None) -> ParseResult:
        pass

    @abstractmethod
    async def extract_params(self, message: str) -> dict[str, Any]:
        pass

    @abstractmethod
    async def detect_multi_intent(self, message: str) -> list[ParseResult]:
        pass

    def get_supported_intents(self) -> list[str]:
        return []

    def get_confidence_threshold(self) -> float:
        return 0.5
