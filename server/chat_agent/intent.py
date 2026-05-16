from __future__ import annotations

import json
import re
from typing import Any, Literal

from agent_runtime.runner import resolve_saved_provider
from security.encryption import secure_storage


IntentMode = Literal["chat", "agent", "workflow"]
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
        "补丁",
        "搜索项目",
        "写脚本",
        "排查报错",
        "排查问题",
        "运行命令",
        "执行补丁",
    )
    workflow_keywords = (
        "workflow",
        "工作流",
        "编排",
        "分阶段",
        "stage",
        "node",
        "流程",
        "审批流",
        "任务流",
        "多阶段",
    )
    discussion_only_keywords = ("不要执行", "只讨论", "只分析", "解释一下", "帮我解释", "什么是", "为什么")

    def classify(self, content: str, force_agent: bool = False) -> tuple[bool, str]:
        text = content.strip().lower()
        if force_agent:
            return True, "manual_agent"
        if not text:
            return False, "empty"
        if any(keyword in text for keyword in self.discussion_only_keywords):
            return False, "chat"
        if any(keyword in text for keyword in self.workflow_keywords):
            return True, "workflow_work"
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
        if any(keyword in text for keyword in self.workflow_keywords):
            return self._decision("workflow", 0.9, "本地规则识别为流程编排、阶段控制或多步骤任务。", "local_rule", agent_id, template_id)
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
                        "你是聊天到开发 Agent 的意图路由器。\n"
                        "规则：只输出纯 JSON 对象，不要输出任何解释、markdown 或代码块。\n"
                        "示例输出：{\"mode\": \"chat\", \"confidence\": 0.9, \"reason\": \"概念讨论\", "
                        "\"suggested_agent_id\": null, \"suggested_template_id\": null}\n"
                        "工作流适合：编排、阶段、节点、审批流、多步骤任务。"
                        "Agent 适合：修改代码、搜索项目、生成补丁、运行测试、排查报错。"
                        "普通聊天适合：概念解释、方案讨论、无需操作文件的问题。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"默认 agent_id: {agent_id}\n默认 template_id: {template_id}\n"
                        f"用户输入：{content}\n\n"
                        "请输出 JSON，包含字段：mode(chat 或 agent 或 workflow), confidence(0-1 数字), "
                        "reason(字符串), suggested_agent_id(字符串或 null), suggested_template_id(字符串或 null)"
                    ),
                },
            ],
            model=selected_model,
            api_key=api_key,
            temperature=0,
            max_tokens=300,
        )
        raw_text = str(response.get("content") or "")
        parsed = self._try_parse_json_object(raw_text)
        if parsed is None:
            # 解析失败时，用关键词兜底判断（不上报为错误）
            is_agent, reason = self.classify(content)
            return self._decision(
                "agent" if is_agent else "chat",
                0.6,
                f"云端返回非 JSON，已用本地规则兜底判断。原始响应：{raw_text[:80]}",
                "fallback",
                agent_id if is_agent else None,
                template_id,
            )
        mode = parsed.get("mode")
        if mode not in {"chat", "agent", "workflow"}:
            # mode 字段非法时也做兜底
            is_agent, _ = self.classify(content)
            return self._decision(
                "agent" if is_agent else "chat",
                0.55,
                f"云端返回 mode 无效（{mode!r}），已用本地规则兜底。",
                "fallback",
                agent_id if is_agent else None,
                template_id,
            )

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

        keys = secure_storage.list_keys()
        for key in sorted(keys):
            if key.startswith("cloud_") and key.endswith("_key"):
                provider_id = key.removeprefix("cloud_").removesuffix("_key")
                key_data = secure_storage.get(key) or {}
                if isinstance(key_data, dict) and key_data.get("api_key"):
                    return provider_id, key_data
        raise RuntimeError("未找到已保存的云端 API 配置")

    def _try_parse_json_object(self, content: str) -> dict[str, Any] | None:
        """尝试从文本中提取 JSON 对象，失败返回 None 而非抛异常。"""
        text = content.strip()
        if not text:
            return None
        # 1. 先试 markdown 代码块
        fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
        if fence:
            try:
                parsed = json.loads(fence.group(1))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        # 2. 尝试直接解析整段
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        # 3. 提取最外层 {} 块（非贪婪，取第一个合法 JSON 对象）
        for match in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL):
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
        return None

    def _parse_json_object(self, content: str) -> dict[str, Any]:
        """旧接口兼容，失败时抛异常。"""
        result = self._try_parse_json_object(content)
        if result is None:
            raise ValueError("云端返回不是 JSON 对象")
        return result

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
