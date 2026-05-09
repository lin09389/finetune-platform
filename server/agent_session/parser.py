from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal


ModelPartType = Literal["text", "tool_call", "summary"]


@dataclass
class ModelOutputPart:
    type: ModelPartType
    content: str = ""
    tool: str | None = None
    arguments: dict[str, Any] | None = None
    payload: dict[str, Any] | None = None


def parse_agent_response(raw: str) -> list[ModelOutputPart]:
    text = raw.strip()
    if not text:
        return []

    whole = _parse_json(text)
    if whole is not None:
        parts = _parts_from_json(whole)
        if parts:
            return parts

    parts: list[ModelOutputPart] = []
    cursor = 0
    found_json = False
    for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE):
        before = text[cursor : match.start()].strip()
        if before:
            parts.append(ModelOutputPart("text", content=before, payload={"parsed_from": "markdown_text"}))
        block = match.group(1).strip()
        parsed = _parse_json(block)
        json_parts = _parts_from_json(parsed) if parsed is not None else []
        if not json_parts:
            json_parts = [
                part
                for part in _parse_inline_json_parts(block)
                if part.type in {"tool_call", "summary"}
            ]
        if json_parts:
            found_json = True
            parts.extend(json_parts)
        elif block:
            parts.append(ModelOutputPart("text", content=block, payload={"parsed_from": "markdown_code"}))
        cursor = match.end()
    if found_json:
        after = text[cursor:].strip()
        if after:
            parts.append(ModelOutputPart("text", content=after, payload={"parsed_from": "markdown_text"}))
        return parts

    inline_parts = _parse_inline_json_parts(text)
    if inline_parts:
        return inline_parts

    if _looks_like_final_text(text):
        return [ModelOutputPart("summary", content=text, payload={"summary": text, "parsed_from": "natural_text"})]
    return [ModelOutputPart("text", content=text, payload={"parsed_from": "natural_text"})]


def parse_tool_request(raw: str) -> dict[str, Any] | None:
    for part in parse_agent_response(raw):
        if part.type == "tool_call" and part.tool:
            return {"tool": part.tool, "arguments": part.arguments or {}}
    return None


def _parse_json(value: str) -> Any | None:
    try:
        return json.loads(value)
    except Exception:
        return None


def _normalize_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = _parse_json(value.strip())
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _parts_from_json(value: Any) -> list[ModelOutputPart]:
    if isinstance(value, list):
        parts: list[ModelOutputPart] = []
        for item in value:
            parts.extend(_parts_from_json(item))
        return parts
    if not isinstance(value, dict):
        return []

    parts: list[ModelOutputPart] = []
    block_type = str(value.get("type") or "").lower()
    text_content = value.get("text") or value.get("content")
    if block_type in {"text", "message"} and text_content:
        parts.append(ModelOutputPart("text", content=str(text_content), payload={"parsed_from": "json_text"}))

    for key in ("tool_calls", "tools", "parts", "content_blocks", "messages", "content"):
        nested = value.get(key)
        if isinstance(nested, list):
            parts.extend(_parts_from_json(nested))
    if parts:
        return parts

    tool = value.get("tool") or value.get("tool_name") or value.get("name") or value.get("action")
    if not tool and block_type in {"tool_use", "tool_call", "function_call"}:
        tool = value.get("name") or value.get("tool_name")
    if tool:
        arguments = (
            value.get("arguments")
            or value.get("args")
            or value.get("parameters")
            or value.get("input")
            or value.get("payload")
            or {}
        )
        return [
            ModelOutputPart(
                "tool_call",
                tool=str(tool),
                arguments=_normalize_arguments(arguments),
                payload={"parsed_from": "json"},
            )
        ]

    summary = value.get("summary") or value.get("final_summary") or value.get("content")
    if summary and any(key in value for key in ("summary", "final_summary", "result", "completed_items")):
        return [ModelOutputPart("summary", content=str(summary), payload={**value, "parsed_from": "json_summary"})]
    return []


def _parse_inline_json_parts(text: str) -> list[ModelOutputPart]:
    spans = _json_candidate_spans(text)
    if not spans:
        return []
    parts: list[ModelOutputPart] = []
    cursor = 0
    found = False
    for start, end, parsed in spans:
        json_parts = _parts_from_json(parsed)
        if not json_parts:
            continue
        before = text[cursor:start].strip()
        if before:
            parts.append(ModelOutputPart("text", content=before, payload={"parsed_from": "inline_text"}))
        found = True
        parts.extend(json_parts)
        cursor = end
    if not found:
        return []
    after = text[cursor:].strip()
    if after:
        parts.append(ModelOutputPart("text", content=after, payload={"parsed_from": "inline_text"}))
    return parts


def _json_candidate_spans(text: str) -> list[tuple[int, int, Any]]:
    spans: list[tuple[int, int, Any]] = []
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            parsed, offset = decoder.raw_decode(text[index:])
        except Exception:
            continue
        end = index + offset
        if _parts_from_json(parsed):
            spans.append((index, end, parsed))
    non_overlapping: list[tuple[int, int, Any]] = []
    last_end = -1
    for span in spans:
        if span[0] >= last_end:
            non_overlapping.append(span)
            last_end = span[1]
    return non_overlapping


def _looks_like_final_text(text: str) -> bool:
    if len(text.strip()) < 12:
        return False
    strong_markers = ("已完成", "已经完成", "最终总结", "最终结果", "验证结果", "下一步", "风险", "改动")
    return any(marker in text for marker in strong_markers)
