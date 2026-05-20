"""Long-term memory API routes."""

from fastapi import APIRouter, HTTPException, Query

from .models import MemoryCreateRequest, MemorySearchRequest, MemoryType, MemoryUpdateRequest
from .service import get_memory_api_service

router = APIRouter(prefix="/memory", tags=["Memory"])


@router.get("/")
async def list_memories(
    memory_type: MemoryType | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user_id: str = "default",
):
    service = get_memory_api_service()
    memories = service.list_memories(user_id, memory_type, limit)

    return {
        "memories": [
            {
                "id": memory.id,
                "content": memory.content,
                "type": memory.type.value,
                "importance": memory.importance,
                "created_at": memory.created_at.isoformat(),
                "last_accessed": memory.updated_at.isoformat(),
                "access_count": memory.access_count,
                "vector_state": memory.vector_state,
                "storage_mode": memory.storage_mode,
            }
            for memory in memories
        ],
        "total": len(memories),
    }


@router.post("/")
async def create_memory(request: MemoryCreateRequest, user_id: str = "default"):
    service = get_memory_api_service()
    memory = service.create_memory(
        user_id=user_id,
        content=request.content,
        memory_type=request.memory_type,
        importance=request.importance,
        metadata=request.metadata,
    )

    return {
        "id": memory.id,
        "content": memory.content,
        "type": memory.type.value,
        "importance": memory.importance,
        "created_at": memory.created_at.isoformat(),
        "vector_state": memory.vector_state,
        "storage_mode": memory.storage_mode,
    }


@router.post("/recall")
async def recall_memories(request: MemorySearchRequest, user_id: str = "default"):
    service = get_memory_api_service()
    results = service.search_memories(
        user_id=user_id,
        query=request.query,
        top_k=request.top_k,
        memory_type=request.memory_type,
    )

    return {
        "memories": [
            {
                "id": result.id,
                "content": result.content,
                "type": result.type.value,
                "importance": result.importance,
                "relevance": result.relevance,
                "created_at": result.created_at.isoformat(),
                "last_accessed": result.created_at.isoformat(),
                "access_count": 0,
                "vector_state": result.vector_state,
                "storage_mode": result.storage_mode,
            }
            for result in results
        ],
        "query": request.query,
        "total": len(results),
    }


@router.get("/stats/summary")
async def get_memory_stats(user_id: str = "default"):
    service = get_memory_api_service()
    return service.get_stats(user_id)


@router.delete("/clear")
async def clear_memories(user_id: str = "default"):
    service = get_memory_api_service()
    count = service.clear_memories(user_id)
    return {"success": True, "cleared_count": count}


@router.get("/export")
async def export_memory_state(user_id: str = "default"):
    service = get_memory_api_service()
    return {"state": service.export_state(user_id)}


@router.post("/import")
async def import_memory_state(state: dict, user_id: str = "default"):
    service = get_memory_api_service()
    return {"success": service.import_state(user_id, state)}


@router.get("/summary")
async def get_memory_summary(user_id: str = "default"):
    service = get_memory_api_service()
    return {"summary": service.get_summary(user_id)}


@router.get("/{memory_id}")
async def get_memory(memory_id: str, user_id: str = "default"):
    service = get_memory_api_service()
    memory = service.get_memory(memory_id, user_id=user_id)

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
        "metadata": memory.metadata,
        "vector_state": memory.vector_state,
        "storage_mode": memory.storage_mode,
    }


@router.put("/{memory_id}")
async def update_memory(memory_id: str, request: MemoryUpdateRequest, user_id: str = "default"):
    service = get_memory_api_service()
    memory = service.update_memory(
        memory_id=memory_id,
        content=request.content,
        importance=request.importance,
        metadata=request.metadata,
        user_id=user_id,
    )

    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    return {
        "id": memory.id,
        "content": memory.content,
        "importance": memory.importance,
        "updated_at": memory.updated_at.isoformat(),
        "vector_state": memory.vector_state,
        "storage_mode": memory.storage_mode,
    }


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str, user_id: str = "default"):
    service = get_memory_api_service()
    success = service.delete_memory(memory_id, user_id=user_id)

    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")

    return {"success": True, "memory_id": memory_id}
