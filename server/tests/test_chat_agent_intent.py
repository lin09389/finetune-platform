from __future__ import annotations

import asyncio
from pathlib import Path

from chat_agent.models import ChatAgentIntentRequest
from chat_agent.service import ChatAgentService

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_chat_agent_package_does_not_recreate_workflow_runtime_boundary():
    checked = [
        REPO_ROOT / "server" / "api" / "chat_agent.py",
        *sorted((REPO_ROOT / "server" / "chat_agent").glob("*.py")),
    ]
    banned_terms = ("workflow", "agent_run", "create_run", "create_workflow")
    violations: list[str] = []

    for path in checked:
        source = path.read_text(encoding="utf-8").lower()
        for term in banned_terms:
            if term in source:
                violations.append(f"{path.relative_to(REPO_ROOT)} contains {term!r}")

    assert not violations, "Chat Agent must stay intent-only:\n" + "\n".join(violations)


def test_chat_agent_intent_falls_back_when_requested_agent_is_subagent():
    service = ChatAgentService()

    response = asyncio.run(
        service.classify_intent(
            ChatAgentIntentRequest(
                content="帮我修改代码",
                routing_mode="agent",
                agent_id="explore",
            )
        )
    )

    assert response.mode == "agent"
    assert response.suggested_agent_id == "build"
    assert "不能直接启动" in response.reason


def test_chat_agent_intent_falls_back_when_requested_agent_is_unknown():
    service = ChatAgentService()

    response = asyncio.run(
        service.classify_intent(
            ChatAgentIntentRequest(
                content="运行测试",
                routing_mode="agent",
                agent_id="missing",
            )
        )
    )

    assert response.mode == "agent"
    assert response.suggested_agent_id == "build"


def test_chat_agent_intent_clears_suggested_agent_for_chat_mode():
    service = ChatAgentService()

    response = asyncio.run(
        service.classify_intent(
            ChatAgentIntentRequest(
                content="只讨论这个设计",
                routing_mode="chat",
                agent_id="build",
            )
        )
    )

    assert response.mode == "chat"
    assert response.suggested_agent_id is None
