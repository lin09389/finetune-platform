from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from agent_session.diagnostics import AgentFrontendDiagnosticsRepository
from agent_session.errors import AgentConfigurationError
from agent_session.models import (
    AgentApprovalResponse,
    AgentAsyncTaskCancelRequest,
    AgentAsyncTaskEventResponse,
    AgentAsyncTaskListResponse,
    AgentAsyncTaskMetricsResponse,
    AgentAsyncTaskResponse,
    AgentAsyncTaskStartRequest,
    AgentAsyncTaskUpdateRequest,
    AgentEventResponse,
    AgentExecutionPlanRecoverRequest,
    AgentExecutionPlanRecoveryResponse,
    AgentFrontendDiagnosticsBatch,
    AgentHitlDecisionRequest,
    AgentMemoryFileResponse,
    AgentPromptRequest,
    AgentSessionCreate,
    AgentSessionOverviewResponse,
    AgentSessionPreferencesUpdate,
    AgentSessionResponse,
    AgentWorkspaceResponse,
)
from agent_session.service import AgentSessionService
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from core.config import settings
from core.db_manager import run_sync
from security.auth_middleware import get_current_user_optional
from security.jwt_auth import Role, TokenPayload

router = APIRouter(prefix="/agent-sessions", tags=["Agent Sessions"])
_AGENT_SESSION_SERVICE: AgentSessionService | None = None
_AGENT_FRONTEND_DIAGNOSTICS_REPOSITORY: AgentFrontendDiagnosticsRepository | None = None


def _session_status(session: Any) -> str | None:
    if isinstance(session, dict):
        return session.get("status")
    return getattr(session, "status", None)


