"""Workspace management API with persisted metadata."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from rag.vector_store import get_vector_store
from workspace.local_paths import normalize_local_workspace_path

logger = logging.getLogger(__name__)

router = APIRouter()

WORKSPACE_DATA_DIR = Path("data/workspaces")
WORKSPACE_DATA_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE_METADATA_FILE = WORKSPACE_DATA_DIR / "metadata.json"


def _load_workspace_store() -> dict[str, dict[str, Any]]:
    if not WORKSPACE_METADATA_FILE.exists():
        return {}

    try:
        with open(WORKSPACE_METADATA_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return {workspace_id: payload for workspace_id, payload in data.items() if isinstance(payload, dict)}
    except Exception as exc:
        logger.warning("Failed to load workspace metadata: %s", exc)

    return {}


def _save_workspace_store(workspaces: dict[str, dict[str, Any]]) -> None:
    with open(WORKSPACE_METADATA_FILE, "w", encoding="utf-8") as handle:
        json.dump(workspaces, handle, ensure_ascii=False, indent=2)


workspaces: dict[str, dict[str, Any]] = _load_workspace_store()


class WorkspaceCreate(BaseModel):
    """Create workspace request."""

    name: str = Field(..., description="Workspace name")
    description: str | None = Field(default=None, description="Workspace description")
    local_path: str | None = Field(default=None, description="Optional local project path")


class Workspace(BaseModel):
    """Workspace metadata."""

    id: str
    name: str
    description: str | None
    created_at: str
    updated_at: str
    document_count: int = 0
    vector_count: int = 0
    vector_collection_name: str
    local_path: str | None = None
    status: str = "active"


class WorkspaceUpdate(BaseModel):
    """Update workspace request."""

    name: str | None = Field(default=None, description="Updated name")
    description: str | None = Field(default=None, description="Updated description")
    local_path: str | None = Field(default=None, description="Updated local project path")


def _persist_workspaces() -> None:
    _save_workspace_store(workspaces)


def _ensure_workspace_exists(workspace_id: str) -> dict[str, Any]:
    workspace = workspaces.get(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


def _refresh_workspace_counts(workspace: dict[str, Any]) -> Workspace:
    vector_store = get_vector_store()
    collection_name = workspace.get("vector_collection_name", workspace["id"])

    try:
        stats = vector_store.get_collection_stats(collection_name)
        vector_count = stats.get("count", 0)
    except Exception:
        vector_count = 0

    workspace["vector_collection_name"] = collection_name
    workspace["vector_count"] = vector_count
    return Workspace(**workspace)


@router.post("/workspaces", response_model=Workspace)
async def create_workspace(data: WorkspaceCreate):
    """Create a workspace."""
    try:
        local_path = normalize_local_workspace_path(data.local_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    workspace_id = f"ws_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    collection_name = workspace_id

    workspace = {
        "id": workspace_id,
        "name": data.name,
        "description": data.description,
        "created_at": now,
        "updated_at": now,
        "document_count": 0,
        "vector_count": 0,
        "vector_collection_name": collection_name,
        "local_path": local_path,
        "status": "active",
    }

    vector_store = get_vector_store()
    vector_store.get_or_create_collection(collection_name)

    workspaces[workspace_id] = workspace
    _persist_workspaces()

    logger.info("Workspace created: %s (%s)", workspace_id, data.name)
    return Workspace(**workspace)


@router.get("/workspaces", response_model=list[Workspace])
async def list_workspaces():
    """List workspaces."""
    result: list[Workspace] = []
    for workspace in workspaces.values():
        result.append(_refresh_workspace_counts(workspace))
    _persist_workspaces()
    return result


@router.get("", response_model=list[Workspace])
async def list_workspaces_compat():
    """Compatibility endpoint for GET /workspace."""
    return await list_workspaces()


@router.get("/workspaces/{workspace_id}", response_model=Workspace)
async def get_workspace(workspace_id: str):
    """Get workspace details."""
    workspace = _ensure_workspace_exists(workspace_id)
    refreshed = _refresh_workspace_counts(workspace)
    _persist_workspaces()
    return refreshed


@router.put("/workspaces/{workspace_id}", response_model=Workspace)
async def update_workspace(workspace_id: str, data: WorkspaceUpdate):
    """Update workspace metadata."""
    workspace = _ensure_workspace_exists(workspace_id)

    if data.name is not None:
        workspace["name"] = data.name
    if data.description is not None:
        workspace["description"] = data.description
    if data.local_path is not None:
        try:
            workspace["local_path"] = normalize_local_workspace_path(data.local_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    workspace["updated_at"] = datetime.now().isoformat()
    _persist_workspaces()

    return Workspace(**workspace)


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(workspace_id: str):
    """Delete a workspace."""
    workspace = _ensure_workspace_exists(workspace_id)
    collection_name = workspace.get("vector_collection_name", workspace_id)

    try:
        vector_store = get_vector_store()
        vector_store.delete_collection(collection_name)
    except Exception as exc:
        logger.error("Failed to delete vector collection %s: %s", collection_name, exc)

    del workspaces[workspace_id]
    _persist_workspaces()

    logger.info("Workspace deleted: %s", workspace_id)
    return {"message": "Deleted successfully", "workspace_id": workspace_id}


@router.get("/workspaces/{workspace_id}/stats")
async def get_workspace_stats(workspace_id: str):
    """Get workspace statistics."""
    workspace = _ensure_workspace_exists(workspace_id)
    collection_name = workspace.get("vector_collection_name", workspace_id)
    vector_store = get_vector_store()

    try:
        stats = vector_store.get_collection_stats(collection_name)
        documents = vector_store.list_documents(collection_name)
        workspace["vector_count"] = stats.get("count", 0)
        workspace["document_count"] = len(documents)
        workspace["updated_at"] = datetime.now().isoformat()
        _persist_workspaces()

        return {
            "workspace_id": workspace_id,
            "vector_count": workspace["vector_count"],
            "document_count": workspace["document_count"],
            "documents": documents,
        }
    except Exception as exc:
        logger.error("Failed to get workspace stats for %s: %s", workspace_id, exc)
        return {
            "workspace_id": workspace_id,
            "vector_count": 0,
            "document_count": 0,
            "documents": [],
        }
