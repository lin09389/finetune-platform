
"""
记忆 API 路由
"""

from fastapi import APIRouter, HTTPException, Query

from .models import (
    MemoryCreateRequest,
    MemorySearchRequest,
    MemoryType,
    MemoryUpdateRequest,
)
from .service import get_memory_api_service

router = APIRouter(prefix="/memory", tags=["Memory"])


@router.get("/")
async def list_memories(
    memory_type: MemoryType | None = None,
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


@router.get("/export")
async def export_memory_state(user_id: str = "default"):
    """导出记忆状态"""
    service = get_memory_api_service()
    state = service.export_state(user_id)
    return {"state": state}


@router.post("/import")
async def import_memory_state(state: dict, user_id: str = "default"):
    """导入记忆状态"""
    service = get_memory_api_service()
    success = service.import_state(user_id, state)
    return {"success": success}


@router.get("/summary")
async def get_memory_summary(user_id: str = "default"):
    """获取记忆摘要"""
    service = get_memory_api_service()
    summary = service.get_summary(user_id)
    return {"summary": summary}


@router.get("/context")
async def get_memory_context(query: str, user_id: str = "default", session_id: str = None):
    """获取记忆上下文"""
    service = get_memory_api_service()
    context = service.get_context(user_id, query, session_id)
    return {"context": context}


@router.get("/sessions")
async def list_sessions():
    """列出会话"""
    service = get_memory_api_service()
    sessions = service.list_sessions()
    return {"sessions": sessions}


@router.get("/sessions/{session_id}")
async def get_session_context(session_id: str, max_tokens: int = 4000):
    """获取会话上下文"""
    service = get_memory_api_service()
    result = service.get_session_context(session_id, max_tokens)
    return result


@router.post("/sessions/{session_id}/messages")
async def add_session_message(session_id: str, role: str, content: str, entities: list[str] = None):
    """添加会话消息"""
    service = get_memory_api_service()
    success = service.add_session_message(session_id, role, content, entities)
    return {"success": success}


@router.delete("/sessions/{session_id}")
async def clear_session(session_id: str):
    """清空会话"""
    service = get_memory_api_service()
    success = service.clear_session(session_id)
    return {"success": success}


@router.get("/sessions/{session_id}/active-entities")
async def get_active_entities(session_id: str, threshold: float = 0.3):
    """获取活跃实体"""
    service = get_memory_api_service()
    entities = service.get_active_entities(session_id, threshold)
    return {"entities": entities}


@router.post("/graph/entities")
async def add_graph_entity(name: str, entity_type: str, attributes: dict = None, confidence: float = 0.5):
    """添加图谱实体"""
    service = get_memory_api_service()
    entity_id, is_new = service.add_entity(name, entity_type, attributes, confidence)
    return {"entity_id": entity_id, "is_new": is_new}


@router.post("/graph/relations")
async def add_graph_relation(source_name: str, target_name: str, relation_type: str, evidence: str = ""):
    """添加图谱关系"""
    service = get_memory_api_service()
    relation_id = service.add_relation(source_name, target_name, relation_type, evidence)
    return {"relation_id": relation_id}


@router.get("/graph/entities/{entity_id}")
async def get_graph_entity(entity_id: str):
    """获取图谱实体"""
    service = get_memory_api_service()
    entity = service.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"entity": entity}


@router.post("/graph/context")
async def get_graph_context(entity_id: str, depth: int = 2):
    """获取图谱上下文"""
    service = get_memory_api_service()
    context = service.get_entity_context(entity_id, depth)
    return {"context": context}


@router.post("/graph/path")
async def find_graph_path(source_id: str, target_id: str, max_depth: int = 4):
    """查找图谱路径"""
    service = get_memory_api_service()
    paths = service.find_path(source_id, target_id, max_depth)
    return {"paths": paths}


@router.post("/graph/search")
async def search_graph(query: str, entity_types: list[str] = None, limit: int = 10):
    """搜索图谱"""
    service = get_memory_api_service()
    results = service.search_graph(query, entity_types, limit)
    return {"results": results}


@router.get("/graph/stats")
async def get_graph_stats():
    """获取图谱统计"""
    service = get_memory_api_service()
    stats = service.get_graph_stats()
    return {"stats": stats}


@router.delete("/graph/entities/{entity_id}")
async def delete_graph_entity(entity_id: str):
    """删除图谱实体"""
    service = get_memory_api_service()
    success = service.delete_entity(entity_id)
    return {"success": success}


@router.get("/graph/relations")
async def list_graph_relations():
    """列出图谱关系"""
    service = get_memory_api_service()
    relations = service.list_relations()
    return {"relations": relations}
