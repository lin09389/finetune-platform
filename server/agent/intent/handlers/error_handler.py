"""
意图检测处理器 - 错误处理

处理意图检测过程中的错误
"""
import logging
from typing import Any

from ..models import DetectionMethod, IntentResult

logger = logging.getLogger(__name__)


class ErrorHandler:
    """错误处理器"""

    ERROR_MESSAGES = {
        "model_not_loaded": "意图检测模型未加载，请检查模型文件",
        "invalid_input": "输入内容无效，请提供有效的文本",
        "detection_failed": "意图检测失败，请稍后重试",
        "param_extraction_failed": "参数提取失败",
        "unknown_intent": "无法识别您的意图，请尝试更明确的表达",
        "dangerous_operation": "此操作可能存在风险，请确认后执行",
    }

    SUGGESTIONS = {
        "file_operation": [
            "创建文件：创建一个 test.py 文件",
            "读取文件：读取 config.json",
            "删除文件：删除 test.py",
        ],
        "app_control": [
            "打开应用：打开 VS Code",
            "关闭应用：关闭 Chrome",
        ],
        "cua_operation": [
            "截图：截取屏幕",
            "点击：点击坐标 100,200",
            "输入：输入 \"Hello World\"",
        ],
    }

    def __init__(self):
        pass

    def handle_error(
        self,
        error_type: str,
        original_input: str | None = None,
        details: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        error_message = self.ERROR_MESSAGES.get(error_type, "未知错误")

        suggestions = self._get_suggestions_for_error(error_type)

        error_info = {
            "error_type": error_type,
            "message": error_message,
            "suggestions": suggestions,
            "original_input": original_input,
            "details": details or {},
        }

        logger.warning(f"意图检测错误: {error_type} - {error_message}")

        return error_info

    def create_error_result(
        self,
        error_type: str,
        original_input: str | None = None,
        session_id: str | None = None
    ) -> IntentResult:
        error_info = self.handle_error(error_type, original_input)

        return IntentResult(
            detected=False,
            intent_type="error",
            action="",
            params={},
            description=error_info["message"],
            confidence=0.0,
            method=DetectionMethod.RULE,
            need_confirm=False,
            alternatives=[],
            raw_match=original_input or "",
            session_id=session_id,
        )

    def _get_suggestions_for_error(self, error_type: str) -> list[str]:
        if error_type == "unknown_intent":
            suggestions = []
            for category_suggestions in self.SUGGESTIONS.values():
                suggestions.extend(category_suggestions[:2])
            return suggestions[:6]

        if error_type == "model_not_loaded":
            return [
                "请检查模型文件是否存在",
                "请确保已安装必要的依赖",
            ]

        return []

    def log_detection_error(
        self,
        error: Exception,
        context: dict[str, Any] | None = None
    ):
        error_info = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context or {},
        }

        logger.error(f"意图检测异常: {error_info}")

        return error_info


error_handler = ErrorHandler()
