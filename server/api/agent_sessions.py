from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from agent_session.models import (
    AgentApprovalResponse,
    AgentEventResponse,
    AgentPromptRequest,
    AgentSessionCreate,
    AgentSessionOverviewResponse,
    AgentSessionResponse,
    LegacyAgentHistoryResponse,
)
from agent_session.legacy_history import LegacyAgentHistoryService
from agent_session.service import AgentSessionService
from agent_runtime_legacy.service import AgentRuntimeService
from agent_runtime_legacy.read_service import LegacyWorkflowReadService
from api.workflows import get_agent_runtime_service
from core.config import settings
from core.db_manager import run_sync
from security.auth_middleware import get_current_user_optional
from security.jwt_auth import Role, TokenPayload

router = APIRouter(prefix="/agent-sessions", tags=["Agent Sessions"])


def get_agent_session_service() -> AgentSessionService:
    return AgentSessionService()


def get_legacy_workflow_read_service(
    runtime: AgentRuntimeService = Depends(get_agent_runtime_service),
) -> LegacyWorkflowReadService:
    return LegacyWorkflowReadService(runtime.repository)


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


@router.get("/legacy-workflows/{workflow_id}", response_model=LegacyAgentHistoryResponse)
async def get_legacy_workflow_history(
    workflow_id: str,
    reader: LegacyWorkflowReadService = Depends(get_legacy_workflow_read_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    return await run_sync(LegacyAgentHistoryService(reader).get_workflow_history, workflow_id)


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


@router.get("/{session_id}/overview", response_model=AgentSessionOverviewResponse)
async def get_agent_session_overview(
    session_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        return await run_sync(service.get_overview, session_id)
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
        last_heartbeat = time.monotonic()
        heartbeat_interval = 15.0
        yield "retry: 3000\n\n"

        queue = service.subscribe_events(session_id)
        try:
            for event in await run_sync(service.list_events, session_id, since_id):
                if event.get("id") in seen:
                    continue
                seen.add(event["id"])
                since_id = event["id"]
                chunk = await run_sync(service.build_stream_chunk, event)
                yield f"event: agent_session_event\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                last_heartbeat = time.monotonic()

            session = await run_sync(service.get_session, session_id)
            if session and session.get("status") in AgentSessionService.TERMINAL_STATUSES and len(seen) > (1 if since_event_id else 0):
                yield f"event: agent_session_done\ndata: {json.dumps({'status': session.get('status')}, ensure_ascii=False)}\n\n"
                return

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=heartbeat_interval)
                except asyncio.TimeoutError:
                    now = time.monotonic()
                    if now - last_heartbeat >= heartbeat_interval:
                        yield ": heartbeat\n\n"
                        last_heartbeat = now
                    session = await run_sync(service.get_session, session_id)
                    if session and session.get("status") in AgentSessionService.TERMINAL_STATUSES:
                        yield f"event: agent_session_done\ndata: {json.dumps({'status': session.get('status')}, ensure_ascii=False)}\n\n"
                        break
                    continue

                event_id = event.get("id", "")
                if event_id in seen:
                    continue
                seen.add(event_id)
                since_id = event_id
                chunk = await run_sync(service.build_stream_chunk, event)
                yield f"event: agent_session_event\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                last_heartbeat = time.monotonic()

                session_status = chunk.get("session_status")
                if session_status in AgentSessionService.TERMINAL_STATUSES:
                    yield f"event: agent_session_done\ndata: {json.dumps({'status': session_status}, ensure_ascii=False)}\n\n"
                    break
        finally:
            service.unsubscribe_events(session_id, queue)

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
