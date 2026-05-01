from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from api.workflows import get_agent_runtime_service
from agent_runtime.models import WorkflowActionResponse, WorkflowToolCallResponse
from agent_runtime.service import AgentRuntimeService
from chat_agent.models import (
    ChatAgentApprovalRequest,
    ChatAgentIntentRequest,
    ChatAgentIntentResponse,
    ChatAgentRunEvent,
    ChatAgentRunCreate,
    ChatAgentRunResponse,
)
from chat_agent.service import ChatAgentService

router = APIRouter(prefix="/chat-agent", tags=["Chat Agent"])


def get_chat_agent_service(
    runtime: AgentRuntimeService = Depends(get_agent_runtime_service),
) -> ChatAgentService:
    return ChatAgentService(runtime)


@router.post("/runs", response_model=ChatAgentRunResponse)
async def create_chat_agent_run(
    request: ChatAgentRunCreate,
    service: ChatAgentService = Depends(get_chat_agent_service),
):
    return service.create_run(request)


@router.post("/intent", response_model=ChatAgentIntentResponse)
async def classify_chat_agent_intent(
    request: ChatAgentIntentRequest,
    service: ChatAgentService = Depends(get_chat_agent_service),
):
    return await service.classify_intent(request)


@router.get("/runs/{run_id}", response_model=ChatAgentRunResponse)
async def get_chat_agent_run(
    run_id: str,
    service: ChatAgentService = Depends(get_chat_agent_service),
):
    return service.get_run(run_id)


@router.post("/runs/{run_id}/run", response_model=ChatAgentRunResponse)
async def run_chat_agent_run(
    run_id: str,
    service: ChatAgentService = Depends(get_chat_agent_service),
):
    return await service.run(run_id)


@router.post("/steps/{step_id}/approve", response_model=ChatAgentRunResponse)
async def approve_chat_agent_step(
    step_id: str,
    request: ChatAgentApprovalRequest,
    service: ChatAgentService = Depends(get_chat_agent_service),
):
    return await service.approve_step(step_id, approved=request.approved, comment=request.comment)


@router.post("/actions/{action_id}/approve", response_model=WorkflowActionResponse)
async def approve_chat_agent_action(
    action_id: str,
    service: ChatAgentService = Depends(get_chat_agent_service),
):
    return await service.approve_action(action_id)


@router.post("/actions/{action_id}/reject", response_model=WorkflowActionResponse)
async def reject_chat_agent_action(
    action_id: str,
    service: ChatAgentService = Depends(get_chat_agent_service),
):
    return service.reject_action(action_id)


@router.post("/actions/{action_id}/execute", response_model=WorkflowActionResponse)
async def execute_chat_agent_action(
    action_id: str,
    service: ChatAgentService = Depends(get_chat_agent_service),
):
    return await service.execute_action_with_repair(action_id)


@router.get("/runs/{run_id}/tool-calls", response_model=list[WorkflowToolCallResponse])
async def get_chat_agent_tool_calls(
    run_id: str,
    service: ChatAgentService = Depends(get_chat_agent_service),
):
    return service.list_tool_calls(run_id)


@router.get("/runs/{run_id}/events/stream")
async def stream_chat_agent_run_events(
    run_id: str,
    service: ChatAgentService = Depends(get_chat_agent_service),
):
    async def event_stream():
        seen: set[str] = set()
        active_statuses = {"created", "running", "planning", "implementing", "reviewing"}
        for tick in range(180):
            for event in service.list_events(run_id):
                event_id = str(event.payload.get("workflow_event_id") or f"{event.event_type}:{event.message}")
                if event_id in seen:
                    continue
                seen.add(event_id)
                yield f"event: chat_agent_event\ndata: {json.dumps(event.model_dump(), ensure_ascii=False)}\n\n"
            if tick % 5 == 0:
                heartbeat = ChatAgentRunEvent(
                    event_type="heartbeat",
                    run_id=run_id,
                    message="Agent 正在工作",
                    payload={"tick": tick},
                )
                yield f"event: chat_agent_event\ndata: {json.dumps(heartbeat.model_dump(), ensure_ascii=False)}\n\n"
            try:
                run = service.get_run(run_id)
                if tick > 0 and run.status not in active_statuses:
                    break
            except Exception:
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
