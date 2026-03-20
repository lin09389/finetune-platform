"""
MCP (Model Context Protocol) 服务�?支持跨工具记忆共�?参�?supermemory �?MCP 实现
"""
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
import asyncio
from enum import Enum

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MCPResourceType(str, Enum):
    """MCP 资源类型"""
    ENTITY = "entity"
    MEMORY = "memory"
    CONTEXT = "context"
    GRAPH = "graph"


@dataclass
class MCPResource:
    """MCP 资源定义"""
    uri: str
    name: str
    description: str
    mime_type: str = "application/json"
    resource_type: MCPResourceType = MCPResourceType.MEMORY
    
    def to_dict(self) -> Dict:
        return {
            'uri': self.uri,
            'name': self.name,
            'description': self.description,
            'mimeType': self.mime_type,
            'type': self.resource_type.value
        }


@dataclass
class MCPResourceContent:
    """MCP 资源内容"""
    uri: str
    mime_type: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            'uri': self.uri,
            'mimeType': self.mime_type,
            'text': self.text,
            'metadata': self.metadata
        }


@dataclass
class MCPSearchResult:
    """MCP 搜索结果"""
    uri: str
    name: str
    description: str
    score: float
    content_preview: str
    
    def to_dict(self) -> Dict:
        return {
            'uri': self.uri,
            'name': self.name,
            'description': self.description,
            'score': self.score,
            'contentPreview': self.content_preview
        }


