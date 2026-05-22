from __future__ import annotations

import json
import re
from typing import Any, Literal

from ai.providers import resolve_saved_provider
from security.encryption import secure_storage


IntentMode = Literal["chat", "agent"]
IntentSource = Literal["local_rule", "cloud", "fallback", "manual"]


class ChatAgentIntentClassifier:
    """Small deterministic classifier for routing chat messages into agent work."""

    agent_keywords = (
        # 明确指向项目代码修改的词组
        "修改代码",
        "新增功能",
        "新增接口",
        "新增页面",
        "实现功能",
        "实现接口",
        "修复bug",
        "修复报错",
        "重构代码",
        "优化代码",
        # 测试 / 工具命令
        "跑测试",
        "运行测试",
        "typecheck",
        "pytest",
        "npm run",
        # agent 操作
        "让agent做",
        "自动处理",
        "生成补丁",
        "写补丁",
        "搜索项目",
        "写脚本",
        "排查报错",
        "排查问题",
        "运行命令",
        "执行补丁",
        # 帮我+动词（带项目意图）
        "帮我改",
        "帮我修",
        "帮我写",
        "帮我实现",
        "帮我新增",
        "帮我添加",
        "帮我重构",
        # 明确的修改指令
        "改成",
        "改为",
        "加个",
        "加一个",
    )
    discussion_only_keywords = (
        "不要执行", "只讨论", "只分析", "解释一下", "帮我解释", "什么是", "为什么",
        "怎么理解", "怎么用", "是什么意思", "有什么区别", "介绍一下", "帮我看看",
        "分析一下", "看看代码", "这个代码", "这段代码", "看看逻辑", "怎么实现的",
        "原理是什么", "怎么工作的", "帮我梳理", "帮我看看代码",
        # 示例 / demo 类请求应走普通对话
        "示例", "例子", "demo", "演示", "sample", "写一个例子", "给个例子",
        "给我一个例子", "给我示例", "给我一段", "怎么写", "如何写",
    )

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
    ) -> dict[str, Any]:
        agent_id = agent_id or "build"

        if routing_mode == "chat":
            return self._decision("chat", 1.0, "用户选择普通对话模式。", "manual", None)
        if routing_mode == "agent":
            return self._decision("agent", 1.0, "用户选择 Agent 工作模式。", "manual", agent_id)

        local = self._local_route(content, agent_id)
        if local is not None:
            return local

        try:
            return await self._cloud_route(
                content,
                provider=provider,
                model=model,
                agent_id=agent_id,
            )
        except Exception as exc:
            is_agent, reason = self.classify(content)
            return self._decision(
                "agent" if is_agent else "chat",
                0.6 if is_agent else 0.45,
                f"云端意图判断失败，已用本地规则回退：{exc}",
                "fallback",
                agent_id if is_agent else None,
            )

    def _local_route(
        self,
        content: str,
        agent_id: str,
    ) -> dict[str, Any] | None:
        text = content.strip().lower()
        if not text:
            return self._decision("chat", 1.0, "空输入按普通对话处理。", "local_rule", None)
        if any(keyword in text for keyword in self.discussion_only_keywords):
            return self._decision("chat", 0.92, "本地规则识别为解释或讨论类问题。", "local_rule", None)
        if any(keyword in text for keyword in self.agent_keywords):
            return self._decision("agent", 0.9, "本地规则识别为开发、修改、测试或执行类目标。", "local_rule", agent_id)
        return None

    async def _cloud_route(
        self,
        content: str,
        *,
        provider: str | None,
        model: str | None,
        agent_id: str,
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
                        "你是一个意图分类器。判断用户输入应该走哪条路径，只输出一个 JSON 对象。\n\n"
                        "两种模式：\n"
                        "- chat：用户在讨论、提问、咨询，不需要修改任何文件或执行任何命令\n"
                        "- agent：用户需要执行具体操作（修改文件、运行命令、创建代码等）\n\n"
                        "判断规则：\n"
                        "1. 如果用户在问「是什么」「为什么」「怎么理解」「有什么区别」→ chat\n"
                        "2. 如果用户在问「怎么做」但没有明确要求你去执行 → chat\n"
                        "3. 如果用户说「帮我改」「帮我修」「帮我写」「帮我实现」「帮我新增」「帮我添加」→ agent\n"
                        "4. 如果用户说「修改XX文件」「修复XX bug」「运行测试」「生成补丁」→ agent\n"
                        "5. 如果用户说「不要执行」「只讨论」「只分析」「解释一下」→ chat\n\n"
                        "示例：\n"
                        "用户：「这个函数的作用是什么」→ {\"mode\":\"chat\",\"confidence\":0.95,\"reason\":\"询问代码功能\",\"suggested_agent_id\":null}\n"
                        "用户：「帮我修复登录页面的 bug」→ {\"mode\":\"agent\",\"confidence\":0.92,\"reason\":\"要求修复bug\",\"suggested_agent_id\":\"build\"}\n"
                        "用户：「这段代码的性能瓶颈在哪」→ {\"mode\":\"chat\",\"confidence\":0.9,\"reason\":\"性能分析讨论\",\"suggested_agent_id\":null}\n"
                        "用户：「帮我优化这段代码的性能」→ {\"mode\":\"agent\",\"confidence\":0.88,\"reason\":\"要求优化代码\",\"suggested_agent_id\":\"build\"}\n"
                        "用户：「运行 npm run typecheck 看看有没有问题」→ {\"mode\":\"agent\",\"confidence\":0.9,\"reason\":\"要求运行命令\",\"suggested_agent_id\":\"build\"}\n"
                        "用户：「什么是 LoRA 微调」→ {\"mode\":\"chat\",\"confidence\":0.95,\"reason\":\"概念解释\",\"suggested_agent_id\":null}\n\n"
                        "严格要求：只输出 JSON，不要输出任何其他文字、markdown 或代码块标记。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"用户输入：{content}\n\n"
                        f"默认 agent_id: {agent_id}\n\n"
                        "请判断用户意图，输出 JSON：\n"
                        "{\"mode\": \"chat|agent\", \"confidence\": 0.0-1.0, \"reason\": \"判断原因\", "
                        "\"suggested_agent_id\": \"字符串或null\"}"
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
            is_agent, reason = self.classify(content)
            return self._decision(
                "agent" if is_agent else "chat",
                0.6,
                f"云端返回非 JSON，已用本地规则兜底判断。原始响应：{raw_text[:80]}",
                "fallback",
                agent_id if is_agent else None,
            )
        mode = parsed.get("mode")
        if mode not in {"chat", "agent"}:
            is_agent, _ = self.classify(content)
            return self._decision(
                "agent" if is_agent else "chat",
                0.55,
                f"云端返回 mode 无效（{mode!r}），已用本地规则兜底。",
                "fallback",
                agent_id if is_agent else None,
            )

        confidence = self._safe_confidence(parsed.get("confidence"))
        suggested_agent = parsed.get("suggested_agent_id") or (agent_id if mode == "agent" else None)
        return self._decision(
            mode,
            confidence,
            str(parsed.get("reason") or "云端模型完成意图判断。"),
            "cloud",
            str(suggested_agent) if suggested_agent else None,
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
    ) -> dict[str, Any]:
        return {
            "mode": mode,
            "confidence": confidence,
            "reason": reason,
            "source": source,
            "suggested_agent_id": suggested_agent_id,
        }
