"""Pure OpenAI ↔ Ollama tool-calling transforms for the local Chat Completions facade.

These helpers have no I/O so tests can assert payload mapping without a live Ollama.
"""

from __future__ import annotations

import json
from typing import Any

from api.inference.backends.base import BackendType

# Backends that may accept OpenAI-style tools on the local facade (Phase 2: Ollama only).
TOOL_CAPABLE_LOCAL_BACKENDS: frozenset[str] = frozenset({BackendType.OLLAMA.value})

_OLLAMA_TOOL_DENY_MESSAGE = (
    "当前本地后端不支持 Agent 工具调用。"
    "请使用 Ollama 后端（provider=ollama 或 model=ollama/...），"
    "或配置支持工具调用的云端 provider:model。"
)


def request_requires_tools(
    *,
    tools: list[dict[str, Any]] | None,
    tool_choice: Any,
    messages: list[Any],
    parallel_tool_calls: bool | None = None,
) -> bool:
    """True when the OpenAI-compatible request participates in a tool loop."""
    if tools:
        return True
    if parallel_tool_calls is not None:
        return True
    if tool_choice not in (None, "none"):
        return True
    for message in messages or []:
        role = getattr(message, "role", None)
        if role is None and isinstance(message, dict):
            role = message.get("role")
        if role in {"tool", "function"}:
            return True
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls is None and isinstance(message, dict):
            tool_calls = message.get("tool_calls")
        if tool_calls:
            return True
    return False


def backend_allows_tools(backend_name: str | None) -> bool:
    return str(backend_name or "").strip().lower() in TOOL_CAPABLE_LOCAL_BACKENDS


def tools_denied_message(backend_name: str | None) -> str:
    name = str(backend_name or "unknown")
    return f"{_OLLAMA_TOOL_DENY_MESSAGE}（当前 backend={name}）"


def openai_messages_to_ollama(messages: list[Any]) -> list[dict[str, Any]]:
    """Convert OpenAI chat messages (objects or dicts) into Ollama /api/chat messages."""
    converted: list[dict[str, Any]] = []
    for message in messages or []:
        if hasattr(message, "role"):
            role = message.role
            content = message.content
            tool_calls = message.tool_calls
            tool_call_id = message.tool_call_id
            name = message.name
        else:
            role = message.get("role")
            content = message.get("content")
            tool_calls = message.get("tool_calls")
            tool_call_id = message.get("tool_call_id")
            name = message.get("name")

        role_str = "system" if role == "developer" else str(role or "user")
        item: dict[str, Any] = {"role": role_str}

        if role_str == "assistant" and tool_calls:
            item["content"] = content if content is not None else ""
            item["tool_calls"] = [_openai_tool_call_to_ollama(tc) for tc in tool_calls]
        elif role_str == "tool":
            # Ollama expects role=tool with content; tool_name optional in newer versions.
            item["content"] = "" if content is None else str(content)
            if name:
                item["tool_name"] = str(name)
            if tool_call_id:
                # Some Ollama builds ignore this; keep for forward compatibility.
                item["tool_call_id"] = str(tool_call_id)
        else:
            item["content"] = "" if content is None else str(content)

        converted.append(item)
    return converted


def _openai_tool_call_to_ollama(tool_call: Any) -> dict[str, Any]:
    if hasattr(tool_call, "model_dump"):
        tool_call = tool_call.model_dump()
    if not isinstance(tool_call, dict):
        return {"type": "function", "function": {"name": "tool", "arguments": {}}}

    # OpenAI: {id, type, function: {name, arguments: str|dict}}
    if "function" in tool_call:
        fn = tool_call.get("function") or {}
        name = fn.get("name") or tool_call.get("name") or "tool"
        arguments = fn.get("arguments")
    else:
        name = tool_call.get("name") or "tool"
        arguments = tool_call.get("arguments") or tool_call.get("args")

    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            arguments = {"raw": arguments}
    if not isinstance(arguments, dict):
        arguments = {}

    payload: dict[str, Any] = {
        "type": "function",
        "function": {
            "name": str(name),
            "arguments": arguments,
        },
    }
    if tool_call.get("id"):
        payload["id"] = str(tool_call["id"])
    return payload


