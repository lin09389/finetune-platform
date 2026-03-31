"""
意图检测方法 - LLM 意图理解

使用大语言模型进行语义级别的意图理解
"""
import json
import logging
from typing import Any

from ..models import ConfidenceLevel, DetectionMethod, IntentCategory, IntentResult

logger = logging.getLogger(__name__)

LLM_INTENT_PROMPT = """你是一个智能意图识别与任务规划助手。请分析用户的输入，理解用户的真实意图。如果用户提出了一个复杂任务，请将其拆解为多个步骤。

## 意图分类

### 1. 对话意图 (conversation)
用户想要进行对话、聊天、提问，而不是执行具体操作：
- 问候：你好、hi、hello
- 感谢：谢谢、thanks
- 提问：请问...、我想问...
- 能力询问：你能做什么？
- 闲聊：今天天气怎么样？
- 编程帮助：帮我写一个函数、帮我看看这段代码

### 2. 操作意图 (action)
用户想要执行具体的操作，包括但不限于：
- 文件操作 (file_operation): file_create, file_read, file_write, file_delete, file_list
- 应用控制 (app_control): app_open, app_close
- 浏览器操作 (browser_operation): url_open
- 系统操作 (system_operation): screenshot, mouse_click, keyboard_type, window_list, window_activate

## 分析要求

1. 理解用户输入的语义，不要只看关键词。
2. 对于复杂请求，请将其拆解为逻辑连贯的操作序列。例如：“帮我读取 README.md 并在 summary.txt 中总结内容” 应该拆解为 `file_read` 和 `file_write`（总结内容由你生成并作为参数传入）。
3. 如果不确定，倾向于判断为对话意图。

## 返回格式

请以 JSON 格式返回一个包含一个或多个意图的列表：

```json
{
    "intents": [
        {
            "intent_type": "conversation 或 action",
            "action": "具体操作类型（如果是操作意图）",
            "params": {"参数名": "参数值"},
            "confidence": 0.0-1.0,
            "description": "意图描述",
            "reasoning": "判断理由"
        }
    ]
}
```

## 用户输入
{user_input}

请直接返回 JSON，不要添加其他内容。"""


class LLMIntentUnderstanding:
    """LLM 意图理解器"""

    def __init__(self, llm_client: Any | None = None):
        self._llm_client = llm_client

    def set_llm_client(self, client: Any):
        self._llm_client = client

    def understand(self, text: str, session_id: str | None = None) -> list[IntentResult]:
        """使用 LLM 理解用户意图（支持多意图）"""
        if not self._llm_client:
            return []

        try:
            prompt = LLM_INTENT_PROMPT.format(user_input=text)

            response = self._call_llm(prompt)

            if not response:
                return []

            return self._parse_multi_response(response, text, session_id)

        except Exception as e:
            logger.warning(f"LLM 意图理解失败: {e}")
            return []

    def _call_llm(self, prompt: str) -> str | None:
        """调用 LLM"""
        try:
            if hasattr(self._llm_client, 'chat'):
                response = self._llm_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=800
                )
                return response.choices[0].message.content
            elif hasattr(self._llm_client, 'generate'):
                return self._llm_client.generate(prompt)
            elif callable(self._llm_client):
                return self._llm_client(prompt)
            else:
                logger.warning("未知的 LLM 客户端类型")
                return None
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return None

    def _parse_multi_response(self, response: str, text: str, session_id: str | None) -> list[IntentResult]:
        """解析 LLM 返回的多意图响应"""
        try:
            response = response.strip()
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()

            data = json.loads(response)
            intents_data = data.get("intents", [])
            
            # 兼容单对象格式
            if not isinstance(intents_data, list) and isinstance(data, dict) and "intent_type" in data:
                intents_data = [data]

            results = []
            for result in intents_data:
                intent_type = result.get("intent_type", "conversation")
                confidence = float(result.get("confidence", 0.8))
                action = result.get("action", "")
                params = result.get("params", {})

                res = IntentResult(
                    detected=(intent_type == "action"),
                    intent_type=action if intent_type == "action" else "conversation",
                    action=action if intent_type == "action" else None,
                    params=params,
                    description=result.get("description", ""),
                    confidence=confidence,
                    confidence_level=ConfidenceLevel.from_score(confidence),
                    method=DetectionMethod.LLM,
                    category=self._get_category(action) if intent_type == "action" else IntentCategory.CONVERSATION,
                    need_confirm=False,
                    alternatives=[],
                    raw_match=text,
                    session_id=session_id
                )
                results.append(res)
            
            return results

        except Exception as e:
            logger.warning(f"LLM 多意图响应解析失败: {e}")
            return []

    def understand_single(self, text: str, session_id: str | None = None) -> IntentResult | None:
        """保持原有接口，返回得分最高的单个意图"""
        results = self.understand(text, session_id)
        return results[0] if results else None

    def _get_category(self, action: str) -> IntentCategory:
        """根据 action 获取类别"""
        if action.startswith("file_"):
            return IntentCategory.FILE_OPERATION
        elif action.startswith("app_"):
            return IntentCategory.APP_CONTROL
        elif action in ["url_open", "browser_open"]:
            return IntentCategory.BROWSER_OPERATION
        elif action in ["screenshot", "mouse_click", "keyboard_type"]:
            return IntentCategory.CUA_OPERATION
        else:
            return IntentCategory.UNKNOWN


llm_intent_understanding = LLMIntentUnderstanding()