class MCPServer:
    """MCP 协议服务�?""
    
    def __init__(self, memory_service=None, knowledge_graph=None):
        self.memory_service = memory_service
        self.knowledge_graph = knowledge_graph
        self.resources: Dict[str, MCPResource] = {}
        self.handlers: Dict[str, Callable] = {}
        
        self._register_default_handlers()
        logger.info("MCP 服务器初始化完成")
    
    def _register_default_handlers(self):
        """注册默认处理�?""
        self.handlers['list_resources'] = self._handle_list_resources
        self.handlers['read_resource'] = self._handle_read_resource
        self.handlers['search'] = self._handle_search
        self.handlers['query_graph'] = self._handle_query_graph
    
    async def list_resources(
        self,
        resource_type: MCPResourceType = None,
        limit: int = 50
    ) -> List[MCPResource]:
        """列出所有可用资�?""
        resources = []
        
        if self.knowledge_graph:
            for entity in self.knowledge_graph.get_all_entities()[:limit]:
                if resource_type and resource_type != MCPResourceType.ENTITY:
                    continue
                
                resources.append(MCPResource(
                    uri=f"memory://entities/{entity.id}",
                    name=entity.name,
                    description=f"实体: {entity.entity_type}",
                    mime_type="application/json",
                    resource_type=MCPResourceType.ENTITY
                ))
        
        if self.memory_service and (not resource_type or resource_type == MCPResourceType.MEMORY):
            memories = self.memory_service.list_memories(limit=limit)
            for mem in memories:
                resources.append(MCPResource(
                    uri=f"memory://memories/{mem.get('id', '')}",
                    name=mem.get('content', '')[:50],
                    description=f"记忆: {mem.get('type', 'unknown')}",
                    mime_type="application/json",
                    resource_type=MCPResourceType.MEMORY
                ))
        
        return resources
    
    async def read_resource(self, uri: str) -> MCPResourceContent:
        """读取资源内容"""
        if uri.startswith("memory://entities/"):
            return await self._read_entity_resource(uri)
        elif uri.startswith("memory://memories/"):
            return await self._read_memory_resource(uri)
        elif uri.startswith("memory://context/"):
            return await self._read_context_resource(uri)
        elif uri.startswith("memory://graph/"):
            return await self._read_graph_resource(uri)
        else:
            raise HTTPException(404, f"Resource not found: {uri}")
    
    async def search(
        self,
        query: str,
        resource_types: List[MCPResourceType] = None,
        limit: int = 10
    ) -> List[MCPSearchResult]:
        """搜索资源"""
        results = []
        
        if self.knowledge_graph and (not resource_types or MCPResourceType.ENTITY in resource_types):
            for entity in self.knowledge_graph.get_all_entities():
                if query.lower() in entity.name.lower():
                    results.append(MCPSearchResult(
                        uri=f"memory://entities/{entity.id}",
                        name=entity.name,
                        description=f"实体: {entity.entity_type}",
                        score=0.9,
                        content_preview=entity.name
                    ))
        
        if self.memory_service and (not resource_types or MCPResourceType.MEMORY in resource_types):
            memories = self.memory_service.recall(query, top_k=limit)
            for mem in memories:
                results.append(MCPSearchResult(
                    uri=f"memory://memories/{mem.get('id', '')}",
                    name=mem.get('content', '')[:50],
                    description=f"记忆: {mem.get('type', 'unknown')}",
                    score=mem.get('relevance', 0.5),
                    content_preview=mem.get('content', '')[:100]
                ))
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]
    
    async def query_graph(
        self,
        entity_id: str,
        depth: int = 2,
        relation_types: List[str] = None
    ) -> Dict[str, Any]:
        """查询知识图谱"""
        if not self.knowledge_graph:
            return {'error': 'Knowledge graph not available'}
        
        context = self.knowledge_graph.get_entity_context(entity_id, depth)
        
        if relation_types:
            context['relations'] = [
                r for r in context.get('relations', [])
                if r.get('relation_type') in relation_types
            ]
        
        return context
    
    async def add_memory(
        self,
        content: str,
        memory_type: str = "knowledge",
        entities: List[str] = None,
        user_id: str = "default"
    ) -> Dict[str, Any]:
        """添加记忆"""
        if not self.memory_service:
            return {'error': 'Memory service not available'}
        
        result = self.memory_service.process_message(
            message=content,
            role='user',
            user_id=user_id,
            extract_memories=True
        )
        
        return {
            'success': True,
            'memory_id': result.get('facts_extracted', [{}])[0].get('id') if result.get('facts_extracted') else None,
            'entities_created': len(result.get('entities_extracted', [])),
            'relations_created': len(result.get('relations_extracted', []))
        }
    
    async def _read_entity_resource(self, uri: str) -> MCPResourceContent:
        """读取实体资源"""
        entity_id = uri.split("/")[-1]
        
        if not self.knowledge_graph:
            raise HTTPException(503, "Knowledge graph not available")
        
        entity = self.knowledge_graph.get_entity(entity_id)
        if not entity:
            raise HTTPException(404, f"Entity not found: {entity_id}")
        
        context = self.knowledge_graph.get_entity_context(entity_id)
        
        return MCPResourceContent(
            uri=uri,
            mime_type="application/json",
            text=json.dumps({
                'entity': entity.to_dict(),
                'context': context
            }, ensure_ascii=False, indent=2),
            metadata={
                'entity_type': entity.entity_type,
                'confidence': entity.confidence
            }
        )
    
    async def _read_memory_resource(self, uri: str) -> MCPResourceContent:
        """读取记忆资源"""
        memory_id = uri.split("/")[-1]
        
        if not self.memory_service:
            raise HTTPException(503, "Memory service not available")
        
        memories = self.memory_service.list_memories()
        memory = next((m for m in memories if m.get('id') == memory_id), None)
        
        if not memory:
            raise HTTPException(404, f"Memory not found: {memory_id}")
        
        return MCPResourceContent(
            uri=uri,
            mime_type="application/json",
            text=json.dumps(memory, ensure_ascii=False, indent=2),
            metadata={
                'type': memory.get('type'),
                'importance': memory.get('importance')
            }
        )
    
    async def _read_context_resource(self, uri: str) -> MCPResourceContent:
        """读取上下文资�?""
        query = uri.split("/")[-1]
        
        if not self.memory_service:
            raise HTTPException(503, "Memory service not available")
        
        context = self.memory_service.get_context_with_memory(query)
        
        return MCPResourceContent(
            uri=uri,
            mime_type="text/plain",
            text=context,
            metadata={
                'query': query
            }
        )
    
    async def _read_graph_resource(self, uri: str) -> MCPResourceContent:
        """读取图谱资源"""
        if not self.knowledge_graph:
            raise HTTPException(503, "Knowledge graph not available")
        
        stats = self.knowledge_graph.get_stats()
        
        return MCPResourceContent(
            uri=uri,
            mime_type="application/json",
            text=json.dumps(stats, ensure_ascii=False, indent=2),
            metadata={
                'total_entities': stats.get('total_entities', 0),
                'total_relations': stats.get('total_relations', 0)
            }
        )
    
    async def _handle_list_resources(self, params: Dict) -> List[Dict]:
        """处理列出资源请求"""
        resource_type = params.get('type')
        if resource_type:
            resource_type = MCPResourceType(resource_type)
        
        resources = await self.list_resources(resource_type)
        return [r.to_dict() for r in resources]
    
    async def _handle_read_resource(self, params: Dict) -> Dict:
        """处理读取资源请求"""
        uri = params.get('uri')
        if not uri:
            raise ValueError("URI is required")
        
        content = await self.read_resource(uri)
        return content.to_dict()
    
    async def _handle_search(self, params: Dict) -> List[Dict]:
        """处理搜索请求"""
        query = params.get('query')
        if not query:
            raise ValueError("Query is required")
        
        resource_types = params.get('types')
        if resource_types:
            resource_types = [MCPResourceType(t) for t in resource_types]
        
        results = await self.search(query, resource_types)
        return [r.to_dict() for r in results]
    
    async def _handle_query_graph(self, params: Dict) -> Dict:
        """处理图谱查询请求"""
        entity_id = params.get('entity_id')
        if not entity_id:
            raise ValueError("Entity ID is required")
        
        return await self.query_graph(
            entity_id,
            depth=params.get('depth', 2),
            relation_types=params.get('relation_types')
        )


