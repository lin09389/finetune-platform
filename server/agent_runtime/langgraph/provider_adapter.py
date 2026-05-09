"""Provider -> LangChain chat model adapters for LangGraph workflow execution."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from agent_runtime.runner import resolve_saved_provider
from security.encryption import secure_storage

from ..definitions import RuntimeExecutionContext


class ProviderAdapterError(RuntimeError):
    """Raised when a workflow provider cannot be adapted to a chat model."""


class GatewayToolCallingChatModel(BaseChatModel):
    """LangChain chat model backed by the existing gateway provider adapters.

    The upstream gateway providers mostly expose plain chat completion APIs, so this
    wrapper normalizes their outputs into ``AIMessage`` objects and adds a lightweight
    JSON tool-calling protocol for providers without native tool-call support.
    """

    provider_name: str
    model_name: str
    api_key: str
    provider: Any
    temperature: float = 0.2
    max_tokens: int = 2200
    bound_tools: list[dict[str, Any]] = []
    tool_choice: str | None = None

    @property
    def _llm_type(self) -> str:
        return f"gateway-{self.provider_name}"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "tool_count": len(self.bound_tools),
        }

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[Any, AIMessage]:
        _ = kwargs
        normalized = [convert_to_openai_tool(tool) for tool in tools]
        return self.model_copy(update={"bound_tools": normalized, "tool_choice": tool_choice})

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        _ = stop, run_manager
        request_messages = self._to_provider_messages(messages)
        response = await self.provider.chat(
            messages=request_messages,
            model=self.model_name,
            api_key=self.api_key,
            temperature=kwargs.get("temperature", self.temperature),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
        )
        message = self._to_ai_message(response)
        return ChatResult(
            generations=[ChatGeneration(message=message)],
            llm_output={"provider": self.provider_name, "model": self.model_name, "raw": response.get("raw")},
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        _ = stop, run_manager
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs))
        raise RuntimeError("GatewayToolCallingChatModel only supports async invocation when an event loop is already running") from None

    def _to_provider_messages(self, messages: list[BaseMessage]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        tool_instruction_added = False
        for message in messages:
            if isinstance(message, ToolMessage):
                content = message.content if isinstance(message.content, str) else json.dumps(message.content, ensure_ascii=False)
                converted.append(
                    {
                        "role": "tool",
                        "content": content,
                        "tool_call_id": message.tool_call_id,
                        "name": message.name,
                    }
                )
                continue

            role = "user"
            if isinstance(message, AIMessage):
                role = "assistant"
            elif isinstance(message, SystemMessage):
                role = "system"
            elif isinstance(message, HumanMessage):
                role = "user"

            content = message.content if isinstance(message.content, str) else json.dumps(message.content, ensure_ascii=False)
            if role == "system" and self.bound_tools and not tool_instruction_added:
                content = f"{content}\n\n{self._tool_protocol_instruction()}"
                tool_instruction_added = True
            converted.append({"role": role, "content": content})

        if self.bound_tools and not tool_instruction_added:
            converted.insert(0, {"role": "system", "content": self._tool_protocol_instruction()})
        return converted

    def _tool_protocol_instruction(self) -> str:
        tool_catalog = [
            {
                "name": item.get("function", {}).get("name"),
                "description": item.get("function", {}).get("description", ""),
                "parameters": item.get("function", {}).get("parameters", {}),
            }
            for item in self.bound_tools
        ]
        return (
            "你必须严格遵循工具调用 JSON 协议。"
            "如果需要调用工具，请只输出一个 JSON 对象："
            '{"type":"tool_calls","tool_calls":[{"name":"tool_name","arguments":{}}],"assistant_response":"可选补充说明"}。'
            "如果任务已经完成，请只输出："
            '{"type":"final","content":"最终结论","summary":"简短总结","next_action":"后续动作","requires_approval":true}。'
            f"\n可用工具如下：\n{json.dumps(tool_catalog, ensure_ascii=False, indent=2)}"
        )

    def _to_ai_message(self, response: dict[str, Any]) -> AIMessage:
        raw = response.get("raw")
        native = self._parse_native_tool_calls(raw)
        if native is not None:
            return native

        content = str(response.get("content", "") or "")
        parsed = self._parse_structured_content(content)
        if parsed.get("tool_calls"):
            return AIMessage(content=str(parsed.get("assistant_response") or ""), tool_calls=parsed["tool_calls"])
        if parsed.get("final_content"):
            return AIMessage(content=parsed["final_content"])
        return AIMessage(content=content)

    def _parse_native_tool_calls(self, raw: Any) -> AIMessage | None:
        if isinstance(raw, dict):
            choices = raw.get("choices")
            if isinstance(choices, list) and choices:
                message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
                tool_calls = message.get("tool_calls") if isinstance(message, dict) else None
                if isinstance(tool_calls, list) and tool_calls:
                    parsed: list[dict[str, Any]] = []
                    for item in tool_calls:
                        if not isinstance(item, dict):
                            continue
                        function = item.get("function") or {}
                        arguments = function.get("arguments")
                        if isinstance(arguments, str):
                            try:
                                arguments = json.loads(arguments)
                            except json.JSONDecodeError:
                                arguments = {}
                        parsed.append(
                            {
                                "name": function.get("name") or item.get("name") or "tool",
                                "args": arguments if isinstance(arguments, dict) else {},
                                "id": item.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                            }
                        )
                    return AIMessage(content=str(message.get("content", "") or ""), tool_calls=parsed)

            content_blocks = raw.get("content")
            if isinstance(content_blocks, list):
                tool_calls: list[dict[str, Any]] = []
                text_parts: list[str] = []
                for block in content_blocks:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use":
                        tool_calls.append(
                            {
                                "name": block.get("name") or "tool",
                                "args": block.get("input") if isinstance(block.get("input"), dict) else {},
                                "id": block.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                            }
                        )
                    elif block.get("type") == "text":
                        text_parts.append(str(block.get("text", "")))
                if tool_calls:
                    return AIMessage(content="".join(text_parts), tool_calls=tool_calls)
        return None

    def _parse_structured_content(self, content: str) -> dict[str, Any]:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return {"final_content": content}
        if not isinstance(parsed, dict):
            return {"final_content": content}

        response_type = str(parsed.get("type") or "").strip().lower()
        if response_type == "tool_calls":
            tool_calls: list[dict[str, Any]] = []
            for item in parsed.get("tool_calls", []) or []:
                if not isinstance(item, dict):
                    continue
                arguments = item.get("arguments")
                if not isinstance(arguments, dict):
                    arguments = {}
                tool_calls.append(
                    {
                        "name": item.get("name") or "tool",
                        "args": arguments,
                        "id": item.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                    }
                )
            return {"tool_calls": tool_calls, "assistant_response": parsed.get("assistant_response", "")}
        if response_type == "final":
            return {
                "final_content": str(parsed.get("content") or parsed.get("summary") or ""),
                "final_payload": parsed,
            }
        return {"final_content": content}


def get_chat_model(context: RuntimeExecutionContext) -> GatewayToolCallingChatModel:
    """Resolve the current workflow provider into a LangChain-compatible chat model."""

    key_data = secure_storage.get(f"cloud_{context.provider}_key") or {}
    api_key = str(key_data.get("api_key") or "")
    if not api_key:
        raise ProviderAdapterError(f"未配置 {context.provider} 的 API Key")

    provider = resolve_saved_provider(context.provider, key_data)
    if provider is None:
        raise ProviderAdapterError(f"不支持的云端服务商: {context.provider}")

    model_name = context.model or key_data.get("default_model") or provider.get_default_model()
    return GatewayToolCallingChatModel(
        provider_name=context.provider,
        model_name=model_name,
        api_key=api_key,
        provider=provider,
    )
