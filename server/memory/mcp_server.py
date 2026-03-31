"""
MCP (Model Context Protocol) 服务器
提供记忆服务的 MCP 协议接口
"""
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .enhanced_memory_service import get_enhanced_memory_service

logger = logging.getLogger(__name__)


class MCPResourceType(str, Enum):
    """MCP 资源类型"""
    MEMORY = "memory"
    ENTITY = "entity"
    RELATION = "relation"
    CONTEXT = "context"
    CONVERSATION = "conversation"


@dataclass
class MCPResource:
    """MCP 资源"""
    uri: str
    name: str
    description: str
    resource_type: MCPResourceType
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'uri': self.uri,
            'name': self.name,
            'description': self.description,
            'type': self.resource_type.value,
            'metadata': self.metadata
        }


@dataclass
class MCPResourceContent:
    """MCP 资源内容"""
    uri: str
    mime_type: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
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
    resource_type: MCPResourceType

    def to_dict(self) -> dict[str, Any]:
        return {
            'uri': self.uri,
            'name': self.name,
            'description': self.description,
            'score': self.score,
            'type': self.resource_type.value
        }


class MCPServer:
    """
    MCP 服务器
    
    实现 Model Context Protocol，提供：
    - 资源列表
    - 资源读取
    - 资源搜索
    - 工具调用
    """

    def __init__(self, server_name: str = "memory-server"):
        self.server_name = server_name
        self.memory_service = get_enhanced_memory_service()

        self._tools: dict[str, Callable] = {}
        self._resource_handlers: dict[str, Callable] = {}

        self._register_default_tools()
        self._register_resource_handlers()

        logger.info(f"MCP 服务器初始化: {server_name}")

    def _register_default_tools(self):
        """注册默认工具"""
        self._tools = {
            'remember': self._tool_remember,
            'recall': self._tool_recall,
            'forget': self._tool_forget,
            'get_context': self._tool_get_context,
            'add_entity': self._tool_add_entity,
            'add_relation': self._tool_add_relation,
            'search_entities': self._tool_search_entities,
            'get_stats': self._tool_get_stats,
        }

    def _register_resource_handlers(self):
        """注册资源处理器"""
        self._resource_handlers = {
            'memory': self._handle_memory_resource,
            'entity': self._handle_entity_resource,
            'relation': self._handle_relation_resource,
            'context': self._handle_context_resource,
            'conversation': self._handle_conversation_resource,
        }

    async def list_resources(self) -> list[MCPResource]:
        """列出所有可用资源"""
        resources = []

        resources.append(MCPResource(
            uri="memory://all",
            name="所有记忆",
            description="获取所有存储的记忆",
            resource_type=MCPResourceType.MEMORY
        ))

        resources.append(MCPResource(
            uri="memory://recent",
            name="最近记忆",
            description="获取最近的记忆",
            resource_type=MCPResourceType.MEMORY
        ))

        resources.append(MCPResource(
            uri="entity://all",
            name="所有实体",
            description="获取知识图谱中的所有实体",
            resource_type=MCPResourceType.ENTITY
        ))

        resources.append(MCPResource(
            uri="relation://all",
            name="所有关系",
            description="获取知识图谱中的所有关系",
            resource_type=MCPResourceType.RELATION
        ))

        resources.append(MCPResource(
            uri="context://current",
            name="当前上下文",
            description="获取当前会话上下文",
            resource_type=MCPResourceType.CONTEXT
        ))

        resources.append(MCPResource(
            uri="conversation://history",
            name="对话历史",
            description="获取当前会话的对话历史",
            resource_type=MCPResourceType.CONVERSATION
        ))

        return resources

    async def read_resource(self, uri: str) -> MCPResourceContent:
        """读取资源"""
        parts = uri.split("://")
        if len(parts) != 2:
            raise ValueError(f"无效的资源 URI: {uri}")

        resource_type = parts[0]
        resource_id = parts[1]

        handler = self._resource_handlers.get(resource_type)
        if not handler:
            raise ValueError(f"未知的资源类型: {resource_type}")

        return await handler(resource_id)

    async def search_resources(
        self,
        query: str,
        resource_types: list[str] = None
    ) -> list[MCPSearchResult]:
        """搜索资源"""
        results = []

        memories = await self.memory_service.recall(query, top_k=5)
        for mem in memories:
            results.append(MCPSearchResult(
                uri=f"memory://{mem.get('id', '')}",
                name=mem.get('content', '')[:50],
                description=mem.get('content', ''),
                score=mem.get('relevance', 0.5),
                resource_type=MCPResourceType.MEMORY
            ))

        if self.memory_service.knowledge_graph:
            entities = self.memory_service.knowledge_graph.get_all_entities()
            query_lower = query.lower()

            for entity in entities[:10]:
                if query_lower in entity.name.lower():
                    results.append(MCPSearchResult(
                        uri=f"entity://{entity.id}",
                        name=entity.name,
                        description=f"{entity.entity_type}: {entity.name}",
                        score=0.8,
                        resource_type=MCPResourceType.ENTITY
                    ))

        return results

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """调用工具"""
        tool = self._tools.get(tool_name)
        if not tool:
            return {
                'success': False,
                'error': f"未知的工具: {tool_name}"
            }

        try:
            result = await tool(**arguments)
            return {
                'success': True,
                'result': result
            }
        except Exception as e:
            logger.error(f"工具调用失败: {tool_name}, {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def list_tools(self) -> list[dict[str, Any]]:
        """列出所有可用工具"""
        return [
            {
                'name': 'remember',
                'description': '记住一条信息',
                'parameters': {
                    'content': {'type': 'string', 'description': '要记住的内容'},
                    'memory_type': {'type': 'string', 'default': 'knowledge'},
                    'importance': {'type': 'number', 'default': 0.5}
                }
            },
            {
                'name': 'recall',
                'description': '检索相关记忆',
                'parameters': {
                    'query': {'type': 'string', 'description': '查询文本'},
                    'top_k': {'type': 'integer', 'default': 5}
                }
            },
            {
                'name': 'forget',
                'description': '遗忘一条记忆',
                'parameters': {
                    'memory_id': {'type': 'string', 'description': '记忆ID'}
                }
            },
            {
                'name': 'get_context',
                'description': '获取当前上下文',
                'parameters': {
                    'query': {'type': 'string', 'description': '查询文本'},
                    'max_memories': {'type': 'integer', 'default': 5}
                }
            },
            {
                'name': 'add_entity',
                'description': '添加实体到知识图谱',
                'parameters': {
                    'name': {'type': 'string', 'description': '实体名称'},
                    'entity_type': {'type': 'string', 'description': '实体类型'},
                    'attributes': {'type': 'object', 'default': {}}
                }
            },
            {
                'name': 'add_relation',
                'description': '添加关系到知识图谱',
                'parameters': {
                    'source': {'type': 'string', 'description': '源实体名称'},
                    'target': {'type': 'string', 'description': '目标实体名称'},
                    'relation_type': {'type': 'string', 'description': '关系类型'}
                }
            },
            {
                'name': 'search_entities',
                'description': '搜索知识图谱中的实体',
                'parameters': {
                    'query': {'type': 'string', 'description': '查询文本'},
                    'entity_type': {'type': 'string', 'default': None}
                }
            },
            {
                'name': 'get_stats',
                'description': '获取记忆系统统计信息',
                'parameters': {}
            }
        ]

    async def _handle_memory_resource(self, resource_id: str) -> MCPResourceContent:
        """处理记忆资源"""
        if resource_id == "all":
            memories = self.memory_service.memory_service.list_memories(
                self.memory_service._user_id,
                limit=100
            )
            content = json.dumps(memories, ensure_ascii=False, indent=2)
        elif resource_id == "recent":
            memories = self.memory_service.memory_service.list_memories(
                self.memory_service._user_id,
                limit=10
            )
            content = json.dumps(memories, ensure_ascii=False, indent=2)
        else:
            memory = self.memory_service.memory_service.get_memory(
                self.memory_service._user_id,
                resource_id
            )
            if memory:
                content = json.dumps(memory, ensure_ascii=False, indent=2)
            else:
                content = json.dumps({'error': 'Memory not found'})

        return MCPResourceContent(
            uri=f"memory://{resource_id}",
            mime_type="application/json",
            text=content
        )

    async def _handle_entity_resource(self, resource_id: str) -> MCPResourceContent:
        """处理实体资源"""
        if not self.memory_service.knowledge_graph:
            return MCPResourceContent(
                uri=f"entity://{resource_id}",
                mime_type="application/json",
                text=json.dumps({'error': 'Knowledge graph not enabled'})
            )

        if resource_id == "all":
            entities = self.memory_service.knowledge_graph.get_all_entities()
            content = json.dumps(
                [e.to_dict() for e in entities],
                ensure_ascii=False,
                indent=2
            )
        else:
            entity = self.memory_service.knowledge_graph.get_entity(resource_id)
            if entity:
                content = json.dumps(entity.to_dict(), ensure_ascii=False, indent=2)
            else:
                content = json.dumps({'error': 'Entity not found'})

        return MCPResourceContent(
            uri=f"entity://{resource_id}",
            mime_type="application/json",
            text=content
        )

    async def _handle_relation_resource(self, resource_id: str) -> MCPResourceContent:
        """处理关系资源"""
        if not self.memory_service.knowledge_graph:
            return MCPResourceContent(
                uri=f"relation://{resource_id}",
                mime_type="application/json",
                text=json.dumps({'error': 'Knowledge graph not enabled'})
            )

        if resource_id == "all":
            relations = self.memory_service.knowledge_graph.get_all_relations()
            content = json.dumps(
                [r.to_dict() for r in relations],
                ensure_ascii=False,
                indent=2
            )
        else:
            content = json.dumps({'error': 'Single relation not supported'})

        return MCPResourceContent(
            uri=f"relation://{resource_id}",
            mime_type="application/json",
            text=content
        )

    async def _handle_context_resource(self, resource_id: str) -> MCPResourceContent:
        """处理上下文资源"""
        if resource_id == "current":
            context = await self.memory_service.get_context("")
            content = json.dumps(context, ensure_ascii=False, indent=2)
        else:
            content = json.dumps({'error': 'Unknown context resource'})

        return MCPResourceContent(
            uri=f"context://{resource_id}",
            mime_type="application/json",
            text=content
        )

    async def _handle_conversation_resource(self, resource_id: str) -> MCPResourceContent:
        """处理对话资源"""
        if resource_id == "history":
            if self.memory_service.short_term_memory:
                messages = self.memory_service.short_term_memory.get_recent_messages(20)
                content = json.dumps(
                    [m.to_dict() for m in messages],
                    ensure_ascii=False,
                    indent=2
                )
            else:
                content = json.dumps([])
        else:
            content = json.dumps({'error': 'Unknown conversation resource'})

        return MCPResourceContent(
            uri=f"conversation://{resource_id}",
            mime_type="application/json",
            text=content
        )

    async def _tool_remember(
        self,
        content: str,
        memory_type: str = "knowledge",
        importance: float = 0.5
    ) -> dict[str, Any]:
        """记住工具"""
        return await self.memory_service.remember(
            content=content,
            memory_type=memory_type,
            importance=importance
        )

    async def _tool_recall(
        self,
        query: str,
        top_k: int = 5
    ) -> list[dict[str, Any]]:
        """检索工具"""
        return await self.memory_service.recall(query, top_k=top_k)

    async def _tool_forget(self, memory_id: str) -> dict[str, Any]:
        """遗忘工具"""
        success = await self.memory_service.forget(memory_id)
        return {
            'success': success,
            'memory_id': memory_id
        }

    async def _tool_get_context(
        self,
        query: str,
        max_memories: int = 5
    ) -> dict[str, Any]:
        """获取上下文工具"""
        return await self.memory_service.get_context(
            query,
            max_memories=max_memories
        )

    async def _tool_add_entity(
        self,
        name: str,
        entity_type: str,
        attributes: dict[str, Any] = None
    ) -> dict[str, Any]:
        """添加实体工具"""
        if not self.memory_service.knowledge_graph:
            return {'success': False, 'error': 'Knowledge graph not enabled'}

        entity_id, is_new = self.memory_service.knowledge_graph.add_entity(
            name=name,
            entity_type=entity_type,
            attributes=attributes or {}
        )

        return {
            'success': True,
            'entity_id': entity_id,
            'is_new': is_new
        }

    async def _tool_add_relation(
        self,
        source: str,
        target: str,
        relation_type: str
    ) -> dict[str, Any]:
        """添加关系工具"""
        if not self.memory_service.knowledge_graph:
            return {'success': False, 'error': 'Knowledge graph not enabled'}

        relation_id = self.memory_service.knowledge_graph.add_relation(
            source_name=source,
            target_name=target,
            relation_type=relation_type
        )

        return {
            'success': relation_id is not None,
            'relation_id': relation_id
        }

    async def _tool_search_entities(
        self,
        query: str,
        entity_type: str = None
    ) -> list[dict[str, Any]]:
        """搜索实体工具"""
        if not self.memory_service.knowledge_graph:
            return []

        if entity_type:
            entities = self.memory_service.knowledge_graph.get_entities_by_type(entity_type)
        else:
            entities = self.memory_service.knowledge_graph.get_all_entities()

        query_lower = query.lower()
        results = [
            e.to_dict()
            for e in entities
            if query_lower in e.name.lower()
        ]

        return results[:10]

    async def _tool_get_stats(self) -> dict[str, Any]:
        """获取统计工具"""
        return self.memory_service.get_stats()


_mcp_server: MCPServer | None = None


def get_mcp_server() -> MCPServer:
    """获取 MCP 服务器实例"""
    global _mcp_server
    if _mcp_server is None:
        _mcp_server = MCPServer()
    return _mcp_server
