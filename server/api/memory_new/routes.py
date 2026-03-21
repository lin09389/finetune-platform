# -*- coding: utf-8 -*-

"""
记忆 API 路由
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List

from .service import get_memory_api_service
from .models import (
    MemoryItem,
    MemoryType,
    MemoryCreateRequest,
    MemoryUpdateRequest,
    MemorySearchRequest,
    MemorySearchResult
)

router = APIRouter(prefix="/memory", tags=["Memory"])


@router.get("/")
async def list_memories(
    memory_type: Optional[MemoryType] = None,
    limit: int = Query(default=50, ge=1, le=200),
    user_id: str = "default"
):
    """列出记忆"""
    service = get_memory_api_service()
    memories = service.list_memories(user_id, memory_type, limit)
    
    return {
        "memories": [
            {
                "id": m.id,
                "content": m.content,
                "type": m.type.value,
                "importance": m.importance,
                "created_at": m.created_at.isoformat(),
                "access_count": m.access_count
            }
            for m in memories
        ],
        "total": len(memories)
    }


@router.post("/")
async def create_memory(request: MemoryCreateRequest, user_id: str = "default"):
    """创建记忆"""
    service = get_memory_api_service()
    memory = service.create_memory(
        user_id=user_id,
        content=request.content,
        memory_type=request.memory_type,
        importance=request.importance,
        metadata=request.metadata
    )
    
    return {
        "id": memory.id,
        "content": memory.content,
        "type": memory.type.value,
        "importance": memory.importance,
        "created_at": memory.created_at.isoformat()
    }


@router.get("/{memory_id}")
async def get_memory(memory_id: str):
    """获取记忆"""
    service = get_memory_api_service()
    memory = service.get_memory(memory_id)
    
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    return {
        "id": memory.id,
        "content": memory.content,
        "type": memory.type.value,
        "importance": memory.importance,
        "source": memory.source,
        "created_at": memory.created_at.isoformat(),
        "updated_at": memory.updated_at.isoformat(),
        "access_count": memory.access_count,
        "metadata": memory.metadata
    }


@router.put("/{memory_id}")
async def update_memory(memory_id: str, request: MemoryUpdateRequest):
    """更新记忆"""
    service = get_memory_api_service()
    memory = service.update_memory(
        memory_id=memory_id,
        content=request.content,
        importance=request.importance,
        metadata=request.metadata
    )
    
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    return {
        "id": memory.id,
        "content": memory.content,
        "importance": memory.importance,
        "updated_at": memory.updated_at.isoformat()
    }


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str):
    """删除记忆"""
    service = get_memory_api_service()
    success = service.delete_memory(memory_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    return {"success": True, "memory_id": memory_id}


@router.post("/recall")
async def recall_memories(request: MemorySearchRequest, user_id: str = "default"):
    """检索记忆"""
    service = get_memory_api_service()
    results = service.search_memories(
        user_id=user_id,
        query=request.query,
        top_k=request.top_k,
        memory_type=request.memory_type
    )
    
    return {
        "memories": [
            {
                "id": r.id,
                "content": r.content,
                "type": r.type.value,
                "importance": r.importance,
                "relevance": r.relevance,
                "created_at": r.created_at.isoformat()
            }
            for r in results
        ],
        "query": request.query,
        "total": len(results)
    }


@router.get("/stats/summary")
async def get_memory_stats(user_id: str = "default"):
    """获取记忆统计"""
    service = get_memory_api_service()
    return service.get_stats(user_id)


@router.delete("/clear")
async def clear_memories(user_id: str = "default"):
    """清空记忆"""
    service = get_memory_api_service()
    count = service.clear_memories(user_id)
    
    return {"success": True, "cleared_count": count}
