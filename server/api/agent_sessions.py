from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from agent_session.models import (
    AgentApprovalResponse,
    AgentEventResponse,
    AgentPromptRequest,
    AgentSessionCreate,
    AgentSessionResponse,
)
from agent_session.service import AgentSessionService

router = APIRouter(prefix="/agent-sessions", tags=["Agent Sessions"])


def get_agent_session_service() -> AgentSessionService:
    return AgentSessionService()


@router.post("", response_model=AgentSessionResponse)
async def create_agent_session(
    request: AgentSessionCreate,
    service: AgentSessionService = Depends(get_agent_session_service),
):
    return service.create_session(request)


@router.get("/{session_id}", response_model=AgentSessionResponse)
async def get_agent_session(
    session_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
):
    try:
        return service.get_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{session_id}/prompt", response_model=AgentSessionResponse)
async def prompt_agent_session(
    session_id: str,
    request: AgentPromptRequest,
    service: AgentSessionService = Depends(get_agent_session_service),
):
    try:
        return await service.prompt(session_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{session_id}/events", response_model=list[AgentEventResponse])
async def list_agent_session_events(
    session_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
):
    try:
        service.get_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return service.list_events(session_id)


@router.get("/{session_id}/events/stream")
async def stream_agent_session_events(
    session_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
):
    async def event_stream():
        seen: set[str] = set()
        for _ in range(180):
            for event in service.list_events(session_id):
                if event["id"] in seen:
                    continue
                seen.add(event["id"])
                yield f"event: agent_session_event\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            try:
                session = service.get_session(session_id)
                if session.status in {"completed", "failed"} and seen:
                    break
            except Exception:
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


permission_router = APIRouter(tags=["Agent Sessions"])
action_router = APIRouter(tags=["Agent Sessions"])


@permission_router.post("/agent-permissions/{permission_id}/approve", response_model=AgentApprovalResponse)
async def approve_agent_permission(
    permission_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
):
    session = service.approve_permission(permission_id, True)
    part = next((item for item in session.parts if item.id == permission_id), None)
    if not part:
        raise HTTPException(status_code=404, detail="Permission part not found")
    return AgentApprovalResponse(part=part, session=session)


@permission_router.post("/agent-permissions/{permission_id}/reject", response_model=AgentApprovalResponse)
async def reject_agent_permission(
    permission_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
):
    session = service.approve_permission(permission_id, False)
    part = next((item for item in session.parts if item.id == permission_id), None)
    if not part:
        raise HTTPException(status_code=404, detail="Permission part not found")
    return AgentApprovalResponse(part=part, session=session)


@action_router.post("/agent-actions/{action_id}/approve", response_model=AgentApprovalResponse)
async def approve_agent_action(
    action_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
):
    session = service.approve_action(action_id, True)
    part = next((item for item in session.parts if item.id == action_id), None)
    if not part:
        raise HTTPException(status_code=404, detail="Action part not found")
    return AgentApprovalResponse(part=part, session=session)


@action_router.post("/agent-actions/{action_id}/reject", response_model=AgentApprovalResponse)
async def reject_agent_action(
    action_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
):
    session = service.approve_action(action_id, False)
    part = next((item for item in session.parts if item.id == action_id), None)
    if not part:
        raise HTTPException(status_code=404, detail="Action part not found")
    return AgentApprovalResponse(part=part, session=session)


@action_router.post("/agent-actions/{action_id}/execute", response_model=AgentApprovalResponse)
async def execute_agent_action(
    action_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
):
    session = service.execute_action(action_id)
    part = next((item for item in session.parts if item.id == action_id), None)
    if not part:
        raise HTTPException(status_code=404, detail="Action part not found")
    return AgentApprovalResponse(part=part, session=session)
