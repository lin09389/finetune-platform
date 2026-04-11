from agent.intent.policy import (
    choose_execution_policy,
    choose_route,
    validate_action,
)


def test_choose_route_chat_for_model_identity():
    decision = choose_route(
        "你是哪个模型",
        detected=True,
        action="ocr_recognize",
        confidence=0.99,
        intent_type="ocr_recognize",
    )
    assert decision.route == "chat"
    assert decision.reason == "chat_only_query"


def test_choose_route_chat_for_greeting():
    decision = choose_route(
        "你好",
        detected=True,
        action="file_read",
        confidence=0.99,
        intent_type="file_read",
    )
    assert decision.route == "chat"
    assert decision.reason == "chat_only_query"


def test_choose_route_unsure_for_medium_confidence():
    decision = choose_route(
        "read README.md",
        detected=True,
        action="file_read",
        confidence=0.60,
        intent_type="file_read",
    )
    assert decision.route == "unsure"
    assert decision.reason == "medium_confidence"


def test_validate_action_rejects_ocr_without_context():
    ok, reason = validate_action(
        "ocr_recognize",
        {},
        "你是哪个模型",
        supported_actions={"ocr_recognize"},
    )
    assert ok is False
    assert reason == "ocr_guard_fallback"


def test_validate_action_accepts_ocr_english_command():
    ok, reason = validate_action(
        "ocr_recognize",
        {},
        "recognize text on screen",
        supported_actions={"ocr_recognize"},
    )
    assert ok is True
    assert reason == "ok"


def test_validate_action_accepts_supported_action():
    ok, reason = validate_action(
        "file_read",
        {"file_path": "README.md"},
        "读取 README.md",
        supported_actions={"file_read"},
    )
    assert ok is True
    assert reason == "ok"


def test_choose_execution_policy_requires_confirmation():
    decision = choose_execution_policy(
        action="file_delete",
        action_confidence=0.95,
        need_confirm=True,
        auto_confirm=False,
    )
    assert decision.decision == "needs_confirmation"
    assert decision.reason == "confirmation_required"


def test_choose_execution_policy_low_confidence_fallback():
    decision = choose_execution_policy(
        action="file_read",
        action_confidence=0.60,
        need_confirm=False,
        auto_confirm=True,
    )
    assert decision.decision == "needs_inference"
    assert decision.reason == "low_action_confidence"