def _session_metadata(session: Any) -> dict[str, Any]:
    metadata = session.get("metadata") if isinstance(session, dict) else getattr(session, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _session_owner_id(session: Any) -> str | None:
    metadata = _session_metadata(session)
    owner = str(metadata.get("user_id") or "").strip()
    return owner or None


def _user_can_access_session(session: Any, current_user: TokenPayload) -> bool:
    owner = _session_owner_id(session)
    if not owner:
        return True
    if owner == current_user.user_id:
        return True
    return current_user.role in {Role.ADMIN, Role.SUPER_ADMIN}


def _enforce_session_access(session: Any, current_user: TokenPayload) -> None:
    if not _user_can_access_session(session, current_user):
        raise HTTPException(status_code=403, detail="Agent session access denied")


def _sse_event(event_name: str, data: dict[str, Any], event_id: str | None = None) -> str:
    event_id_line = f"id: {event_id}\n" if event_id else ""
    return f"{event_id_line}event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _require_accessible_session(
    service: AgentSessionService,
    session_id: str,
    current_user: TokenPayload,
) -> AgentSessionResponse:
    try:
        session = await run_sync(service.get_session, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _enforce_session_access(session, current_user)
    return session


async def _require_accessible_part_session(
    service: AgentSessionService,
    part_id: str,
    current_user: TokenPayload,
) -> AgentSessionResponse:
    part = await run_sync(service.repository.get_part, part_id)
    if not part:
        raise HTTPException(status_code=404, detail="Agent part not found")
    return await _require_accessible_session(service, str(part.get("session_id") or ""), current_user)


def _resolve_artifact_project_path(project_root: Path, artifact_path: str) -> Path:
    raw_path = str(artifact_path or "").strip()
    if not raw_path:
        raise HTTPException(status_code=400, detail="Artifact path is empty")
    normalized = raw_path.replace("\\", "/")
    if normalized == "/workspace":
        normalized = ""
    elif normalized.startswith("/workspace/"):
        normalized = normalized[len("/workspace/"):]
    elif normalized.startswith("workspace/"):
        normalized = normalized[len("workspace/"):]

    candidate = Path(normalized)
    target_path = candidate if candidate.is_absolute() else project_root / normalized
    try:
        resolved_target = target_path.resolve()
        if not resolved_target.is_relative_to(project_root):
            raise HTTPException(status_code=403, detail="Access denied: target path is outside project root")
        return resolved_target
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid target path")


def get_agent_session_service() -> AgentSessionService:
    global _AGENT_SESSION_SERVICE
    if _AGENT_SESSION_SERVICE is None:
        _AGENT_SESSION_SERVICE = AgentSessionService()
    return _AGENT_SESSION_SERVICE


def get_agent_frontend_diagnostics_repository() -> AgentFrontendDiagnosticsRepository:
    global _AGENT_FRONTEND_DIAGNOSTICS_REPOSITORY
    if _AGENT_FRONTEND_DIAGNOSTICS_REPOSITORY is None:
        _AGENT_FRONTEND_DIAGNOSTICS_REPOSITORY = AgentFrontendDiagnosticsRepository()
    return _AGENT_FRONTEND_DIAGNOSTICS_REPOSITORY


async def get_agent_session_user(
    current_user: TokenPayload | None = Depends(get_current_user_optional),
) -> TokenPayload:
    if current_user:
        return current_user
    from security.runtime_policy import allow_local_agent_auth, is_production_environment

    # Production/staging hard-closed; non-production needs ALLOW_LOCAL_AGENT_AUTH.
    if is_production_environment(settings) or not allow_local_agent_auth(settings):
        raise HTTPException(status_code=401, detail="Missing authorization")
    return TokenPayload(
        user_id="desktop-local-user",
        username="desktop",
        role=Role.USER,
        permissions=["agent_sessions:local"],
    )


@router.post("/diagnostics/batch")
async def report_agent_frontend_diagnostics(
    request: AgentFrontendDiagnosticsBatch,
    repository: AgentFrontendDiagnosticsRepository = Depends(get_agent_frontend_diagnostics_repository),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    for report in request.reports:
        await run_sync(repository.upsert, report.model_dump(), current_user.user_id)
    return {"accepted": len(request.reports)}


@router.get("/diagnostics/summary")
async def get_agent_frontend_diagnostics_summary(
    repository: AgentFrontendDiagnosticsRepository = Depends(get_agent_frontend_diagnostics_repository),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    if current_user.role not in {Role.ADMIN, Role.SUPER_ADMIN}:
        raise HTTPException(status_code=403, detail="Agent diagnostics summary requires administrator access")
    return await run_sync(repository.summary)


@router.post("", response_model=AgentSessionResponse)
async def create_agent_session(
    request: AgentSessionCreate,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        return await run_sync(service.create_session, request, current_user.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[AgentSessionResponse])
async def list_agent_sessions(
    limit: int = Query(default=100, ge=1, le=500),
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    include_all = current_user.role in {Role.ADMIN, Role.SUPER_ADMIN}
    return await run_sync(service.list_sessions, current_user.user_id, include_all, limit)


@router.get("/{session_id}", response_model=AgentSessionResponse)
async def get_agent_session(
    session_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    return await _require_accessible_session(service, session_id, current_user)


@router.patch("/{session_id}/preferences", response_model=AgentSessionResponse)
async def update_agent_session_preferences(
    session_id: str,
    request: AgentSessionPreferencesUpdate,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    await _require_accessible_session(service, session_id, current_user)
    try:
        return await run_sync(service.update_session_preferences, session_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{session_id}/overview", response_model=AgentSessionOverviewResponse)
async def get_agent_session_overview(
    session_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    await _require_accessible_session(service, session_id, current_user)
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
    await _require_accessible_session(service, session_id, current_user)
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
    await _require_accessible_session(service, session_id, current_user)
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
    await _require_accessible_session(service, session_id, current_user)
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
    await _require_accessible_session(service, session_id, current_user)
    try:
        return await service.start_prompt_detached(session_id, request)
    except AgentConfigurationError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": str(exc),
                "failure_kind": exc.failure_kind,
                "next_action": "configure_model",
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        try:
            return await run_sync(service.record_prompt_failure, session_id, exc)
        except ValueError as value_exc:
            raise HTTPException(status_code=404, detail=str(value_exc)) from value_exc
        except Exception:
            raise HTTPException(status_code=500, detail=f"Prompt failed: {exc}") from exc


@router.post("/{session_id}/interrupt", response_model=AgentSessionResponse)
async def interrupt_agent_session(
    session_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    await _require_accessible_session(service, session_id, current_user)
    try:
        return await run_sync(service.interrupt_session, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{session_id}/execution-plan/nodes/{node_id}/recover", response_model=AgentExecutionPlanRecoveryResponse)
async def recover_agent_execution_plan_node(
    session_id: str,
    node_id: str,
    request: AgentExecutionPlanRecoverRequest,
    background_tasks: BackgroundTasks,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    await _require_accessible_session(service, session_id, current_user)
    try:
        return await service.recover_execution_node(session_id, node_id, request, background_tasks)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 422
        raise HTTPException(status_code=status_code, detail=message) from exc


@router.post("/{session_id}/async-tasks", response_model=AgentAsyncTaskResponse)
async def start_async_agent_task(
    session_id: str,
    request: AgentAsyncTaskStartRequest,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    await _require_accessible_session(service, session_id, current_user)
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
    await _require_accessible_session(service, session_id, current_user)
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
    await _require_accessible_session(service, session_id, current_user)
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
    await _require_accessible_session(service, session_id, current_user)
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
    await _require_accessible_session(service, session_id, current_user)
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
    await _require_accessible_session(service, session_id, current_user)
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
    await _require_accessible_session(service, session_id, current_user)
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
    await _require_accessible_session(service, session_id, current_user)
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
    await _require_accessible_session(service, session_id, current_user)
    return await run_sync(service.list_events, session_id)


@router.get("/{session_id}/events/stream")
async def stream_agent_session_events(
    session_id: str,
    since_event_id: str | None = None,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    await _require_accessible_session(service, session_id, current_user)

    async def event_stream():
        initial_since_id = since_event_id or last_event_id
        seen = {initial_since_id: True} if initial_since_id else {}
        since_id = initial_since_id
        last_heartbeat = time.monotonic()
        heartbeat_interval = 15.0
        yield "retry: 3000\n\n"

        queue = service.subscribe_events(session_id)
        try:
            snapshot = await run_sync(service.build_session_snapshot_chunk, session_id)
            yield _sse_event("agent_session_event", snapshot, str(snapshot.get("id") or ""))
            last_heartbeat = time.monotonic()

            for event in await run_sync(service.list_events, session_id, since_id):
                if event.get("id") in seen:
                    continue
                if len(seen) >= 1000:
                    seen.pop(next(iter(seen)))
                seen[event["id"]] = True
                since_id = event["id"]
                chunk = await run_sync(service.build_stream_chunk, event)
                yield _sse_event("agent_session_event", chunk, str(chunk.get("id") or ""))
                last_heartbeat = time.monotonic()

            session = await run_sync(service.get_session, session_id)
            status = _session_status(session)
            if status in AgentSessionService.TERMINAL_STATUSES:
                yield _sse_event("agent_session_done", {"status": status})
                return

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=heartbeat_interval)
                except TimeoutError:
                    now = time.monotonic()
                    if now - last_heartbeat >= heartbeat_interval:
                        yield ": heartbeat\n\n"
                        last_heartbeat = now
                    session = await run_sync(service.get_session, session_id)
                    status = _session_status(session)
                    if status in AgentSessionService.TERMINAL_STATUSES:
                        yield _sse_event("agent_session_done", {"status": status})
                        break
                    continue

                event_id = event.get("id", "")
                if event_id in seen:
                    continue
                if len(seen) >= 1000:
                    seen.pop(next(iter(seen)))
                seen[event_id] = True
                since_id = event_id
                chunk = await run_sync(service.build_stream_chunk, event)
                yield _sse_event("agent_session_event", chunk, str(chunk.get("id") or ""))
                last_heartbeat = time.monotonic()

                session_status = chunk.get("session_status")
                if session_status in AgentSessionService.TERMINAL_STATUSES:
                    yield _sse_event("agent_session_done", {"status": session_status})
                    break
        finally:
            service.unsubscribe_events(session_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    )


@router.get("/{session_id}/artifacts/{artifact_id:path}/original")
async def get_artifact_original(
    session_id: str,
    artifact_id: str,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
) -> str:
    """Retrieve the original content of a modified artifact before changes were applied."""
    try:
        session = await _require_accessible_session(service, session_id, current_user)

        overview = await run_sync(service.get_overview, session_id)
        artifact = next((item for item in overview.artifacts if item.id == artifact_id), None)
        if artifact is None:
            raise HTTPException(status_code=404, detail="Artifact not found")

        project_path = session.project_path
        if not project_path:
            raise HTTPException(status_code=400, detail="Session has no project path configured")

        project_root = Path(project_path).resolve()
        resolved_target = _resolve_artifact_project_path(project_root, artifact.path)

        if not resolved_target.exists() or not resolved_target.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        try:
            return resolved_target.read_text(encoding="utf-8", errors="ignore")
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
    background_tasks: BackgroundTasks,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    await _require_accessible_part_session(service, permission_id, current_user)
    try:
        session = await run_sync(
            service.start_permission_resume_background,
            permission_id,
            [{"type": "approve"}],
            background_tasks,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    part = next((item for item in session.parts if item.id == permission_id), None)
    if not part:
        raise HTTPException(status_code=404, detail="Permission part not found")
    return AgentApprovalResponse(part=part, session=session)


@permission_router.post("/agent-permissions/{permission_id}/reject", response_model=AgentApprovalResponse)
async def reject_agent_permission(
    permission_id: str,
    background_tasks: BackgroundTasks,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    await _require_accessible_part_session(service, permission_id, current_user)
    try:
        session = await run_sync(
            service.start_permission_resume_background,
            permission_id,
            [{"type": "reject"}],
            background_tasks,
        )
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
    background_tasks: BackgroundTasks,
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    await _require_accessible_part_session(service, permission_id, current_user)
    try:
        decisions = [decision.model_dump(exclude_none=True) for decision in request.decisions]
        session = await run_sync(
            service.start_permission_resume_background,
            permission_id,
            decisions,
            background_tasks,
        )
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 422
        raise HTTPException(status_code=status_code, detail=message) from exc
    part = next((item for item in session.parts if item.id == permission_id), None)
    if not part:
        raise HTTPException(status_code=404, detail="Permission part not found")
    return AgentApprovalResponse(part=part, session=session)
