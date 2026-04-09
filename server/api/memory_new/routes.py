"""Memory API routes."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from memory.intelligent_extractor import extract_memories

from .models import (
    MemoryCreateRequest,
    MemorySearchRequest,
    MemoryType,
    MemoryUpdateRequest,
)
from .service import get_memory_api_service

router = APIRouter(prefix="/memory", tags=["Memory"])


class SessionMessageRequest(BaseModel):
    role: str
    content: str
    entities: list[str] | None = None


class ProcessMessageRequest(BaseModel):
    message: str
    role: str = "user"
    user_id: str = "default"
    session_id: str | None = None
    extract_memories: bool = True


class GraphEntityRequest(BaseModel):
    name: str
    entity_type: str
    attributes: dict[str, Any] | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)


class GraphRelationRequest(BaseModel):
    source_name: str
    target_name: str
    relation_type: str
    evidence: str = ""


class GraphContextRequest(BaseModel):
    entity_id: str
    depth: int = 2


class GraphPathRequest(BaseModel):
    source_id: str
    target_id: str
    max_depth: int = 4


class GraphSearchRequest(BaseModel):
    query: str = ""
    entity_types: list[str] | None = None
    limit: int = 10


def _serialize_entity(entity: dict[str, Any] | None, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(fallback or {})
    payload.update(entity or {})
    return {
        "id": str(payload.get("id", "")),
        "name": str(payload.get("name", "")),
        "entity_type": str(payload.get("entity_type") or payload.get("type") or "concept"),
        "attributes": payload.get("attributes", {}) or {},
        "confidence": float(payload.get("confidence", 0.5) or 0.5),
        "created_at": str(payload.get("created_at", "")),
        "updated_at": str(payload.get("updated_at", "")),
        "access_count": int(payload.get("access_count", 0) or 0),
    }


def _serialize_relation(relation: dict[str, Any] | None, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(fallback or {})
    payload.update(relation or {})
    return {
        "id": str(payload.get("id", "")),
        "source_id": str(payload.get("source_id", "")),
        "target_id": str(payload.get("target_id", "")),
        "relation_type": str(payload.get("relation_type") or payload.get("relation") or "related_to"),
        "weight": float(payload.get("weight", 1.0) or 1.0),
        "evidence": str(payload.get("evidence", "")),
        "confidence": float(payload.get("confidence", 0.5) or 0.5),
        "created_at": str(payload.get("created_at", "")),
    }


def _coerce_fact_type(value: str | None) -> MemoryType:
    try:
        return MemoryType(value or MemoryType.KNOWLEDGE.value)
    except ValueError:
        return MemoryType.KNOWLEDGE


def _serialize_fact(memory: Any, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    if hasattr(memory, "model_dump"):
        payload = memory.model_dump(mode="json")
    elif isinstance(memory, dict):
        payload = dict(memory)
    else:
        payload = dict(fallback or {})
    if fallback:
        for key, value in fallback.items():
            payload.setdefault(key, value)

    return {
        "id": str(payload.get("id", "")),
        "content": str(payload.get("content", "")),
        "type": str(payload.get("type", MemoryType.KNOWLEDGE.value)),
        "importance": float(payload.get("importance", 0.5) or 0.5),
        "created_at": str(payload.get("created_at", "")),
        "last_accessed": str(
            payload.get("updated_at")
            or payload.get("last_accessed")
            or payload.get("created_at")
            or ""
        ),
        "access_count": int(payload.get("access_count", 0) or 0),
        "relevance": float(payload.get("relevance", 0.0) or 0.0),
    }


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
async def import_memory_state(state: dict[str, Any], user_id: str = "default"):
    service = get_memory_api_service()
    return {"success": service.import_state(user_id, state)}


@router.get("/summary")
async def get_memory_summary(user_id: str = "default"):
    service = get_memory_api_service()
    return {"summary": service.get_summary(user_id)}


@router.get("/context")
async def get_memory_context(query: str, user_id: str = "default", session_id: str | None = None):
    service = get_memory_api_service()
    return {"context": service.get_context(user_id, query, session_id)}


@router.post("/extract")
async def extract_memory_candidates(request: ProcessMessageRequest):
    extraction = extract_memories(request.message, request.role).to_dict()

    entities = [
        _serialize_entity(
            None,
            {
                **entity,
                "entity_type": entity.get("type", "concept"),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
        )
        for entity in extraction.get("entities", [])
    ]
    relations = [
        _serialize_relation(
            None,
            {
                **relation,
                "relation_type": relation.get("relation", "related_to"),
                "created_at": datetime.now().isoformat(),
            },
        )
        for relation in extraction.get("relations", [])
    ]
    facts = [
        _serialize_fact(
            None,
            {
                "id": "",
                "content": fact.get("content", ""),
                "type": _coerce_fact_type(fact.get("type")).value,
                "importance": float(fact.get("confidence", 0.5) or 0.5),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "access_count": 0,
            },
        )
        for fact in extraction.get("facts", [])
    ]

    return {
        "extraction": {
            "entities": entities,
            "relations": relations,
            "facts": facts,
            "confidence": extraction.get("confidence", 0.0),
            "extraction_method": extraction.get("extraction_method", "rule"),
        }
    }


@router.post("/process")
async def process_message(request: ProcessMessageRequest):
    service = get_memory_api_service()
    session_id = request.session_id or "default"
    stored = service.add_session_message(session_id, request.role, request.message)

    extraction = extract_memories(request.message, request.role).to_dict() if request.extract_memories else {
        "entities": [],
        "relations": [],
        "facts": [],
    }

    entities_extracted: list[dict[str, Any]] = []
    relations_extracted: list[dict[str, Any]] = []
    facts_extracted: list[dict[str, Any]] = []

    for entity in extraction.get("entities", []):
        entity_id, _ = service.add_entity(
            entity.get("name", ""),
            entity.get("type", "concept"),
            entity.get("attributes", {}),
            float(entity.get("confidence", 0.5) or 0.5),
        )
        stored_entity = service.get_entity(entity_id)
        entities_extracted.append(_serialize_entity(stored_entity, entity))

    for relation in extraction.get("relations", []):
        relation_id = service.add_relation(
            relation.get("source", ""),
            relation.get("target", ""),
            relation.get("relation", "related_to"),
            relation.get("evidence", ""),
        )
        stored_relation = next(
            (item for item in service.list_relations() if item.get("id") == relation_id),
            None,
        )
        relations_extracted.append(_serialize_relation(stored_relation, relation))

    for fact in extraction.get("facts", []):
        memory = service.create_memory(
            user_id=request.user_id,
            content=fact.get("content", ""),
            memory_type=_coerce_fact_type(fact.get("type")),
            importance=float(fact.get("confidence", 0.5) or 0.5),
            metadata={
                "source": "memory.process",
                "session_id": session_id,
                "extraction_method": extraction.get("extraction_method", "rule"),
            },
        )
        facts_extracted.append(_serialize_fact(memory, fact))

    return {
        "result": {
            "message_stored": bool(stored),
            "entities_extracted": entities_extracted,
            "relations_extracted": relations_extracted,
            "facts_extracted": facts_extracted,
            "active_entities": service.get_active_entities(session_id),
            "context": service.get_context(request.user_id, request.message, session_id),
        }
    }


@router.get("/sessions")
async def list_sessions():
    service = get_memory_api_service()
    return {"sessions": service.list_sessions()}


@router.get("/sessions/{session_id}")
async def get_session_context(session_id: str, max_tokens: int = 4000):
    service = get_memory_api_service()
    return service.get_session_context(session_id, max_tokens)


@router.post("/sessions/{session_id}/messages")
async def add_session_message(session_id: str, request: SessionMessageRequest):
    service = get_memory_api_service()
    success = service.add_session_message(session_id, request.role, request.content, request.entities)
    return {"success": success}


@router.delete("/sessions/{session_id}")
async def clear_session(session_id: str):
    service = get_memory_api_service()
    return {"success": service.clear_session(session_id)}


@router.get("/sessions/{session_id}/active-entities")
async def get_active_entities(session_id: str, threshold: float = 0.3):
    service = get_memory_api_service()
    return {"entities": service.get_active_entities(session_id, threshold)}


@router.post("/graph/entities")
async def add_graph_entity(request: GraphEntityRequest):
    service = get_memory_api_service()
    entity_id, is_new = service.add_entity(
        request.name,
        request.entity_type,
        request.attributes,
        request.confidence,
    )
    return {"entity_id": entity_id, "is_new": is_new}


@router.post("/graph/relations")
async def add_graph_relation(request: GraphRelationRequest):
    service = get_memory_api_service()
    relation_id = service.add_relation(
        request.source_name,
        request.target_name,
        request.relation_type,
        request.evidence,
    )
    return {"relation_id": relation_id}


@router.get("/graph/entities/{entity_id}")
async def get_graph_entity(entity_id: str):
    service = get_memory_api_service()
    entity = service.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"entity": entity}


@router.post("/graph/context")
async def get_graph_context(request: GraphContextRequest):
    service = get_memory_api_service()
    return {"context": service.get_entity_context(request.entity_id, request.depth)}


@router.post("/graph/path")
async def find_graph_path(request: GraphPathRequest):
    service = get_memory_api_service()
    return {"paths": service.find_path(request.source_id, request.target_id, request.max_depth)}


@router.post("/graph/search")
async def search_graph(request: GraphSearchRequest):
    service = get_memory_api_service()
    return {"results": service.search_graph(request.query, request.entity_types, request.limit)}


@router.get("/graph/stats")
async def get_graph_stats():
    service = get_memory_api_service()
    return {"stats": service.get_graph_stats()}


@router.delete("/graph/entities/{entity_id}")
async def delete_graph_entity(entity_id: str):
    service = get_memory_api_service()
    return {"success": service.delete_entity(entity_id)}


@router.get("/graph/relations")
async def list_graph_relations():
    service = get_memory_api_service()
    return {"relations": service.list_relations()}


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
    }


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str, user_id: str = "default"):
    service = get_memory_api_service()
    success = service.delete_memory(memory_id, user_id=user_id)

    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")

    return {"success": True, "memory_id": memory_id}
