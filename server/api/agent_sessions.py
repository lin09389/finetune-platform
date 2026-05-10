from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from agent_session.models import (
    AgentApprovalResponse,
    AgentEventResponse,
    AgentPromptRequest,
    AgentSessionCreate,
    AgentSessionResponse,
)
from agent_session.service import AgentSessionService
from core.config import settings
from core.db_manager import run_sync
from security.auth_middleware import get_current_user_optional
from security.jwt_auth import Role, TokenPayload

router = APIRouter(prefix="/agent-sessions", tags=["Agent Sessions"])


def get_agent_session_service() -> AgentSessionService:
    return AgentSessionService()


async def get_agent_session_user(
    current_user: TokenPayload | None = Depends(get_current_user_optional),
) -> TokenPayload:
    if current_user:
        return current_user
    if settings.environment == "production":
        raise HTTPException(status_code=401, detail="Missing authorization")
    return TokenPayload(
        user_id="desktop-local-user",
        username="desktop",
        role=Role.USER,
        permissions=["agent_sessions:local"],
    )


@router.post("", response_model=AgentSessionResponse)
async def create_agent_session(
    request: AgentSessionCreate,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    return await run_sync(service.create_session, request)


@router.get("/{session_id}", response_model=AgentSessionResponse)
async def get_agent_session(
    session_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        return await run_sync(service.get_session, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{session_id}/prompt", response_model=AgentSessionResponse)
async def prompt_agent_session(
    session_id: str,
    request: AgentPromptRequest,
    background_tasks: BackgroundTasks,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        return await run_sync(service.start_prompt_background, session_id, request, background_tasks)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        try:
            return await run_sync(service.record_prompt_failure, session_id, exc)
        except ValueError as value_exc:
            raise HTTPException(status_code=404, detail=str(value_exc)) from value_exc


@router.post("/{session_id}/interrupt", response_model=AgentSessionResponse)
async def interrupt_agent_session(
    session_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        return await run_sync(service.interrupt_session, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{session_id}/events", response_model=list[AgentEventResponse])
async def list_agent_session_events(
    session_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        await run_sync(service.get_session, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await run_sync(service.list_events, session_id)


@router.get("/{session_id}/events/stream")
async def stream_agent_session_events(
    session_id: str,
    since_event_id: str | None = None,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    async def event_stream():
        seen: set[str] = {since_event_id} if since_event_id else set()
        since_id = since_event_id
        for _ in range(720):
            events = await run_sync(service.list_events, session_id, since_id)
            for event in events:
                if event["id"] in seen:
                    continue
                seen.add(event["id"])
                since_id = event["id"]
                chunk = await run_sync(service.build_stream_chunk, event)
                yield f"event: agent_session_event\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            try:
                session = await run_sync(service.get_session, session_id)
                if session.status in {"completed", "failed", "interrupted", "needs_manual_review", "waiting_approval", "waiting_permission"} and seen:
                    break
            except Exception:
                break
            await asyncio.sleep(0.25)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


permission_router = APIRouter(tags=["Agent Sessions"])
action_router = APIRouter(tags=["Agent Sessions"])


@permission_router.post("/agent-permissions/{permission_id}/approve", response_model=AgentApprovalResponse)
async def approve_agent_permission(
    permission_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        session = await service.approve_permission_async(permission_id, True)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    part = next((item for item in session.parts if item.id == permission_id), None)
    if not part:
        raise HTTPException(status_code=404, detail="Permission part not found")
    return AgentApprovalResponse(part=part, session=session)


@permission_router.post("/agent-permissions/{permission_id}/reject", response_model=AgentApprovalResponse)
async def reject_agent_permission(
    permission_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        session = await service.approve_permission_async(permission_id, False)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    part = next((item for item in session.parts if item.id == permission_id), None)
    if not part:
        raise HTTPException(status_code=404, detail="Permission part not found")
    return AgentApprovalResponse(part=part, session=session)


@action_router.post("/agent-actions/{action_id}/approve", response_model=AgentApprovalResponse)
async def approve_agent_action(
    action_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        session = await service.approve_action_async(action_id, True)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    part = next((item for item in session.parts if item.id == action_id), None)
    if not part:
        raise HTTPException(status_code=404, detail="Action part not found")
    return AgentApprovalResponse(part=part, session=session)


@action_router.post("/agent-actions/{action_id}/reject", response_model=AgentApprovalResponse)
async def reject_agent_action(
    action_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        session = await service.approve_action_async(action_id, False)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    part = next((item for item in session.parts if item.id == action_id), None)
    if not part:
        raise HTTPException(status_code=404, detail="Action part not found")
    return AgentApprovalResponse(part=part, session=session)


@action_router.post("/agent-actions/{action_id}/execute", response_model=AgentApprovalResponse)
async def execute_agent_action(
    action_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        session = await service.execute_action_async(action_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    part = next((item for item in session.parts if item.id == action_id), None)
    if not part:
        raise HTTPException(status_code=404, detail="Action part not found")
    return AgentApprovalResponse(part=part, session=session)