def openai_tools_for_ollama(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """Ollama accepts OpenAI-style tool definitions; pass through with light normalization."""
    if not tools:
        return None
    normalized: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
            normalized.append(tool)
            continue
        # LangChain-ish {name, description, parameters}
        if tool.get("name"):
            normalized.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description") or "",
                        "parameters": tool.get("parameters") or tool.get("input_schema") or {},
                    },
                }
            )
    return normalized or None


def build_ollama_chat_payload(
    *,
    model: str,
    messages: list[Any],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: Any = None,
    stream: bool = False,
    options: dict[str, Any] | None = None,
    keep_alive: str | None = "5m",
    think: bool | None = None,
) -> dict[str, Any]:
    """Build a JSON body for Ollama ``POST /api/chat`` including tools when present."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": openai_messages_to_ollama(messages),
        "stream": stream,
    }
    ollama_tools = openai_tools_for_ollama(tools)
    if ollama_tools:
        payload["tools"] = ollama_tools
    if tool_choice not in (None, "none"):
        # Ollama currently accepts string tool_choice sparingly; pass through when set.
        payload["tool_choice"] = tool_choice
    if options:
        payload["options"] = options
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    if think is not None:
        payload["think"] = think
    return payload


def ollama_tool_calls_to_openai(tool_calls: Any) -> list[dict[str, Any]]:
    """Map Ollama message.tool_calls into OpenAI chat.completion tool_calls."""
    if not tool_calls:
        return []
    if not isinstance(tool_calls, list):
        return []

    mapped: list[dict[str, Any]] = []
    for index, raw in enumerate(tool_calls):
        if not isinstance(raw, dict):
            continue
        fn = raw.get("function") if isinstance(raw.get("function"), dict) else raw
        name = str(fn.get("name") or raw.get("name") or "tool")
        arguments = fn.get("arguments") if isinstance(fn, dict) else None
        if arguments is None:
            arguments = raw.get("arguments") or raw.get("args") or {}
        if isinstance(arguments, dict):
            arguments_str = json.dumps(arguments, ensure_ascii=False)
        else:
            arguments_str = str(arguments)
        call_id = str(raw.get("id") or f"call_ollama_{index}")
        mapped.append(
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": arguments_str,
                },
            }
        )
    return mapped


def ollama_chat_result_to_openai_message(message: dict[str, Any] | None) -> dict[str, Any]:
    """Convert Ollama response message to OpenAI assistant message fields."""
    message = message or {}
    content = message.get("content")
    if content is None:
        content = message.get("thinking") or ""
    tool_calls = ollama_tool_calls_to_openai(message.get("tool_calls"))
    payload: dict[str, Any] = {
        "role": "assistant",
        "content": content if content is not None else "",
    }
    if tool_calls:
        payload["tool_calls"] = tool_calls
        # OpenAI allows null content when tool_calls present; keep empty string for schema ease.
        if payload["content"] is None:
            payload["content"] = ""
    return payload


def finish_reason_for_ollama_message(message: dict[str, Any] | None, *, done_reason: str | None = None) -> str:
    message = message or {}
    if message.get("tool_calls"):
        return "tool_calls"
    if done_reason:
        return str(done_reason)
    return "stop"


__all__ = [
    "TOOL_CAPABLE_LOCAL_BACKENDS",
    "backend_allows_tools",
    "build_ollama_chat_payload",
    "finish_reason_for_ollama_message",
    "ollama_chat_result_to_openai_message",
    "ollama_tool_calls_to_openai",
    "openai_messages_to_ollama",
    "openai_tools_for_ollama",
    "request_requires_tools",
    "tools_denied_message",
]
