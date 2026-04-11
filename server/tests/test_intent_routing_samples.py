import pytest

from agent.intent.policy import (
    choose_execution_policy_with_threshold,
    choose_route_with_thresholds,
    validate_action,
)


@pytest.mark.parametrize(
    ("message", "detected", "action", "confidence", "intent_type", "expected_route"),
    [
        ("你是哪个模型", True, "ocr_recognize", 0.99, "ocr_recognize", "chat"),
        ("hello", True, "file_read", 0.99, "file_read", "chat"),
        ("read README.md", True, "file_read", 0.92, "file_read", "tool"),
        ("read README.md", True, "file_read", 0.60, "file_read", "unsure"),
        ("random talk", False, None, 0.0, None, "chat"),
    ],
)
def test_route_samples(message, detected, action, confidence, intent_type, expected_route):
    decision = choose_route_with_thresholds(
        message,
        detected=detected,
        action=action,
        confidence=confidence,
        intent_type=intent_type,
        route_chat_threshold=0.45,
        route_tool_threshold=0.75,
    )
    assert decision.route == expected_route


@pytest.mark.parametrize(
    ("action", "params", "message", "supported", "expected_ok"),
    [
        ("file_read", {"file_path": "README.md"}, "read README.md", {"file_read"}, True),
        ("ocr_recognize", {}, "recognize text on screen", {"ocr_recognize"}, True),
        ("ocr_recognize", {}, "你是哪个模型", {"ocr_recognize"}, False),
        ("unknown_action", {}, "do task", {"file_read"}, False),
    ],
)
def test_action_validation_samples(action, params, message, supported, expected_ok):
    ok, _ = validate_action(action, params, message, supported_actions=supported)
    assert ok is expected_ok


def test_execution_policy_threshold_sample():
    low = choose_execution_policy_with_threshold(
        action="file_read",
        action_confidence=0.65,
        need_confirm=False,
        auto_confirm=True,
        action_execution_threshold=0.72,
    )
    assert low.decision == "needs_inference"

    high = choose_execution_policy_with_threshold(
        action="file_read",
        action_confidence=0.92,
        need_confirm=False,
        auto_confirm=True,
        action_execution_threshold=0.72,
    )
    assert high.decision == "execute"
