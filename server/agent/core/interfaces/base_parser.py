from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..types import ParseResult


class BaseParser(ABC):
    @abstractmethod
    async def parse(self, message: str, context: Optional[Dict[str, Any]] = None) -> ParseResult:
        pass

    @abstractmethod
    async def extract_params(self, message: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def detect_multi_intent(self, message: str) -> List[ParseResult]:
        pass

    def get_supported_intents(self) -> List[str]:
        return []

    def get_confidence_threshold(self) -> float:
        return 0.5
