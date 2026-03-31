from abc import ABC, abstractmethod

from ..types import ErrorResult, ExecutionResult, FormattedResult, ProgressInfo


class BaseFeedback(ABC):
    @abstractmethod
    async def format_result(self, result: ExecutionResult) -> FormattedResult:
        pass

    @abstractmethod
    async def report_progress(self, task_id: str, progress: float) -> None:
        pass

    @abstractmethod
    async def handle_error(self, error: Exception) -> ErrorResult:
        pass

    async def get_progress(self, task_id: str) -> ProgressInfo | None:
        return None

    def get_supported_formats(self) -> list[str]:
        return ["text", "json", "markdown"]
