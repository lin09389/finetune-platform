"""Intent policy helpers for safe routing and execution gating."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


ROUTE_CHAT_THRESHOLD = 0.45
ROUTE_TOOL_THRESHOLD = 0.75
ACTION_EXECUTION_THRESHOLD = 0.72

MODEL_IDENTITY_QUERY_PATTERN = re.compile(
    r"(你是(哪个|什么)?模型|当前(使用|在用)?(的)?模型(是|叫什么)?|what\s+model\s+are\s+you)",
    re.IGNORECASE,
)
CHAT_ONLY_PATTERN = re.compile(
    r"^(你好|您好|hi|hello|hey|谢谢|thanks|bye|再见)[\s!,.?]*$",
    re.IGNORECASE,
)
OCR_COMMAND_PATTERN = re.compile(
    r"(ocr|识别|提取).*(文字|文本|图片|图像|截图|屏幕)|"
    r"(文字|文本).*(识别|提取)|"
    r"(屏幕|截图|图片|图像).*(识别|ocr)|"
    r"(ocr|recognize|extract).*(text|image|screen|screenshot)|"
    r"(text|image|screen|screenshot).*(ocr|recognize|extract)",
    re.IGNORECASE,
)
OCR_ACTIONS = {"ocr_recognize", "ocr_find_text"}


@dataclass
class RoutingDecision:
    route: str
    route_confidence: float
    reason: str


@dataclass
class ExecutionPolicyDecision:
    decision: str
    reason: str
    action_confidence: float


def choose_route(message: str, *, detected: bool, action: str | None, confidence: float, intent_type: str | None) -> RoutingDecision:
    return choose_route_with_thresholds(
        message,
        detected=detected,
        action=action,
        confidence=confidence,
        intent_type=intent_type,
        route_chat_threshold=ROUTE_CHAT_THRESHOLD,
        route_tool_threshold=ROUTE_TOOL_THRESHOLD,
    )


def choose_route_with_thresholds(
    message: str,
    *,
    detected: bool,
    action: str | None,
    confidence: float,
    intent_type: str | None,
    route_chat_threshold: float,
    route_tool_threshold: float,
) -> RoutingDecision:
    normalized = (message or "").strip()
    if not normalized:
        return RoutingDecision(route="chat", route_confidence=1.0, reason="empty_input")

    if MODEL_IDENTITY_QUERY_PATTERN.search(normalized) or CHAT_ONLY_PATTERN.match(normalized):
        return RoutingDecision(route="chat", route_confidence=1.0, reason="chat_only_query")

    if not detected:
        return RoutingDecision(route="chat", route_confidence=0.0, reason="not_detected")

    if intent_type == "conversation" or not action:
        return RoutingDecision(route="chat", route_confidence=max(confidence, 0.9), reason="conversation_intent")

    if confidence < route_chat_threshold:
        return RoutingDecision(route="chat", route_confidence=confidence, reason="low_confidence")
    if confidence < route_tool_threshold:
        return RoutingDecision(route="unsure", route_confidence=confidence, reason="medium_confidence")
    return RoutingDecision(route="tool", route_confidence=confidence, reason="tool_intent")


def validate_action(
    action: str,
    params: dict[str, Any],
    message: str,
    *,
    supported_actions: set[str],
) -> tuple[bool, str]:
    if action not in supported_actions:
        return False, "unsupported_action"

    if action in OCR_ACTIONS and not OCR_COMMAND_PATTERN.search(message or ""):
        return False, "ocr_guard_fallback"

    if action == "url_open":
        url = params.get("url")
        if not isinstance(url, str) or not url.strip():
            return False, "missing_url_param"

    if action.startswith("file_") and action not in {"file_list", "file_search", "file_exists", "file_info"}:
        path = params.get("file_path") or params.get("path")
        if not isinstance(path, str) or not path.strip():
            return False, "missing_file_path"

    return True, "ok"


def choose_execution_policy(
    *,
    action: str,
    action_confidence: float,
    need_confirm: bool,
    auto_confirm: bool,
) -> ExecutionPolicyDecision:
    return choose_execution_policy_with_threshold(
        action=action,
        action_confidence=action_confidence,
        need_confirm=need_confirm,
        auto_confirm=auto_confirm,
        action_execution_threshold=ACTION_EXECUTION_THRESHOLD,
    )


def choose_execution_policy_with_threshold(
    *,
    action: str,
    action_confidence: float,
    need_confirm: bool,
    auto_confirm: bool,
    action_execution_threshold: float,
) -> ExecutionPolicyDecision:
    if action_confidence < action_execution_threshold:
        return ExecutionPolicyDecision(
            decision="needs_inference",
            reason="low_action_confidence",
            action_confidence=action_confidence,
        )

    if need_confirm and not auto_confirm:
        return ExecutionPolicyDecision(
            decision="needs_confirmation",
            reason="confirmation_required",
            action_confidence=action_confidence,
        )

    return ExecutionPolicyDecision(
        decision="execute",
        reason="policy_pass",
        action_confidence=action_confidence,
    )
