from __future__ import annotations

from chat_agent.models import ChatAgentIntentRequest, ChatAgentIntentResponse
from chat_agent.service import ChatAgentService
from fastapi import APIRouter, Depends, HTTPException

from api.agent_sessions import get_agent_session_user
from security.jwt_auth import TokenPayload

router = APIRouter(prefix="/chat-agent", tags=["Chat Agent"])

_chat_agent_service: ChatAgentService | None = None


def get_chat_agent_service() -> ChatAgentService:
    global _chat_agent_service
    if _chat_agent_service is None:
        _chat_agent_service = ChatAgentService()
    return _chat_agent_service


@router.post("/intent", response_model=ChatAgentIntentResponse)
async def classify_chat_agent_intent(
    request: ChatAgentIntentRequest,
    service: ChatAgentService = Depends(get_chat_agent_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        return await service.classify_intent(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
