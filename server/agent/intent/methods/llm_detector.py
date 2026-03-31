"""
意图检测方法 - LLM检测器

基于大语言模型的意图检测（Fallback方案）
"""
import asyncio
import json
import logging
from typing import Any

from ..core.patterns import INTENT_PATTERNS
from ..models import ConfidenceLevel, DetectionMethod, IntentCategory, IntentResult

logger = logging.getLogger(__name__)

LLM_INTENT_PROMPT = """你是一个意图识别助手。请分析用户的输入，识别用户想要执行的操作。

可能的意图类型：
{intent_types}

请以JSON格式返回结果：
{{
    "intent_type": "意图类型",
    "action": "具体动作",
    "params": {{参数键值对}},
    "confidence": 0.0-1.0的置信度,
    "description": "意图描述"
}}

用户输入：{user_input}

请直接返回JSON，不要添加其他内容。"""


class LLMDetector:
    """LLM意图检测器"""

    def __init__(self, llm_client: Any | None = None):
        self._llm_client = llm_client
        self._intent_types = list(INTENT_PATTERNS.keys())

    def set_llm_client(self, client: Any):
        self._llm_client = client

    def _build_prompt(self, text: str) -> str:
        intent_list = "\n".join(f"- {k}: {v.description}" for k, v in INTENT_PATTERNS.items())

        return LLM_INTENT_PROMPT.format(
            intent_types=intent_list,
            user_input=text
        )

    def _parse_response(self, response: str, text: str, session_id: str | None = None) -> IntentResult:
        try:
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]

            result = json.loads(response)

            intent_type = result.get("intent_type", "unknown")
            confidence = float(result.get("confidence", 0.5))

            return IntentResult(
                detected=True,
                intent_type=intent_type,
                action=result.get("action", intent_type),
                params=result.get("params", {}),
                description=result.get("description", f"LLM检测: {intent_type}"),
                confidence=confidence,
                confidence_level=ConfidenceLevel.from_score(confidence),
                method=DetectionMethod.LLM,
                category=IntentCategory.UNKNOWN,
                need_confirm=False,
                alternatives=[],
                raw_match=text,
                session_id=session_id
            )
        except json.JSONDecodeError as e:
            logger.warning(f"LLM响应解析失败: {e}")
            return IntentResult(
                detected=False,
                intent_type="unknown",
                action="",
                params={},
                description="LLM响应解析失败",
                confidence=0.0,
                confidence_level=ConfidenceLevel.UNKNOWN,
                method=DetectionMethod.LLM,
                category=IntentCategory.UNKNOWN,
                need_confirm=False,
                alternatives=[],
                raw_match=text,
                session_id=session_id
            )

    def detect(
        self,
        text: str,
        session_id: str | None = None
    ) -> IntentResult | None:
        if self._llm_client is None:
            return None

        try:
            prompt = self._build_prompt(text)

            if hasattr(self._llm_client, 'generate'):
                response = self._llm_client.generate(prompt)
            elif hasattr(self._llm_client, 'chat'):
                response = self._llm_client.chat([{"role": "user", "content": prompt}])
            elif hasattr(self._llm_client, '__call__'):
                response = self._llm_client(prompt)
            else:
                logger.warning("LLM客户端不支持已知的调用方式")
                return None

            return self._parse_response(response, text, session_id)

        except Exception as e:
            logger.error(f"LLM检测失败: {e}")
            return None

    async def detect_async(
        self,
        text: str,
        session_id: str | None = None
    ) -> IntentResult | None:
        if self._llm_client is None:
            return None

        try:
            prompt = self._build_prompt(text)

            if hasattr(self._llm_client, 'generate_async'):
                response = await self._llm_client.generate_async(prompt)
            elif hasattr(self._llm_client, 'chat_async'):
                response = await self._llm_client.chat_async([{"role": "user", "content": prompt}])
            else:
                return await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.detect(text, session_id)
                )

            return self._parse_response(response, text, session_id)

        except Exception as e:
            logger.error(f"LLM异步检测失败: {e}")
            return None


llm_detector = LLMDetector()
