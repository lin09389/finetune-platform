"""
增强版记忆管理 API
支持三级记忆架构、知识图谱、MCP协议
"""
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import logging
import asyncio

from memory.memory_service import get_memory_service
from memory.enhanced_memory_service import get_enhanced_memory_service
from memory.knowledge_graph import get_knowledge_graph
from memory.short_term_memory import get_short_term_memory, get_stm_manager
from memory.intelligent_extractor import extract_memories
from memory.mcp_server import get_mcp_server, MCPResourceType

logger = logging.getLogger(__name__)

router = APIRouter()


class ProcessMessageRequest(BaseModel):
    """处理消息请求"""
    message: str = Field(..., description="消息内容")
    role: str = Field(default="user", description="角色")
    user_id: str = Field(default="default", description="用户ID")
    session_id: Optional[str] = Field(None, description="会话ID")
    extract_memories: bool = Field(default=True, description="是否提取记忆")


class RecallRequest(BaseModel):
    """回忆请求"""
    query: str = Field(..., description="查询文本")
    user_id: str = Field(default="default", description="用户ID")
    top_k: int = Field(default=5, description="返回数量")
    memory_type: Optional[str] = Field(default=None, description="记忆类型")


class AddEntityRequest(BaseModel):
    """添加实体请求"""
    name: str = Field(..., description="实体名称")
    entity_type: str = Field(..., description="实体类型")
    attributes: Dict[str, Any] = Field(default={}, description="属性")
    confidence: float = Field(default=0.5, description="置信度")


class AddRelationRequest(BaseModel):
    """添加关系请求"""
    source_name: str = Field(..., description="源实体名称")
    target_name: str = Field(..., description="目标实体名称")
    relation_type: str = Field(..., description="关系类型")
    evidence: str = Field(default="", description="证据")


class GetEntityContextRequest(BaseModel):
    """获取实体上下文请求"""
    entity_id: str = Field(..., description="实体ID")
    depth: int = Field(default=2, description="遍历深度")


class FindPathRequest(BaseModel):
    """查找路径请求"""
    source_id: str = Field(..., description="源实体ID")
    target_id: str = Field(..., description="目标实体ID")
    max_depth: int = Field(default=4, description="最大深度")


class SearchKnowledgeGraphRequest(BaseModel):
    """搜索知识图谱请求"""
    query: str = Field(..., description="搜索查询")
    entity_types: Optional[List[str]] = Field(None, description="实体类型过滤")
    limit: int = Field(default=10, description="返回数量")


class SessionMessageRequest(BaseModel):
    """会话消息请求"""
    session_id: str = Field(..., description="会话ID")
    role: str = Field(..., description="角色")
    content: str = Field(..., description="内容")
    entities: Optional[List[str]] = Field(None, description="相关实体")


class ExtractRequest(BaseModel):
    """提取请求"""
    message: str = Field(..., description="消息内容")
    role: str = Field(default="user", description="角色")


@router.post("/process")
async def process_message(request: ProcessMessageRequest):
    """
    处理消息 - 完整的记忆处理流程

    包括：
    - 短期记忆存储
    - 智能记忆提取
    - 知识图谱更新
    """
    try:
        service = get_enhanced_memory_service()
        result = service.process_message(
            message=request.message,
            role=request.role,
            user_id=request.user_id,
            session_id=request.session_id,
            extract_memories=request.extract_memories
        )

        logger.info(f"处理消息: 提取 {len(result['entities_extracted'])} 实体, "
                   f"{len(result['relations_extracted'])} 关系")

        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        logger.error(f"处理消息失败: {e}")
        raise HTTPException(500, f"处理失败: {str(e)}")


@router.post("/extract")
async def extract_memory(request: ExtractRequest):
    """
    智能提取记忆

    使用规则+LLM混合提取
    """
    try:
        result = extract_memories(request.message, request.role)

        return {
            "success": True,
            "extraction": result.to_dict()
        }
    except Exception as e:
        logger.error(f"提取记忆失败: {e}")
        raise HTTPException(500, f"提取失败: {str(e)}")


@router.post("/recall")
async def recall_memory(request: RecallRequest):
    """检索相关记忆"""
    try:
        service = get_memory_service()
        memories = service.recall(
            query=request.query,
            user_id=request.user_id,
            top_k=request.top_k,
            memory_type=request.memory_type
        )

        return {
            "success": True,
            "memories": memories,
            "count": len(memories)
        }
    except Exception as e:
        logger.error(f"检索记忆失败: {e}")
        raise HTTPException(500, f"检索失败: {str(e)}")


@router.get("/list")
async def list_memories(
    user_id: str = Query(default="default"),
    memory_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50)
):
    """列出所有记忆"""
    try:
        service = get_memory_service()
        memories = service.list_memories(
            user_id=user_id,
            memory_type=memory_type,
            limit=limit
        )

        return {
            "success": True,
            "count": len(memories),
            "memories": memories
        }
    except Exception as e:
        logger.error(f"列出记忆失败: {e}")
        raise HTTPException(500, f"获取失败: {str(e)}")


