"""
记忆模块路由 - 统一记忆管理接口
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import logging

from api.types import MemoryInfo, MemoryRecallRequest, MemoryStoreRequest
from api.errors import MemoryNotFoundError, InvalidInputError
from api.memory_new.service import get_memory_service

logger = logging.getLogger(__name__)

router = APIRouter()


class ExtractRequest(BaseModel):
    """提取请求"""
    message: str = Field(..., description="消息内容")
    role: str = Field(default="user", description="角色")
    user_id: str = Field(default="default", description="用户 ID")


class ExtractResponse(BaseModel):
    """提取响应"""
    success: bool
    extracted: int
    memories: List[Dict[str, Any]]


class RecallResponse(BaseModel):
    """回忆响应"""
    success: bool
    memories: List[MemoryInfo]
    count: int


class MemoryListResponse(BaseModel):
    """记忆列表响应"""
    success: bool
    count: int
    memories: List[MemoryInfo]


class EntityInfo(BaseModel):
    """实体信息"""
    id: str
    name: str
    entity_type: str
    observations: List[str]
    created_at: str


class RelationInfo(BaseModel):
    """关系信息"""
    from_entity: str
    relation_type: str
    to_entity: str
    confidence: float


class GraphResponse(BaseModel):
    """知识图谱响应"""
    entities: List[EntityInfo]
    relations: List[RelationInfo]
    total_entities: int
    total_relations: int


class ShortTermMemoryResponse(BaseModel):
    """短期记忆响应"""
    session_id: str
    messages: List[Dict[str, Any]]
    entity_mentions: Dict[str, float]
    summary: Optional[str]


@router.post("/extract", response_model=ExtractResponse)
async def extract_memory(request: ExtractRequest):
    """
    从消息中提取记忆
    
    自动识别用户消息中的重要信息并存�?    """
    try:
        service = get_memory_service()
        memories = service.extract_and_store(
            message=request.message,
            role=request.role,
            user_id=request.user_id
        )
        
        logger.info(f"提取记忆: {len(memories)} �?)
        
        return ExtractResponse(
            success=True,
            extracted=len(memories),
            memories=memories
        )
    except Exception as e:
        logger.error(f"提取记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"提取失败: {str(e)}")


@router.post("/recall", response_model=RecallResponse)
async def recall_memory(request: MemoryRecallRequest):
    """
    检索相关记�?    
    根据查询文本返回相关的记�?    """
    try:
        service = get_memory_service()
        memories = service.recall(
            query=request.query,
            user_id=request.user_id,
            top_k=request.top_k,
            memory_type=request.memory_type
        )
        
        memory_infos = [
            MemoryInfo(
                id=m.get("id", ""),
                type=m.get("type", "fact"),
                content=m.get("content", ""),
                confidence=m.get("confidence", 1.0),
                metadata=m.get("metadata", {})
            )
            for m in memories
        ]
        
        return RecallResponse(
            success=True,
            memories=memory_infos,
            count=len(memory_infos)
        )
    except Exception as e:
        logger.error(f"检索记忆失�? {e}")
        raise HTTPException(status_code=500, detail=f"检索失�? {str(e)}")


@router.post("/store", response_model=MemoryInfo)
async def store_memory(request: MemoryStoreRequest):
    """
    直接存储记忆
    
    手动添加一条记�?    """
    try:
        service = get_memory_service()
        memory = service.store(
            content=request.content,
            memory_type=request.memory_type,
            user_id=request.user_id,
            confidence=request.confidence,
            metadata=request.metadata
        )
        
        return MemoryInfo(
            id=memory.get("id", ""),
            type=memory.get("type", request.memory_type),
            content=memory.get("content", request.content),
            confidence=memory.get("confidence", request.confidence),
            metadata=memory.get("metadata", request.metadata)
        )
    except Exception as e:
        logger.error(f"存储记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"存储失败: {str(e)}")


@router.get("/list", response_model=MemoryListResponse)
async def list_memories(
    user_id: str = Query(default="default"),
    memory_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50)
):
    """
    列出所有记�?    
    支持按类型过�?    """
    try:
        service = get_memory_service()
        memories = service.list_memories(
            user_id=user_id,
            memory_type=memory_type,
            limit=limit
        )
        
        memory_infos = [
            MemoryInfo(
                id=m.get("id", ""),
                type=m.get("type", "fact"),
                content=m.get("content", ""),
                confidence=m.get("confidence", 1.0),
                metadata=m.get("metadata", {})
            )
            for m in memories
        ]
        
        return MemoryListResponse(
            success=True,
            count=len(memory_infos),
            memories=memory_infos
        )
    except Exception as e:
        logger.error(f"列出记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.delete("/{memory_id}")
async def forget_memory(
    memory_id: str,
    user_id: str = Query(default="default")
):
    """
    删除记忆
    
    用户主动遗忘某条记忆
    """
    try:
        service = get_memory_service()
        success = service.forget(user_id, memory_id)
        
        if success:
            return {"success": True, "message": "记忆已删�?}
        else:
            raise MemoryNotFoundError(memory_id)
    except MemoryNotFoundError:
        raise
    except Exception as e:
        logger.error(f"删除记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.delete("/clear")
async def clear_memories(
    user_id: str = Query(default="default"),
    memory_type: Optional[str] = Query(default=None)
):
    """
    清空记忆
    
    清空指定用户的所有记忆或特定类型的记�?    """
    try:
        service = get_memory_service()
        count = service.clear_memories(user_id, memory_type)
        
        return {
            "success": True,
            "message": f"已清�?{count} 条记�?,
            "count": count
        }
    except Exception as e:
        logger.error(f"清空记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"清空失败: {str(e)}")


@router.get("/stats")
async def get_memory_stats(user_id: str = Query(default="default")):
    """
    获取记忆统计信息
    
    包括记忆数量、类型分布等
    """
    try:
        service = get_memory_service()
        stats = service.get_stats(user_id)
        return stats
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.get("/graph", response_model=GraphResponse)
async def get_knowledge_graph(
    user_id: str = Query(default="default"),
    entity_type: Optional[str] = Query(default=None)
):
    """
    获取知识图谱
    
    返回用户的所有实体和关系
    """
    try:
        service = get_memory_service()
        
        if hasattr(service, 'get_knowledge_graph'):
            graph = service.get_knowledge_graph(user_id, entity_type)
            
            entities = [
                EntityInfo(
                    id=e.get("id", ""),
                    name=e.get("name", ""),
                    entity_type=e.get("entity_type", ""),
                    observations=e.get("observations", []),
                    created_at=e.get("created_at", "")
                )
                for e in graph.get("entities", [])
            ]
            
            relations = [
                RelationInfo(
                    from_entity=r.get("from", ""),
                    relation_type=r.get("relation_type", ""),
                    to_entity=r.get("to", ""),
                    confidence=r.get("confidence", 1.0)
                )
                for r in graph.get("relations", [])
            ]
            
            return GraphResponse(
                entities=entities,
                relations=relations,
                total_entities=len(entities),
                total_relations=len(relations)
            )
        else:
            return GraphResponse(
                entities=[],
                relations=[],
                total_entities=0,
                total_relations=0
            )
    except Exception as e:
        logger.error(f"获取知识图谱失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.get("/graph/stats")
async def get_graph_stats(user_id: str = Query(default="default")):
    """
    获取知识图谱统计信息
    
    返回实体和关系的数量统计
    """
    try:
        service = get_memory_service()
        
        if hasattr(service, 'get_knowledge_graph'):
            graph = service.get_knowledge_graph(user_id)
            entities = graph.get("entities", [])
            relations = graph.get("relations", [])
            
            entity_types: Dict[str, int] = {}
            for e in entities:
                et = e.get("entity_type", "unknown")
                entity_types[et] = entity_types.get(et, 0) + 1
            
            relation_types: Dict[str, int] = {}
            for r in relations:
                rt = r.get("relation_type", "unknown")
                relation_types[rt] = relation_types.get(rt, 0) + 1
            
            return {
                "stats": {
                    "total_entities": len(entities),
                    "total_relations": len(relations),
                    "entity_types": entity_types,
                    "relation_types": relation_types
                }
            }
        else:
            return {
                "stats": {
                    "total_entities": 0,
                    "total_relations": 0,
                    "entity_types": {},
                    "relation_types": {}
                }
            }
    except Exception as e:
        logger.error(f"获取图谱统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.get("/graph/relations")
async def get_graph_relations(user_id: str = Query(default="default")):
    """
    获取知识图谱所有关�?    
    返回所有关系列�?    """
    try:
        service = get_memory_service()
        
        if hasattr(service, 'get_knowledge_graph'):
            graph = service.get_knowledge_graph(user_id)
            relations = graph.get("relations", [])
            
            return {"relations": relations}
        else:
            return {"relations": []}
    except Exception as e:
        logger.error(f"获取图谱关系失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.get("/short-term/{session_id}", response_model=ShortTermMemoryResponse)
async def get_short_term_memory(session_id: str):
    """
    获取短期记忆
    
    返回会话的短期记忆状�?    """
    try:
        service = get_memory_service()
        
        if hasattr(service, 'get_short_term_memory'):
            stm = service.get_short_term_memory(session_id)
            
            return ShortTermMemoryResponse(
                session_id=session_id,
                messages=stm.get("messages", []),
                entity_mentions=stm.get("entity_mentions", {}),
                summary=stm.get("summary")
            )
        else:
            return ShortTermMemoryResponse(
                session_id=session_id,
                messages=[],
                entity_mentions={},
                summary=None
            )
    except Exception as e:
        logger.error(f"获取短期记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.delete("/short-term/{session_id}")
async def clear_short_term_memory(session_id: str):
    """
    清空短期记忆
    
    清空指定会话的短期记�?    """
    try:
        service = get_memory_service()
        
        if hasattr(service, 'clear_short_term_memory'):
            service.clear_short_term_memory(session_id)
        
        return {"success": True, "message": "短期记忆已清�?}
    except Exception as e:
        logger.error(f"清空短期记忆失败: {e}")
        raise HTTPException(status_code=500, detail=f"清空失败: {str(e)}")
