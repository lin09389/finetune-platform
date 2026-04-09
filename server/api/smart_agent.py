"""Smart agent API wrapper with unified response contract."""

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.agent import ChatExecuteRequest, chat_execute

logger = logging.getLogger(__name__)
router = APIRouter()


class SmartAgentRequest(BaseModel):
    message: str = Field(..., description="user message")
    auto_execute: bool = Field(default=True, description="execute automatically")
    auto_confirm_safe: bool = Field(default=False, description="auto confirm high-risk actions")
    context: dict[str, Any] | None = Field(default=None, description="context")


class OperationFeedback(BaseModel):
    detected: bool
    intent_type: str = ""
    action: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    confidence: float = 0.0
    need_confirm: bool = False
    execution: dict[str, Any] | None = None
    executed: bool = False
    success: bool | None = None
    result_data: dict[str, Any] | None = None
    feedback: str = ""
    error: str | None = None
    duration_ms: float = 0.0


class MultiOperationResponse(BaseModel):
    operations: list[OperationFeedback] = Field(default_factory=list)
    summary: str = ""


@router.post("/smart-execute", response_model=OperationFeedback)
async def smart_execute(request: SmartAgentRequest):
    if not request.auto_execute:
        return OperationFeedback(
            detected=True,
            intent_type="unknown",
            feedback="auto_execute is disabled",
            execution={"status": "planned", "error": None, "result": None},
        )

    resp = await chat_execute(
        ChatExecuteRequest(
            message=request.message,
            auto_confirm=request.auto_confirm_safe,
            context=request.context,
            session_id="smart-agent",
        )
    )

    execution = resp.execution or {"status": "unknown", "error": resp.error, "result": resp.result}
    return OperationFeedback(
        detected=resp.detected,
        intent_type=resp.intent_type,
        action=resp.action,
        params=resp.params,
        description=resp.description,
        confidence=resp.confidence,
        need_confirm=resp.need_confirm,
        execution=execution,
        executed=execution.get("status") in {"executed", "failed"},
        success=execution.get("status") == "executed",
        result_data=resp.result,
        feedback=resp.description or "",
        error=resp.error,
    )


@router.post("/smart-chat", response_model=MultiOperationResponse)
async def smart_chat(request: SmartAgentRequest):
    single = await smart_execute(request)
    return MultiOperationResponse(
        operations=[single],
        summary="1 operation handled" if single.detected else "no intent detected",
    )


@router.get("/supported-operations")
async def get_supported_operations():
    from api.agent import get_capabilities

    caps = await get_capabilities()
    return {
        "actions": caps["actions"],
        "count": len(caps["actions"]),
    }
