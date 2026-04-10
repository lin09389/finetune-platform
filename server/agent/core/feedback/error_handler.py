import traceback
from datetime import datetime
from enum import Enum
from typing import Any

from ..interfaces.base_feedback import BaseFeedback
from ..types import ErrorCode, ErrorResult, ExecutionResult, FormattedResult, ProgressInfo


class ErrorCategory(str, Enum):
    PERMISSION = "permission"
    RESOURCE = "resource"
    PARAMETER = "parameter"
    SYSTEM = "system"
    NETWORK = "network"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class ErrorHandler(BaseFeedback):
    def __init__(self, language: str = "zh_CN"):
        self.language = language
        self._progress_store: dict[str, ProgressInfo] = {}

        self._error_messages = {
            "zh_CN": {
                "permission": "Permission Error",
                "resource": "Resource Error",
                "parameter": "Parameter Error",
                "system": "System Error",
                "network": "Network Error",
                "timeout": "Timeout Error",
                "unknown": "Unknown Error",
                "permission_denied": "You do not have permission to perform this operation",
                "file_not_found": "The specified file or directory was not found",
                "insufficient_memory": "Insufficient memory",
                "invalid_parameter": "Invalid parameter",
                "network_connection_failed": "Network connection failed",
                "operation_timeout": "Operation timed out",
                "internal_error": "Internal error",
                "suggestion_check_permission": "Please check your permission settings",
                "suggestion_check_path": "Please verify the file path",
                "suggestion_free_memory": "Please free up some memory and try again",
                "suggestion_check_params": "Please check the input parameters",
                "suggestion_check_network": "Please check your network connection",
                "suggestion_increase_timeout": "Please increase the timeout or try again later",
                "suggestion_contact_support": "Please contact technical support",
                "suggestion_retry": "Please try again later",
            },
            "en_US": {
                "permission": "Permission Error",
                "resource": "Resource Error",
                "parameter": "Parameter Error",
                "system": "System Error",
                "network": "Network Error",
                "timeout": "Timeout Error",
                "unknown": "Unknown Error",
                "permission_denied": "You do not have permission to perform this operation",
                "file_not_found": "The specified file or directory was not found",
                "insufficient_memory": "Insufficient memory",
                "invalid_parameter": "Invalid parameter",
                "network_connection_failed": "Network connection failed",
                "operation_timeout": "Operation timed out",
                "internal_error": "Internal error",
                "suggestion_check_permission": "Please check your permission settings",
                "suggestion_check_path": "Please verify the file path",
                "suggestion_free_memory": "Please free up some memory and try again",
                "suggestion_check_params": "Please check the input parameters",
                "suggestion_check_network": "Please check your network connection",
                "suggestion_increase_timeout": "Please increase the timeout or try again later",
                "suggestion_contact_support": "Please contact technical support",
                "suggestion_retry": "Please try again later",
            }
        }

    async def handle_error(self, error: Exception) -> ErrorResult:
        category = self._categorize_error(error)
        error_code = self._map_to_error_code(error, category)
        message = self._generate_user_message(error, category)
        details = self._extract_error_details(error)
        recoverable = self._is_recoverable(error, category)
        suggestions = self._generate_suggestions(error, category)

        return ErrorResult(
            error_code=error_code,
            message=message,
            details=details,
            recoverable=recoverable,
            recovery_suggestions=suggestions
        )

    def _categorize_error(self, error: Exception) -> ErrorCategory:
        error_name = type(error).__name__.lower()
        error_message = str(error).lower()

        if "permission" in error_name or "access" in error_name or "forbidden" in error_name:
            return ErrorCategory.PERMISSION

        if "filenotfound" in error_name or "notfound" in error_name:
            return ErrorCategory.RESOURCE

        if "memory" in error_message or "oom" in error_message:
            return ErrorCategory.RESOURCE

        if "value" in error_name or "type" in error_name or "parameter" in error_message:
            return ErrorCategory.PARAMETER

        if "network" in error_message or "connection" in error_message:
            return ErrorCategory.NETWORK

        if "timeout" in error_name or "timeout" in error_message:
            return ErrorCategory.TIMEOUT

        return ErrorCategory.SYSTEM

    def _map_to_error_code(self, error: Exception, category: ErrorCategory) -> ErrorCode:
        error_name = type(error).__name__

        error_mapping = {
            "PermissionError": ErrorCode.PERMISSION_DENIED,
            "FileNotFoundError": ErrorCode.RESOURCE_NOT_FOUND,
            "ValueError": ErrorCode.VALIDATION_ERROR,
            "TypeError": ErrorCode.VALIDATION_ERROR,
            "TimeoutError": ErrorCode.TIMEOUT_ERROR,
        }

        if error_name in error_mapping:
            return error_mapping[error_name]

        category_mapping = {
            ErrorCategory.PERMISSION: ErrorCode.PERMISSION_DENIED,
            ErrorCategory.RESOURCE: ErrorCode.RESOURCE_NOT_FOUND,
            ErrorCategory.PARAMETER: ErrorCode.VALIDATION_ERROR,
            ErrorCategory.NETWORK: ErrorCode.INTERNAL_ERROR,
            ErrorCategory.TIMEOUT: ErrorCode.TIMEOUT_ERROR,
            ErrorCategory.SYSTEM: ErrorCode.INTERNAL_ERROR,
        }

        return category_mapping.get(category, ErrorCode.INTERNAL_ERROR)

    def _generate_user_message(self, error: Exception, category: ErrorCategory) -> str:
        messages = self._error_messages.get(self.language, self._error_messages["en_US"])

        error_name = type(error).__name__
        error_message = str(error).lower()

        if "permission" in error_name:
            return messages["permission_denied"]
        if "filenotfound" in error_name:
            return messages["file_not_found"]
        if "memory" in error_message:
            return messages["insufficient_memory"]
        if "value" in error_name or "type" in error_name:
            return messages["invalid_parameter"]
        if "network" in error_message or "connection" in error_message:
            return messages["network_connection_failed"]
        if "timeout" in error_name:
            return messages["operation_timeout"]

        return messages.get(category.value, messages["internal_error"])

    def _extract_error_details(self, error: Exception) -> dict[str, Any]:
        return {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "timestamp": datetime.now().isoformat(),
            "traceback": traceback.format_exc()
        }

    def _is_recoverable(self, error: Exception, category: ErrorCategory) -> bool:
        non_recoverable_categories = {
            ErrorCategory.PERMISSION,
        }

        if category in non_recoverable_categories:
            return False

        return not (
            "critical" in str(error).lower() or "fatal" in str(error).lower()
        )

    def _generate_suggestions(self, error: Exception, category: ErrorCategory) -> list[str]:
        messages = self._error_messages.get(self.language, self._error_messages["en_US"])
        suggestions = []

        if category == ErrorCategory.PERMISSION:
            suggestions.append(messages["suggestion_check_permission"])
        elif category == ErrorCategory.RESOURCE:
            if "memory" in str(error).lower():
                suggestions.append(messages["suggestion_free_memory"])
            else:
                suggestions.append(messages["suggestion_check_path"])
        elif category == ErrorCategory.PARAMETER:
            suggestions.append(messages["suggestion_check_params"])
        elif category == ErrorCategory.NETWORK:
            suggestions.append(messages["suggestion_check_network"])
        elif category == ErrorCategory.TIMEOUT:
            suggestions.append(messages["suggestion_increase_timeout"])
        else:
            suggestions.append(messages["suggestion_retry"])
            suggestions.append(messages["suggestion_contact_support"])

        return suggestions

    async def format_result(self, result: ExecutionResult) -> FormattedResult:
        from .formatter import ResultFormatter
        formatter = ResultFormatter(language=self.language)
        return await formatter.format_result(result)

    async def report_progress(self, task_id: str, progress: float) -> None:
        if task_id in self._progress_store:
            self._progress_store[task_id].progress = progress

    async def get_progress(self, task_id: str) -> ProgressInfo | None:
        return self._progress_store.get(task_id)

    def analyze_error(self, error: Exception) -> dict[str, Any]:
        category = self._categorize_error(error)

        return {
            "category": category.value,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "is_recoverable": self._is_recoverable(error, category),
            "timestamp": datetime.now().isoformat()
        }

    def get_error_category(self, error: Exception) -> ErrorCategory:
        return self._categorize_error(error)

    def get_friendly_message(self, error: Exception) -> str:
        category = self._categorize_error(error)
        return self._generate_user_message(error, category)
