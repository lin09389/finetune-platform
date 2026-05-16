from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatAgentIntentRequest(BaseModel):
    content: str = Field(..., min_length=1)
    provider: str | None = None
    model: str | None = None
    agent_id: str | None = None
    template_id: str | None = None
    chat_session_id: str | None = None
    routing_mode: Literal["auto", "chat", "agent"] = "auto"


class ChatAgentIntentResponse(BaseModel):
    mode: Literal["chat", "agent", "workflow"]
    confidence: float = Field(default=0.5, ge=0, le=1)
    reason: str
    source: Literal["local_rule", "cloud", "fallback", "manual"]
    suggested_agent_id: str | None = None
    suggested_template_id: str | None = None
