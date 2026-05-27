from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from agent_session.models import (
    AgentApprovalResponse,
    AgentEventResponse,
    AgentHitlDecisionRequest,
    AgentPromptRequest,
    AgentSessionCreate,
    AgentSessionOverviewResponse,
    AgentSessionResponse,
)
from agent_session.service import AgentSessionService
from core.config import settings
from core.db_manager import run_sync
from security.auth_middleware import get_current_user_optional
from security.jwt_auth import Role, TokenPayload

router = APIRouter(prefix="/agent-sessions", tags=["Agent Sessions"])


def _session_status(session: Any) -> str | None:
    if isinstance(session, dict):
        return session.get("status")
    return getattr(session, "status", None)


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
            snapshot = await run_sync(service.build_session_snapshot_chunk, session_id)
            yield f"event: agent_session_event\ndata: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
            last_heartbeat = time.monotonic()

            for event in await run_sync(service.list_events, session_id, since_id):
                if event.get("id") in seen:
                    continue
                seen.add(event["id"])
                since_id = event["id"]
                chunk = await run_sync(service.build_stream_chunk, event)
                yield f"event: agent_session_event\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                last_heartbeat = time.monotonic()

            session = await run_sync(service.get_session, session_id)
            status = _session_status(session)
            if status in AgentSessionService.TERMINAL_STATUSES and len(seen) > (1 if since_event_id else 0):
                yield f"event: agent_session_done\ndata: {json.dumps({'status': status}, ensure_ascii=False)}\n\n"
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
                    status = _session_status(session)
                    if status in AgentSessionService.TERMINAL_STATUSES:
                        yield f"event: agent_session_done\ndata: {json.dumps({'status': status}, ensure_ascii=False)}\n\n"
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


@router.get("/{session_id}/artifacts/{artifact_id}/original")
async def get_artifact_original(
    session_id: str,
    artifact_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
) -> str | None:
    """Retrieve the original content of a modified artifact before changes were applied."""
    from pathlib import Path
    try:
        session = await run_sync(service.get_session, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Agent session not found")
        
        parts = artifact_id.split(":")
        if len(parts) < 2:
            raise HTTPException(status_code=400, detail="Invalid artifact ID format")
        
        # The file path is everything after part_id and before the seen_count
        file_path = ":".join(parts[1:-1]) if len(parts) > 2 else parts[1]
        
        project_path = session.get("project_path")
        if not project_path:
            raise HTTPException(status_code=400, detail="Session has no project path configured")
            
        target_path = Path(project_path).resolve() / file_path
        
        # Path safety verification
        try:
            resolved_target = target_path.resolve()
            resolved_project = Path(project_path).resolve()
            if not resolved_target.is_relative_to(resolved_project):
                raise HTTPException(status_code=403, detail="Access denied: target path is outside project root")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid target path")
            
        if not target_path.exists() or not target_path.is_file():
            return None
            
        try:
            return target_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as read_exc:
            raise HTTPException(status_code=500, detail=f"Failed to read file: {read_exc}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))



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


@permission_router.post("/agent-permissions/{permission_id}/decide", response_model=AgentApprovalResponse)
async def decide_agent_permission(
    permission_id: str,
    request: AgentHitlDecisionRequest,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        decisions = [decision.model_dump(exclude_none=True) for decision in request.decisions]
        session = await service.decide_permission_async(permission_id, decisions)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 422
        raise HTTPException(status_code=status_code, detail=message) from exc
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


@action_router.post("/agent-actions/{action_id}/hunk-decision")
async def record_hunk_decision(
    action_id: str,
    body: dict,
    service: AgentSessionService = Depends(get_agent_session_service),
) -> dict:
    """Record an accept/reject decision for a single hunk in a diff action."""
    file_path = str(body.get("file_path") or "")
    hunk_index = int(body.get("hunk_index") or 0)
    decision = str(body.get("decision") or "accepted")
    if decision not in {"accepted", "rejected"}:
        from fastapi import HTTPException as _H
        raise _H(status_code=422, detail="decision must be 'accepted' or 'rejected'")
    part = await run_sync(service.record_hunk_decision, action_id, file_path, hunk_index, decision)
    return {"action_id": action_id, "file_path": file_path, "hunk_index": hunk_index, "decision": decision, "part_id": part.get("id")}


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
