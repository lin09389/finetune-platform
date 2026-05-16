from __future__ import annotations

from fastapi import APIRouter, Depends

from chat_agent.models import ChatAgentIntentRequest, ChatAgentIntentResponse
from chat_agent.service import ChatAgentService

router = APIRouter(prefix="/chat-agent", tags=["Chat Agent"])


def get_chat_agent_service() -> ChatAgentService:
    return ChatAgentService()


@router.post("/intent", response_model=ChatAgentIntentResponse)
async def classify_chat_agent_intent(
    request: ChatAgentIntentRequest,
    service: ChatAgentService = Depends(get_chat_agent_service),
):
    return await service.classify_intent(request)
