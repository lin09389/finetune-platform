"""DeepAgents-style long-term memory API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .models import (
    MemoryConsolidateRequest,
    MemoryFileResponse,
    MemoryFileUpdateRequest,
    MemoryMigrateRequest,
    MemoryScopeLiteral,
    MemorySearchRequest,
    MemorySearchResultResponse,
)
from .service import get_memory_api_service

router = APIRouter(prefix="/memory", tags=["Memory"])


@router.get("/files", response_model=list[MemoryFileResponse])
async def list_memory_files(
    scope: MemoryScopeLiteral = "user",
    namespace: str = "default",
):
    service = get_memory_api_service()
    return service.list_files(scope=scope, namespace=namespace)


@router.get("/files/{file_id}", response_model=MemoryFileResponse)
async def get_memory_file(file_id: str):
    service = get_memory_api_service()
    try:
        return service.get_file(file_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Memory file not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/files/{file_id}", response_model=MemoryFileResponse)
async def update_memory_file(file_id: str, request: MemoryFileUpdateRequest):
    service = get_memory_api_service()
    try:
        return service.update_file(file_id, request.content, metadata=request.metadata)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Memory file not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/search", response_model=list[MemorySearchResultResponse])
async def search_memory(request: MemorySearchRequest):
    service = get_memory_api_service()
    return service.search(
        query=request.query,
        scope=request.scope,
        namespace=request.namespace,
        user_id=request.user_id,
        top_k=request.top_k,
    )


@router.post("/consolidate")
async def consolidate_memory(request: MemoryConsolidateRequest):
    service = get_memory_api_service()
    return service.consolidate(user_id=request.user_id, session_id=request.session_id)


@router.get("/episodes")
async def list_memory_episodes(
    user_id: str = "default",
    session_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    service = get_memory_api_service()
    return {"events": service.list_episodes(user_id=user_id, session_id=session_id, limit=limit)}


@router.post("/migrate-from-items")
async def migrate_from_items(request: MemoryMigrateRequest):
    service = get_memory_api_service()
    return service.migrate_from_items(user_id=request.user_id)


@router.api_route("/{legacy_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def legacy_memory_api_gone(legacy_path: str):
    _ = legacy_path
    raise HTTPException(status_code=410, detail="Legacy item-based memory API was replaced by /memory/files and /memory/search")
