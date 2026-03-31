"""
意图检测处理器 - 澄清对话处理

处理意图不明确时的澄清对话
"""
import logging
from typing import Any

from ..core.patterns import get_intent_definition
from ..models import ConfidenceLevel, IntentResult

logger = logging.getLogger(__name__)


class ClarificationHandler:
    """澄清对话处理器"""

    CLARIFICATION_TEMPLATES = {
        "file_path": {
            "question": "请问您要操作哪个文件？",
            "examples": ["例如：test.py", "例如：config.json"],
        },
        "app_name": {
            "question": "请问您要打开哪个应用？",
            "examples": ["例如：VS Code", "例如：Chrome"],
        },
        "url": {
            "question": "请问您要访问哪个网址？",
            "examples": ["例如：https://www.example.com"],
        },
        "content": {
            "question": "请问您要写入什么内容？",
            "examples": [],
        },
        "directory": {
            "question": "请问您要操作哪个目录？",
            "examples": ["例如：/home/user", "例如：C:\\Users"],
        },
        "text": {
            "question": "请问您要输入什么内容？",
            "examples": [],
        },
        "pattern": {
            "question": "请问您要搜索什么？",
            "examples": ["例如：*.py", "例如：config"],
        },
    }

    AMBIGUITY_TEMPLATES = {
        "multiple_intents": "您是想 {option1} 还是 {option2}？",
        "low_confidence": "我不太确定您的意思，您是想 {suggestion} 吗？",
    }

    def __init__(self):
        pass

    def needs_clarification(self, result: IntentResult) -> bool:
        if not result.detected:
            return True

        if result.confidence_level == ConfidenceLevel.LOW:
            return True

        intent_def = get_intent_definition(result.intent_type)
        if intent_def:
            for param in intent_def.required_params:
                if param not in result.params or not result.params[param]:
                    return True

        return False

    def get_missing_params(self, result: IntentResult) -> list[str]:
        missing = []
        intent_def = get_intent_definition(result.intent_type)

        if intent_def:
            for param in intent_def.required_params:
                if param not in result.params or not result.params[param]:
                    missing.append(param)

        return missing

    def create_clarification(
        self,
        result: IntentResult,
        alternatives: list[IntentResult] | None = None
    ) -> dict[str, Any]:
        if not result.detected:
            return {
                "type": "unknown_intent",
                "question": "抱歉，我不太理解您的意思，能否请您详细描述一下？",
                "suggestions": self._get_common_suggestions(),
            }

        missing_params = self.get_missing_params(result)

        if missing_params:
            return self._create_param_clarification(result, missing_params)

        if alternatives and len(alternatives) > 1:
            return self._create_ambiguity_clarification(result, alternatives)

        if result.confidence_level == ConfidenceLevel.LOW:
            return self._create_low_confidence_clarification(result)

        return {
            "type": "none",
            "question": None,
            "suggestions": [],
        }

    def _create_param_clarification(
        self,
        result: IntentResult,
        missing_params: list[str]
    ) -> dict[str, Any]:
        first_missing = missing_params[0]
        template = self.CLARIFICATION_TEMPLATES.get(first_missing, {
            "question": f"请提供 {first_missing}",
            "examples": [],
        })

        return {
            "type": "missing_param",
            "param_name": first_missing,
            "intent_type": result.intent_type,
            "question": template["question"],
            "examples": template.get("examples", []),
            "collected_params": result.params,
        }

    def _create_ambiguity_clarification(
        self,
        result: IntentResult,
        alternatives: list[IntentResult]
    ) -> dict[str, Any]:
        top_two = alternatives[:2]

        option1 = self._intent_to_description(top_two[0])
        option2 = self._intent_to_description(top_two[1]) if len(top_two) > 1 else ""

        return {
            "type": "ambiguity",
            "question": self.AMBIGUITY_TEMPLATES["multiple_intents"].format(
                option1=option1,
                option2=option2
            ),
            "options": [
                {
                    "intent_type": r.intent_type,
                    "description": self._intent_to_description(r),
                    "params": r.params,
                }
                for r in top_two
            ],
        }

    def _create_low_confidence_clarification(
        self,
        result: IntentResult
    ) -> dict[str, Any]:
        suggestion = self._intent_to_description(result)

        return {
            "type": "low_confidence",
            "question": self.AMBIGUITY_TEMPLATES["low_confidence"].format(
                suggestion=suggestion
            ),
            "suggested_intent": result.intent_type,
            "suggested_params": result.params,
        }

    def _intent_to_description(self, result: IntentResult) -> str:
        intent_def = get_intent_definition(result.intent_type)
        if intent_def:
            return intent_def.description
        return result.description or result.intent_type

    def _get_common_suggestions(self) -> list[dict[str, str]]:
        return [
            {"intent_type": "file_create", "description": "创建文件", "example": "创建一个 test.py 文件"},
            {"intent_type": "file_read", "description": "读取文件", "example": "读取 config.json"},
            {"intent_type": "screenshot", "description": "截图", "example": "截图"},
            {"intent_type": "app_open", "description": "打开应用", "example": "打开 VS Code"},
        ]

    def handle_clarification_response(
        self,
        response: str,
        clarification: dict[str, Any],
        original_result: IntentResult
    ) -> IntentResult:
        if clarification.get("type") == "missing_param":
            param_name = clarification.get("param_name")

            new_params = dict(original_result.params)
            new_params[param_name] = response

            return IntentResult(
                detected=True,
                intent_type=original_result.intent_type,
                action=original_result.action,
                params=new_params,
                description=original_result.description,
                confidence=0.9,
                confidence_level=ConfidenceLevel.HIGH,
                method=original_result.method,
                category=original_result.category,
                need_confirm=False,
                alternatives=[],
                raw_match=original_result.raw_match,
                session_id=original_result.session_id,
            )

        if clarification.get("type") == "ambiguity":
            options = clarification.get("options", [])
            for option in options:
                if option["description"] in response or option["intent_type"] in response:
                    return IntentResult(
                        detected=True,
                        intent_type=option["intent_type"],
                        action=option["intent_type"],
                        params=option.get("params", {}),
                        description=option["description"],
                        confidence=0.95,
                        confidence_level=ConfidenceLevel.HIGH,
                        method=original_result.method,
                        category=original_result.category,
                        need_confirm=False,
                        alternatives=[],
                        raw_match=response,
                        session_id=original_result.session_id,
                    )

        return original_result


clarification_handler = ClarificationHandler()
