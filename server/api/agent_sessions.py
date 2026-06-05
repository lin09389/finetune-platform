from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from agent_session.models import (
    AgentAsyncTaskCancelRequest,
    AgentAsyncTaskEventResponse,
    AgentAsyncTaskListResponse,
    AgentAsyncTaskMetricsResponse,
    AgentAsyncTaskResponse,
    AgentAsyncTaskStartRequest,
    AgentAsyncTaskUpdateRequest,
    AgentApprovalResponse,
    AgentEventResponse,
    AgentHitlDecisionRequest,
    AgentMemoryFileResponse,
    AgentPromptRequest,
    AgentSessionCreate,
    AgentSessionOverviewResponse,
    AgentSessionResponse,
    AgentWorkspaceResponse,
)
from agent_session.service import AgentSessionService
from core.config import settings
from core.db_manager import run_sync
from security.auth_middleware import get_current_user_optional
from security.jwt_auth import Role, TokenPayload

router = APIRouter(prefix="/agent-sessions", tags=["Agent Sessions"])
_AGENT_SESSION_SERVICE: AgentSessionService | None = None


def _session_status(session: Any) -> str | None:
    if isinstance(session, dict):
        return session.get("status")
    return getattr(session, "status", None)


def get_agent_session_service() -> AgentSessionService:
    global _AGENT_SESSION_SERVICE
    if _AGENT_SESSION_SERVICE is None:
        _AGENT_SESSION_SERVICE = AgentSessionService()
    return _AGENT_SESSION_SERVICE


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


@router.get("/{session_id}/workspace", response_model=AgentWorkspaceResponse)
async def get_agent_session_workspace(
    session_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        return await run_sync(service.get_workspace, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{session_id}/memory-files", response_model=list[AgentMemoryFileResponse])
async def list_agent_session_memory_files(
    session_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        return await run_sync(service.list_memory_files, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{session_id}/memory-file", response_model=AgentMemoryFileResponse)
async def read_agent_session_memory_file(
    session_id: str,
    path: str = Query(..., min_length=1),
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        return await run_sync(service.read_memory_file, session_id, path)
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


@router.post("/{session_id}/async-tasks", response_model=AgentAsyncTaskResponse)
async def start_async_agent_task(
    session_id: str,
    request: AgentAsyncTaskStartRequest,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        return await service.start_async_subtask(session_id, request.subagent_type, request.description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{session_id}/async-tasks", response_model=AgentAsyncTaskListResponse)
async def list_async_agent_tasks(
    session_id: str,
    status_filter: str | None = None,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        return await run_sync(service.list_async_subtasks, session_id, status_filter)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{session_id}/async-tasks/metrics", response_model=AgentAsyncTaskMetricsResponse)
async def get_async_agent_task_metrics(
    session_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        return await run_sync(service.get_async_subtask_metrics, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{session_id}/async-tasks/events", response_model=list[AgentAsyncTaskEventResponse])
async def list_async_agent_task_events(
    session_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        return await run_sync(service.list_async_subtask_events, session_id, None, limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{session_id}/async-tasks/{task_id}", response_model=AgentAsyncTaskResponse)
async def get_async_agent_task(
    session_id: str,
    task_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        return await run_sync(service.check_async_subtask, session_id, task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{session_id}/async-tasks/{task_id}/events", response_model=list[AgentAsyncTaskEventResponse])
async def list_single_async_agent_task_events(
    session_id: str,
    task_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        return await run_sync(service.list_async_subtask_events, session_id, task_id, limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{session_id}/async-tasks/{task_id}", response_model=AgentAsyncTaskResponse)
async def update_async_agent_task(
    session_id: str,
    task_id: str,
    request: AgentAsyncTaskUpdateRequest,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        return await service.update_async_subtask(session_id, task_id, request.description)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{session_id}/async-tasks/{task_id}/cancel", response_model=AgentAsyncTaskResponse)
async def cancel_async_agent_task(
    session_id: str,
    task_id: str,
    request: AgentAsyncTaskCancelRequest | None = None,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        reason = request.reason if request else None
        return await service.cancel_async_subtask(session_id, task_id, reason)
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
