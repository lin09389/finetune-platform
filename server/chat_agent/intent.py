from __future__ import annotations

import json
import re
from typing import Any, Literal

from agent_runtime.runner import resolve_saved_provider
from security.encryption import secure_storage


IntentMode = Literal["chat", "agent"]
IntentSource = Literal["local_rule", "cloud", "fallback", "manual"]


class ChatAgentIntentClassifier:
    """Small deterministic classifier for routing chat messages into agent work."""

    agent_keywords = (
        "修改",
        "新增",
        "实现",
        "修复",
        "重构",
        "优化代码",
        "给当前项目",
        "代码里",
        "页面",
        "接口",
        "组件",
        "后端",
        "前端",
        "跑测试",
        "运行测试",
        "typecheck",
        "pytest",
        "npm run",
        "让agent做",
        "自动处理",
        "帮我改",
        "补丁",
        "执行",
    )
    discussion_only_keywords = ("不要执行", "只讨论", "只分析", "解释一下", "什么是", "为什么")

    def classify(self, content: str, force_agent: bool = False) -> tuple[bool, str]:
        text = content.strip().lower()
        if force_agent:
            return True, "manual_agent"
        if not text:
            return False, "empty"
        if any(keyword in text for keyword in self.discussion_only_keywords):
            return False, "chat"
        if any(keyword in text for keyword in self.agent_keywords):
            return True, "agent_work"
        return False, "chat"

    async def route(
        self,
        content: str,
        *,
        routing_mode: Literal["auto", "chat", "agent"] = "auto",
        provider: str | None = None,
        model: str | None = None,
        agent_id: str | None = None,
        template_id: str | None = None,
    ) -> dict[str, Any]:
        agent_id = agent_id or "build"
        template_id = template_id or "software_delivery"

        if routing_mode == "chat":
            return self._decision("chat", 1.0, "用户选择普通对话模式。", "manual", None, template_id)
        if routing_mode == "agent":
            return self._decision("agent", 1.0, "用户选择 Agent 工作模式。", "manual", agent_id, template_id)

        local = self._local_route(content, agent_id, template_id)
        if local is not None:
            return local

        try:
            return await self._cloud_route(
                content,
                provider=provider,
                model=model,
                agent_id=agent_id,
                template_id=template_id,
            )
        except Exception as exc:
            return self._decision(
                "chat",
                0.45,
                f"云端意图判断失败，已回退到普通对话：{exc}",
                "fallback",
                None,
                template_id,
            )

    def _local_route(
        self,
        content: str,
        agent_id: str,
        template_id: str,
    ) -> dict[str, Any] | None:
        text = content.strip().lower()
        if not text:
            return self._decision("chat", 1.0, "空输入按普通对话处理。", "local_rule", None, template_id)
        if any(keyword in text for keyword in self.discussion_only_keywords):
            return self._decision("chat", 0.92, "本地规则识别为解释或讨论类问题。", "local_rule", None, template_id)
        if any(keyword in text for keyword in self.agent_keywords):
            return self._decision("agent", 0.9, "本地规则识别为开发、修改、测试或执行类目标。", "local_rule", agent_id, template_id)
        return None

    async def _cloud_route(
        self,
        content: str,
        *,
        provider: str | None,
        model: str | None,
        agent_id: str,
        template_id: str,
    ) -> dict[str, Any]:
        provider_id, key_data = self._resolve_provider_data(provider)
        api_key = key_data.get("api_key", "")
        if not api_key:
            raise RuntimeError(f"未配置 {provider_id} 的 API Key")

        provider_instance = resolve_saved_provider(provider_id, key_data)
        if provider_instance is None:
            raise RuntimeError(f"不支持的云端服务商：{provider_id}")

        selected_model = model or key_data.get("default_model") or provider_instance.get_default_model()
        response = await provider_instance.chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是聊天到开发 Agent 的意图路由器。只返回 JSON，不要输出解释文本。"
                        "判断用户输入是否需要进入 Agent 工作。Agent 适合修改代码、搜索项目、生成补丁、运行测试、排查报错；"
                        "普通聊天适合概念解释、方案讨论、无需操作项目文件的问题。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请判断下面输入的处理模式。返回字段："
                        "mode(chat 或 agent), confidence(0-1), reason, suggested_agent_id, suggested_template_id。\n\n"
                        f"默认 agent_id: {agent_id}\n默认 template_id: {template_id}\n用户输入：{content}"
                    ),
                },
            ],
            model=selected_model,
            api_key=api_key,
            temperature=0,
            max_tokens=300,
        )
        parsed = self._parse_json_object(str(response.get("content") or ""))
        mode = parsed.get("mode")
        if mode not in {"chat", "agent"}:
            raise ValueError("云端返回缺少合法 mode")

        confidence = self._safe_confidence(parsed.get("confidence"))
        suggested_agent = parsed.get("suggested_agent_id") or (agent_id if mode == "agent" else None)
        suggested_template = parsed.get("suggested_template_id") or template_id
        return self._decision(
            mode,
            confidence,
            str(parsed.get("reason") or "云端模型完成意图判断。"),
            "cloud",
            str(suggested_agent) if suggested_agent else None,
            str(suggested_template) if suggested_template else None,
        )

    def _resolve_provider_data(self, provider: str | None) -> tuple[str, dict[str, Any]]:
        if provider:
            key_data = secure_storage.get(f"cloud_{provider}_key") or {}
            return provider, key_data

        vault = secure_storage._load_vault()
        for key in sorted(vault):
            if key.startswith("cloud_") and key.endswith("_key"):
                provider_id = key.removeprefix("cloud_").removesuffix("_key")
                key_data = secure_storage.get(key) or {}
                if isinstance(key_data, dict) and key_data.get("api_key"):
                    return provider_id, key_data
        raise RuntimeError("未找到已保存的云端 API 配置")

    def _parse_json_object(self, content: str) -> dict[str, Any]:
        text = content.strip()
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence:
            text = fence.group(1)
        if not text.startswith("{"):
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                text = match.group(0)
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("云端返回不是 JSON 对象")
        return parsed

    def _safe_confidence(self, value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            confidence = 0.6
        return max(0.0, min(1.0, confidence))

    def _decision(
        self,
        mode: IntentMode,
        confidence: float,
        reason: str,
        source: IntentSource,
        suggested_agent_id: str | None,
        suggested_template_id: str | None,
    ) -> dict[str, Any]:
        return {
            "mode": mode,
            "confidence": confidence,
            "reason": reason,
            "source": source,
            "suggested_agent_id": suggested_agent_id,
            "suggested_template_id": suggested_template_id,
        }
