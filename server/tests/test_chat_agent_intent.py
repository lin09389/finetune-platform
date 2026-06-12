from __future__ import annotations

import asyncio

from chat_agent.models import ChatAgentIntentRequest
from chat_agent.service import ChatAgentService


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
