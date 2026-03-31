"""
工作空间管理 API
管理 RAG 知识库的工作空间
"""
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from rag.vector_store import get_vector_store

logger = logging.getLogger(__name__)

router = APIRouter()

workspaces: dict[str, dict[str, Any]] = {}


class WorkspaceCreate(BaseModel):
    """创建工作空间请求"""
    name: str = Field(..., description="工作空间名称")
    description: str | None = Field(default=None, description="描述")


class Workspace(BaseModel):
    """工作空间信息"""
    id: str
    name: str
    description: str | None
    created_at: str
    updated_at: str
    document_count: int = 0
    vector_count: int = 0


class WorkspaceUpdate(BaseModel):
    """更新工作空间请求"""
    name: str | None = Field(default=None, description="新名称")
    description: str | None = Field(default=None, description="新描述")


@router.post("/workspaces", response_model=Workspace)
async def create_workspace(data: WorkspaceCreate):
    """创建工作空间"""
    workspace_id = f"ws_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()

    workspace = {
        "id": workspace_id,
        "name": data.name,
        "description": data.description,
        "created_at": now,
        "updated_at": now,
        "document_count": 0,
        "vector_count": 0
    }

    workspaces[workspace_id] = workspace

    vector_store = get_vector_store()
    vector_store.get_or_create_collection(workspace_id)

    logger.info(f"工作空间已创建：{workspace_id}, 名称：{data.name}")

    return workspace


@router.get("/workspaces", response_model=list[Workspace])
async def list_workspaces():
    """获取工作空间列表"""
    vector_store = get_vector_store()

    result = []
    for ws in workspaces.values():
        try:
            stats = vector_store.get_collection_stats(ws["id"])
            ws["vector_count"] = stats.get("count", 0)
        except Exception:
            ws["vector_count"] = 0

        result.append(Workspace(**ws))

    return result


@router.get("/workspaces/{workspace_id}", response_model=Workspace)
async def get_workspace(workspace_id: str):
    """获取工作空间详情"""
    if workspace_id not in workspaces:
        raise HTTPException(status_code=404, detail="工作空间不存在")

    workspace = workspaces[workspace_id]

    try:
        vector_store = get_vector_store()
        stats = vector_store.get_collection_stats(workspace_id)
        workspace["vector_count"] = stats.get("count", 0)
    except Exception:
        workspace["vector_count"] = 0

    return workspace


@router.put("/workspaces/{workspace_id}", response_model=Workspace)
async def update_workspace(workspace_id: str, data: WorkspaceUpdate):
    """更新工作空间"""
    if workspace_id not in workspaces:
        raise HTTPException(status_code=404, detail="工作空间不存在")

    workspace = workspaces[workspace_id]

    if data.name is not None:
        workspace["name"] = data.name
    if data.description is not None:
        workspace["description"] = data.description

    workspace["updated_at"] = datetime.now().isoformat()

    return workspace


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(workspace_id: str):
    """删除工作空间"""
    if workspace_id not in workspaces:
        raise HTTPException(status_code=404, detail="工作空间不存在")

    try:
        vector_store = get_vector_store()
        vector_store.delete_collection(workspace_id)
    except Exception as e:
        logger.error(f"删除向量集合失败：{e}")

    del workspaces[workspace_id]

    logger.info(f"工作空间已删除：{workspace_id}")

    return {"message": "删除成功", "workspace_id": workspace_id}


@router.get("/workspaces/{workspace_id}/stats")
async def get_workspace_stats(workspace_id: str):
    """获取工作空间统计信息"""
    if workspace_id not in workspaces:
        raise HTTPException(status_code=404, detail="工作空间不存在")

    vector_store = get_vector_store()

    try:
        stats = vector_store.get_collection_stats(workspace_id)
        documents = vector_store.list_documents(workspace_id)

        return {
            "workspace_id": workspace_id,
            "vector_count": stats.get("count", 0),
            "document_count": len(documents),
            "documents": documents
        }
    except Exception as e:
        logger.error(f"获取统计失败：{e}")
        return {
            "workspace_id": workspace_id,
            "vector_count": 0,
            "document_count": 0,
            "documents": []
        }