@router.delete("/{memory_id}")
async def forget_memory(
    memory_id: str,
    user_id: str = Query(default="default")
):
    """删除记忆"""
    try:
        service = get_memory_service()
        success = service.forget(user_id, memory_id)

        if success:
            return {"success": True, "message": "记忆已删除"}
        else:
            raise HTTPException(404, "记忆不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除记忆失败: {e}")
        raise HTTPException(500, f"删除失败: {str(e)}")


@router.delete("/clear/all")
async def clear_all_memories(user_id: str = Query(default="default")):
    """清除所有记忆"""
    try:
        service = get_memory_service()
        success = service.clear_all(user_id)

        if success:
            return {"success": True, "message": "所有记忆已清除"}
        else:
            raise HTTPException(500, "清除失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"清除记忆失败: {e}")
        raise HTTPException(500, f"清除失败: {str(e)}")


@router.get("/summary")
async def get_summary(user_id: str = Query(default="default")):
    """获取用户记忆摘要"""
    try:
        service = get_enhanced_memory_service()
        summary = service.get_user_summary(user_id)

        return {
            "success": True,
            "summary": summary
        }
    except Exception as e:
        logger.error(f"获取摘要失败: {e}")
        raise HTTPException(500, f"获取摘要失败: {str(e)}")


@router.get("/context")
async def get_context(
    query: str = Query(..., description="查询文本"),
    user_id: str = Query(default="default"),
    session_id: Optional[str] = Query(None, description="会话ID"),
    max_memories: int = Query(default=5)
):
    """获取带记忆的上下文"""
    try:
        service = get_enhanced_memory_service()
        context = service._build_enhanced_context(query, user_id, session_id)

        return {
            "success": True,
            "context": context
        }
    except Exception as e:
        logger.error(f"获取上下文失败: {e}")
        raise HTTPException(500, f"获取上下文失败: {str(e)}")


@router.get("/stats")
async def get_stats(user_id: str = Query(default="default")):
    """获取记忆统计信息"""
    try:
        service = get_enhanced_memory_service()
        stats = service.get_stats(user_id)

        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        raise HTTPException(500, f"获取统计失败: {str(e)}")


@router.post("/export")
async def export_state(user_id: str = Query(default="default")):
    """导出记忆状态"""
    try:
        service = get_enhanced_memory_service()
        state = service.export_state(user_id)

        return {
            "success": True,
            "state": state
        }
    except Exception as e:
        logger.error(f"导出状态失败: {e}")
        raise HTTPException(500, f"导出失败: {str(e)}")


@router.post("/import")
async def import_state(
    state: Dict[str, Any] = Body(..., description="状态数据"),
    user_id: str = Query(default="default")
):
    """导入记忆状态"""
    try:
        service = get_enhanced_memory_service()
        service.import_state(state, user_id)

        return {
            "success": True,
            "message": "状态导入成功"
        }
    except Exception as e:
        logger.error(f"导入状态失败: {e}")
        raise HTTPException(500, f"导入失败: {str(e)}")


@router.post("/graph/entities")
async def add_entity(request: AddEntityRequest):
    """添加实体到知识图谱"""
    try:
        kg = get_knowledge_graph()
        entity_id, is_new = kg.add_entity(
            name=request.name,
            entity_type=request.entity_type,
            attributes=request.attributes,
            confidence=request.confidence
        )

        return {
            "success": True,
            "entity_id": entity_id,
            "is_new": is_new,
            "message": "实体已创建" if is_new else "实体已合并"
        }
    except Exception as e:
        logger.error(f"添加实体失败: {e}")
        raise HTTPException(500, f"添加失败: {str(e)}")


@router.post("/graph/relations")
async def add_relation(request: AddRelationRequest):
    """添加关系到知识图谱"""
    try:
        kg = get_knowledge_graph()
        relation_id = kg.add_relation(
            source_name=request.source_name,
            target_name=request.target_name,
            relation_type=request.relation_type,
            evidence=request.evidence
        )

        if relation_id:
            return {
                "success": True,
                "relation_id": relation_id
            }
        else:
            raise HTTPException(400, "无法创建关系，实体不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加关系失败: {e}")
        raise HTTPException(500, f"添加失败: {str(e)}")


@router.get("/graph/entities/{entity_id}")
async def get_entity(entity_id: str):
    """获取实体详情"""
    try:
        kg = get_knowledge_graph()
        entity = kg.get_entity(entity_id)

        if entity:
            return {
                "success": True,
                "entity": entity.to_dict()
            }
        else:
            raise HTTPException(404, "实体不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取实体失败: {e}")
        raise HTTPException(500, f"获取失败: {str(e)}")


@router.post("/graph/context")
async def get_entity_context(request: GetEntityContextRequest):
    """获取实体上下文（多跳关系）"""
    try:
        kg = get_knowledge_graph()
        context = kg.get_entity_context(request.entity_id, request.depth)

        return {
            "success": True,
            "context": context
        }
    except Exception as e:
        logger.error(f"获取上下文失败: {e}")
        raise HTTPException(500, f"获取失败: {str(e)}")


@router.post("/graph/path")
async def find_path(request: FindPathRequest):
    """查找两个实体之间的路径"""
    try:
        kg = get_knowledge_graph()
        paths = kg.find_path(
            request.source_id,
            request.target_id,
            request.max_depth
        )

        return {
            "success": True,
            "paths": paths,
            "count": len(paths)
        }
    except Exception as e:
        logger.error(f"查找路径失败: {e}")
        raise HTTPException(500, f"查找失败: {str(e)}")


@router.post("/graph/search")
async def search_knowledge_graph(request: SearchKnowledgeGraphRequest):
    """搜索知识图谱"""
    try:
        kg = get_knowledge_graph()
        results = []

        for entity in kg.get_all_entities():
            if request.query.lower() in entity.name.lower():
                if request.entity_types and entity.entity_type not in request.entity_types:
                    continue
                results.append(entity.to_dict())

                if len(results) >= request.limit:
                    break

        return {
            "success": True,
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        logger.error(f"搜索图谱失败: {e}")
        raise HTTPException(500, f"搜索失败: {str(e)}")


@router.get("/graph/stats")
async def get_graph_stats():
    """获取知识图谱统计"""
    try:
        kg = get_knowledge_graph()
        stats = kg.get_stats()

        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        raise HTTPException(500, f"获取失败: {str(e)}")


@router.delete("/graph/entities/{entity_id}")
async def delete_entity(entity_id: str):
    """删除实体"""
    try:
        kg = get_knowledge_graph()
        success = kg.delete_entity(entity_id)

        if success:
            return {"success": True, "message": "实体已删除"}
        else:
            raise HTTPException(404, "实体不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除实体失败: {e}")
        raise HTTPException(500, f"删除失败: {str(e)}")


@router.get("/graph/relations")
async def list_relations():
    """列出所有关系"""
    try:
        kg = get_knowledge_graph()
        relations = kg.get_all_relations()

        return {
            "success": True,
            "relations": [r.to_dict() for r in relations],
            "count": len(relations)
        }
    except Exception as e:
        logger.error(f"列出关系失败: {e}")
        raise HTTPException(500, f"获取失败: {str(e)}")


@router.get("/sessions")
async def list_sessions():
    """列出所有会话"""
    try:
        manager = get_stm_manager()
        sessions = manager.get_all_sessions()

        return {
            "success": True,
            "sessions": sessions,
            "count": len(sessions)
        }
    except Exception as e:
        logger.error(f"列出会话失败: {e}")
        raise HTTPException(500, f"获取失败: {str(e)}")


@router.get("/sessions/{session_id}")
async def get_session_context(
    session_id: str,
    max_tokens: int = Query(default=4000)
):
    """获取会话上下文"""
    try:
        stm = get_short_term_memory(session_id)
        context = stm.get_context(max_tokens)
        summary = stm.summarize()

        return {
            "success": True,
            "context": context,
            "summary": summary
        }
    except Exception as e:
        logger.error(f"获取会话上下文失败: {e}")
        raise HTTPException(500, f"获取失败: {str(e)}")


@router.post("/sessions/{session_id}/messages")
async def add_session_message(
    session_id: str,
    request: SessionMessageRequest
):
    """添加会话消息"""
    try:
        stm = get_short_term_memory(session_id)
        message = stm.add_message(
            role=request.role,
            content=request.content,
            entities=request.entities
        )

        return {
            "success": True,
            "message": message.to_dict()
        }
    except Exception as e:
        logger.error(f"添加消息失败: {e}")
        raise HTTPException(500, f"添加失败: {str(e)}")


@router.delete("/sessions/{session_id}")
async def clear_session(session_id: str):
    """清空会话"""
    try:
        manager = get_stm_manager()
        manager.clear_session(session_id)

        return {"success": True, "message": "会话已清空"}
    except Exception as e:
        logger.error(f"清空会话失败: {e}")
        raise HTTPException(500, f"清空失败: {str(e)}")


@router.get("/sessions/{session_id}/active-entities")
async def get_active_entities(
    session_id: str,
    threshold: float = Query(default=0.3)
):
    """获取会话活跃实体"""
    try:
        stm = get_short_term_memory(session_id)
        entities = stm.get_active_entities(threshold)

        return {
            "success": True,
            "entities": entities,
            "count": len(entities)
        }
    except Exception as e:
        logger.error(f"获取活跃实体失败: {e}")
        raise HTTPException(500, f"获取失败: {str(e)}")


from memory.mcp_server import router as mcp_router
router.include_router(mcp_router, prefix="/mcp", tags=["MCP"])
