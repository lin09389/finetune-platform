from datetime import datetime
from enum import Enum
from typing import Any

from ..interfaces.base_feedback import BaseFeedback
from ..types import ErrorResult, ExecutionResult, FormattedResult, ProgressInfo


class OutputFormat(str, Enum):
    TEXT = "text"
    JSON = "json"
    MARKDOWN = "markdown"


class Language(str, Enum):
    ZH_CN = "zh_CN"
    EN_US = "en_US"


class ResultFormatter(BaseFeedback):
    def __init__(
        self,
        output_format: OutputFormat = OutputFormat.TEXT,
        language: Language = Language.ZH_CN
    ):
        self.output_format = output_format
        self.language = language
        self._progress_store: dict[str, ProgressInfo] = {}

        self._messages = {
            Language.ZH_CN: {
                "success": "Operation completed successfully",
                "failed": "Operation failed",
                "partial": "Operation partially completed",
                "pending": "Operation pending",
                "cancelled": "Operation cancelled",
                "file_operation": "File Operation",
                "system_control": "System Control",
                "application": "Application",
                "network": "Network Operation",
                "clipboard": "Clipboard Operation",
                "screenshot": "Screenshot",
                "unknown": "Unknown Operation",
                "execution_time": "Execution time",
                "seconds": "seconds",
                "no_output": "No output result",
                "suggestion_prefix": "Suggestion",
            },
            Language.EN_US: {
                "success": "Operation completed successfully",
                "failed": "Operation failed",
                "partial": "Operation partially completed",
                "pending": "Operation pending",
                "cancelled": "Operation cancelled",
                "file_operation": "File Operation",
                "system_control": "System Control",
                "application": "Application",
                "network": "Network Operation",
                "clipboard": "Clipboard Operation",
                "screenshot": "Screenshot",
                "unknown": "Unknown Operation",
                "execution_time": "Execution time",
                "seconds": "seconds",
                "no_output": "No output result",
                "suggestion_prefix": "Suggestion",
            }
        }

    async def format_result(self, result: ExecutionResult) -> FormattedResult:
        messages = self._messages[self.language]

        status_messages = {
            "success": messages["success"],
            "failed": messages["failed"],
            "partial": messages["partial"],
            "pending": messages["pending"],
            "cancelled": messages["cancelled"],
        }

        base_message = status_messages.get(result.status.value, messages["unknown"])

        if self.output_format == OutputFormat.JSON:
            formatted_data = self._format_as_json(result)
            message = base_message
        elif self.output_format == OutputFormat.MARKDOWN:
            formatted_data = self._format_as_markdown(result)
            message = base_message
        else:
            formatted_data = self._format_as_text(result)
            message = base_message

        suggestions = self._generate_suggestions(result)
        follow_up_actions = self._generate_follow_up_actions(result)

        return FormattedResult(
            success=result.status.value == "success",
            message=message,
            data=formatted_data,
            suggestions=suggestions,
            follow_up_actions=follow_up_actions
        )

    def _format_as_text(self, result: ExecutionResult) -> dict[str, Any]:
        messages = self._messages[self.language]

        lines = []
        lines.append(f"[{result.action}]")
        lines.append(f"Status: {result.status.value}")

        if result.output is not None:
            if isinstance(result.output, dict):
                for key, value in result.output.items():
                    lines.append(f"{key}: {value}")
            elif isinstance(result.output, list):
                for item in result.output:
                    lines.append(str(item))
            else:
                lines.append(str(result.output))
        else:
            lines.append(messages["no_output"])

        lines.append(f"{messages['execution_time']}: {result.execution_time_ms / 1000:.2f} {messages['seconds']}")

        return {"text": "\n".join(lines)}

    def _format_as_json(self, result: ExecutionResult) -> dict[str, Any]:
        return {
            "action": result.action,
            "status": result.status.value,
            "output": result.output,
            "execution_time_ms": result.execution_time_ms,
            "timestamp": datetime.now().isoformat(),
            "metadata": result.metadata
        }

    def _format_as_markdown(self, result: ExecutionResult) -> dict[str, Any]:
        messages = self._messages[self.language]

        lines = []
        lines.append(f"## {result.action}")
        lines.append("")
        lines.append(f"**Status**: `{result.status.value}`")
        lines.append("")

        if result.output is not None:
            lines.append("### Output")
            lines.append("")
            if isinstance(result.output, dict):
                lines.append("```json")
                import json
                lines.append(json.dumps(result.output, indent=2, ensure_ascii=False))
                lines.append("```")
            elif isinstance(result.output, list):
                for item in result.output:
                    lines.append(f"- {item}")
            else:
                lines.append(str(result.output))
        else:
            lines.append(f"*{messages['no_output']}*")

        lines.append("")
        lines.append(f"> {messages['execution_time']}: {result.execution_time_ms / 1000:.2f} {messages['seconds']}")

        return {"markdown": "\n".join(lines)}

    def _generate_suggestions(self, result: ExecutionResult) -> list[str]:
        messages = self._messages[self.language]
        suggestions = []

        if result.status.value == "failed":
            suggestions.append(f"{messages['suggestion_prefix']}: Check the error message and retry")
            if result.error_code:
                suggestions.append(f"Error code: {result.error_code.value}")

        if result.execution_time_ms > 5000:
            suggestions.append("Consider optimizing the operation for better performance")

        return suggestions

    def _generate_follow_up_actions(self, result: ExecutionResult) -> list[str]:
        actions = []

        if result.status.value == "success":
            actions.append("view_result")
            actions.append("export_result")
        elif result.status.value == "failed":
            actions.append("retry")
            actions.append("view_logs")
        elif result.status.value == "partial":
            actions.append("continue")
            actions.append("view_details")

        return actions

    async def report_progress(self, task_id: str, progress: float) -> None:
        if task_id in self._progress_store:
            self._progress_store[task_id].progress = progress

    async def handle_error(self, error: Exception) -> ErrorResult:
        from .error_handler import ErrorHandler
        handler = ErrorHandler(language=self.language)
        return await handler.handle_error(error)

    async def get_progress(self, task_id: str) -> ProgressInfo | None:
        return self._progress_store.get(task_id)

    def get_supported_formats(self) -> list[str]:
        return ["text", "json", "markdown"]

    def set_output_format(self, output_format: OutputFormat) -> None:
        self.output_format = output_format

    def set_language(self, language: Language) -> None:
        self.language = language