router = APIRouter(prefix="/mcp", tags=["MCP"])

_mcp_server: Optional[MCPServer] = None


def get_mcp_server() -> MCPServer:
    """获取 MCP 服务器实�?""
    global _mcp_server
    if _mcp_server is None:
        try:
            from .enhanced_memory_service import get_enhanced_memory_service
            from .knowledge_graph import get_knowledge_graph
            
            memory_service = get_enhanced_memory_service()
            kg = get_knowledge_graph()
            _mcp_server = MCPServer(memory_service, kg)
        except Exception as e:
            logger.warning(f"初始�?MCP 服务器失�? {e}")
            _mcp_server = MCPServer()
    
    return _mcp_server


class ListResourcesRequest(BaseModel):
    """列出资源请求"""
    type: Optional[str] = Field(None, description="资源类型过滤")
    limit: int = Field(default=50, description="返回数量限制")


class ReadResourceRequest(BaseModel):
    """读取资源请求"""
    uri: str = Field(..., description="资源 URI")


class SearchRequest(BaseModel):
    """搜索请求"""
    query: str = Field(..., description="搜索查询")
    types: Optional[List[str]] = Field(None, description="资源类型过滤")
    limit: int = Field(default=10, description="返回数量限制")


class QueryGraphRequest(BaseModel):
    """图谱查询请求"""
    entity_id: str = Field(..., description="实体 ID")
    depth: int = Field(default=2, description="查询深度")
    relation_types: Optional[List[str]] = Field(None, description="关系类型过滤")


class AddMemoryRequest(BaseModel):
    """添加记忆请求"""
    content: str = Field(..., description="记忆内容")
    memory_type: str = Field(default="knowledge", description="记忆类型")
    entities: Optional[List[str]] = Field(None, description="关联实体")
    user_id: str = Field(default="default", description="用户 ID")


@router.get("/resources")
async def mcp_list_resources(
    type: Optional[str] = Query(None, description="资源类型"),
    limit: int = Query(default=50, description="返回数量")
):
    """
    MCP: 列出所有可用资�?    
    支持的资源类�?
    - entity: 知识图谱实体
    - memory: 记忆条目
    - context: 上下�?    - graph: 图谱统计
    """
    server = get_mcp_server()
    resource_type = MCPResourceType(type) if type else None
    resources = await server.list_resources(resource_type, limit)
    return {
        "success": True,
        "resources": [r.to_dict() for r in resources],
        "count": len(resources)
    }


@router.get("/resources/{uri:path}")
async def mcp_read_resource(uri: str):
    """
    MCP: 读取资源内容
    
    URI 格式:
    - memory://entities/{entity_id} - 读取实体
    - memory://memories/{memory_id} - 读取记忆
    - memory://context/{query} - 获取上下�?    - memory://graph/stats - 图谱统计
    """
    server = get_mcp_server()
    full_uri = f"memory://{uri}"
    
    try:
        content = await server.read_resource(full_uri)
        return {
            "success": True,
            "content": content.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"读取资源失败: {e}")
        raise HTTPException(500, f"读取失败: {str(e)}")


@router.post("/search")
async def mcp_search(request: SearchRequest):
    """
    MCP: 搜索资源
    
    在记忆和知识图谱中搜索相关内�?    """
    server = get_mcp_server()
    
    try:
        resource_types = None
        if request.types:
            resource_types = [MCPResourceType(t) for t in request.types]
        
        results = await server.search(
            request.query,
            resource_types,
            request.limit
        )
        
        return {
            "success": True,
            "results": [r.to_dict() for r in results],
            "count": len(results)
        }
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        raise HTTPException(500, f"搜索失败: {str(e)}")


@router.post("/graph/query")
async def mcp_query_graph(request: QueryGraphRequest):
    """
    MCP: 查询知识图谱
    
    获取实体及其关联关系的上下文
    """
    server = get_mcp_server()
    
    try:
        result = await server.query_graph(
            request.entity_id,
            request.depth,
            request.relation_types
        )
        
        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        logger.error(f"图谱查询失败: {e}")
        raise HTTPException(500, f"查询失败: {str(e)}")


@router.post("/memories")
async def mcp_add_memory(request: AddMemoryRequest):
    """
    MCP: 添加记忆
    
    通过 MCP 协议添加新记�?    """
    server = get_mcp_server()
    
    try:
        result = await server.add_memory(
            request.content,
            request.memory_type,
            request.entities,
            request.user_id
        )
        
        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        logger.error(f"添加记忆失败: {e}")
        raise HTTPException(500, f"添加失败: {str(e)}")


@router.get("/stats")
async def mcp_get_stats():
    """
    MCP: 获取统计信息
    
    返回记忆系统的整体统�?    """
    server = get_mcp_server()
    
    try:
        stats = {
            "resources_available": len(await server.list_resources()),
            "handlers_registered": len(server.handlers)
        }
        
        if server.knowledge_graph:
            stats["knowledge_graph"] = server.knowledge_graph.get_stats()
        
        if server.memory_service:
            stats["memory_service"] = server.memory_service.get_stats()
        
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        raise HTTPException(500, f"获取失败: {str(e)}")


@router.post("/rpc")
async def mcp_rpc_call(
    method: str = Body(..., description="方法�?),
    params: Dict = Body(default={}, description="方法参数")
):
    """
    MCP: RPC 调用
    
    通用 RPC 接口，支持所�?MCP 方法
    """
    server = get_mcp_server()
    
    handler = server.handlers.get(method)
    if not handler:
        raise HTTPException(404, f"Method not found: {method}")
    
    try:
        result = await handler(params)
        return {
            "success": True,
            "result": result
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"RPC 调用失败: {method}, {e}")
        raise HTTPException(500, f"调用失败: {str(e)}")
