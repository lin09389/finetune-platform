"""
增强记忆服务
整合短期记忆、长期记忆、知识图谱的统一服务
"""
import logging
from datetime import datetime
from typing import Any

from .intelligent_extractor import (
    ExtractionResult,
    get_memory_extractor,
)
from .knowledge_graph import get_knowledge_graph
from .memory_merger import get_memory_merger
from .memory_service import MemoryService
from .short_term_memory import get_short_term_memory

logger = logging.getLogger(__name__)


class EnhancedMemoryService:
    """
    增强记忆服务
    
    整合多层记忆架构：
    - 工作记忆（当前对话上下文）
    - 短期记忆（会话级记忆）
    - 长期记忆（持久化记忆）
    - 知识图谱（实体关系网络）
    """

    def __init__(
        self,
        vector_db_path: str = "data/memories",
        enable_knowledge_graph: bool = True,
        enable_short_term: bool = True
    ):
        self.memory_service = MemoryService(vector_db_path)

        self.enable_knowledge_graph = enable_knowledge_graph
        self.enable_short_term = enable_short_term

        if enable_knowledge_graph:
            self.knowledge_graph = get_knowledge_graph()
        else:
            self.knowledge_graph = None

        if enable_short_term:
            self.short_term_memory = get_short_term_memory()
        else:
            self.short_term_memory = None

        self.extractor = get_memory_extractor()
        self.merger = get_memory_merger()

        self._session_id: str | None = None
        self._user_id: str = "default"

        logger.info("增强记忆服务初始化完成")

    def set_session(self, session_id: str, user_id: str = "default"):
        """设置当前会话"""
        self._session_id = session_id
        self._user_id = user_id

        if self.short_term_memory:
            self.short_term_memory = get_short_term_memory(session_id)

    async def process_message(
        self,
        message: str,
        role: str,
        extract: bool = True
    ) -> dict[str, Any]:
        """
        处理消息
        
        Args:
            message: 消息内容
            role: 角色
            extract: 是否提取记忆
            
        Returns:
            处理结果
        """
        result = {
            'message_processed': True,
            'memories_extracted': [],
            'entities_extracted': [],
            'relations_extracted': [],
            'context_updated': False
        }

        if self.short_term_memory and role == 'user':
            self.short_term_memory.add_message(role, message)
            result['context_updated'] = True

        if extract and role == 'user':
            extraction = self.extractor.extract(message, role)

            if not extraction.is_empty():
                result['memories_extracted'] = extraction.facts
                result['entities_extracted'] = extraction.entities
                result['relations_extracted'] = extraction.relations

                await self._store_extraction(extraction)

        return result

    async def _store_extraction(self, extraction: ExtractionResult):
        """存储提取结果"""
        for fact in extraction.facts:
            try:
                await self.memory_service.extract_and_store(
                    fact.get('content', ''),
                    'user',
                    self._user_id
                )
            except Exception as e:
                logger.warning(f"存储事实失败: {e}")

        if self.knowledge_graph:
            for entity in extraction.entities:
                try:
                    self.knowledge_graph.add_entity(
                        name=entity.get('name', ''),
                        entity_type=entity.get('type', 'concept'),
                        attributes=entity.get('attributes', {}),
                        confidence=entity.get('confidence', 0.5),
                        source=entity.get('source', 'extraction')
                    )
                except Exception as e:
                    logger.warning(f"添加实体失败: {e}")

            for relation in extraction.relations:
                try:
                    self.knowledge_graph.add_relation(
                        source_name=relation.get('source', ''),
                        target_name=relation.get('target', ''),
                        relation_type=relation.get('relation', 'related_to'),
                        evidence=relation.get('evidence', ''),
                        confidence=relation.get('confidence', 0.5)
                    )
                except Exception as e:
                    logger.warning(f"添加关系失败: {e}")

    async def get_context(
        self,
        query: str,
        max_memories: int = 5,
        include_knowledge_graph: bool = True
    ) -> dict[str, Any]:
        """
        获取上下文
        
        Args:
            query: 查询文本
            max_memories: 最大记忆数
            include_knowledge_graph: 是否包含知识图谱
            
        Returns:
            上下文字典
        """
        context = {
            'short_term': '',
            'long_term': [],
            'knowledge_graph': {},
            'combined': ''
        }

        if self.short_term_memory:
            context['short_term'] = self.short_term_memory.get_context()

        long_term = self.memory_service.recall(
            query,
            self._user_id,
            top_k=max_memories
        )
        context['long_term'] = long_term

        if include_knowledge_graph and self.knowledge_graph:
            entities = self.knowledge_graph.find_entity_by_name(query)
            if entities:
                context['knowledge_graph'] = self.knowledge_graph.get_entity_context(
                    entities.id,
                    depth=2
                )

        combined_parts = []

        if context['short_term']:
            combined_parts.append(f"【当前对话】\n{context['short_term']}")

        if context['long_term']:
            memories_text = "\n".join([
                f"- {m['content']}"
                for m in context['long_term']
            ])
            combined_parts.append(f"【相关记忆】\n{memories_text}")

        if context['knowledge_graph'] and 'entity' in context['knowledge_graph']:
            kg = context['knowledge_graph']
            entity_name = kg['entity'].get('name', '')
            relations = kg.get('relations', [])
            relations_text = "\n".join([
                f"- {r.get('relation_type', '')}: {r.get('target_id', '')}"
                for r in relations[:5]
            ])
            combined_parts.append(f"【知识图谱: {entity_name}】\n{relations_text}")

        context['combined'] = "\n\n".join(combined_parts)

        return context

    async def recall(
        self,
        query: str,
        top_k: int = 5,
        memory_type: str | None = None,
        user_id: str | None = None
    ) -> list[dict[str, Any]]:
        """
        检索记忆
        
        Args:
            query: 查询文本
            top_k: 返回数量
            memory_type: 记忆类型过滤
            user_id: 用户 ID（可选，用于兼容性）
            
        Returns:
            记忆列表
        """
        results = []

        effective_user_id = user_id or self._user_id

        long_term = self.memory_service.recall(
            query,
            effective_user_id,
            top_k=top_k,
            memory_type=memory_type
        )
        results.extend(long_term)

        if self.short_term_memory and len(results) < top_k:
            relevant = self.short_term_memory.find_relevant_messages(
                query,
                top_k=top_k - len(results)
            )
            for msg in relevant:
                results.append({
                    'id': f"stm_{msg.timestamp.timestamp()}",
                    'content': msg.content,
                    'type': 'short_term',
                    'importance': msg.importance,
                    'created_at': msg.timestamp.isoformat(),
                    'source': 'short_term_memory'
                })

        return results[:top_k]

    async def remember(
        self,
        content: str,
        memory_type: str = "knowledge",
        importance: float = 0.5,
        entities: list[str] = None
    ) -> dict[str, Any]:
        """
        主动记忆
        
        Args:
            content: 记忆内容
            memory_type: 记忆类型
            importance: 重要性
            entities: 相关实体
            
        Returns:
            存储结果
        """
        result = {
            'success': False,
            'memory_id': None,
            'entities_added': [],
            'message': ''
        }

        try:
            memories = await self.memory_service.extract_and_store(
                content,
                'user',
                self._user_id
            )

            if memories:
                result['success'] = True
                result['memory_id'] = memories[0].get('id')
                result['message'] = f"已记住: {content[:50]}..."
            else:
                result['message'] = "记忆内容已存在或无法提取"

            if self.knowledge_graph and entities:
                for entity_name in entities:
                    entity_id, is_new = self.knowledge_graph.add_entity(
                        name=entity_name,
                        entity_type='concept',
                        confidence=importance
                    )
                    if is_new:
                        result['entities_added'].append(entity_name)

        except Exception as e:
            result['message'] = f"记忆失败: {str(e)}"
            logger.error(f"主动记忆失败: {e}")

        return result

    async def forget(
        self,
        memory_id: str,
        memory_scope: str = "long_term"
    ) -> bool:
        """
        遗忘记忆
        
        Args:
            memory_id: 记忆ID
            memory_scope: 记忆范围 (long_term/short_term/knowledge_graph)
            
        Returns:
            是否成功
        """
        if memory_scope == "long_term":
            return self.memory_service.forget(self._user_id, memory_id)
        elif memory_scope == "knowledge_graph" and self.knowledge_graph:
            return self.knowledge_graph.delete_entity(memory_id)

        return False

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        stats = {
            'long_term': self.memory_service.get_stats(self._user_id),
            'short_term': {},
            'knowledge_graph': {}
        }

        if self.short_term_memory:
            stats['short_term'] = self.short_term_memory.summarize()

        if self.knowledge_graph:
            stats['knowledge_graph'] = self.knowledge_graph.get_stats()

        return stats

    def get_user_summary(self) -> dict[str, Any]:
        """获取用户记忆摘要"""
        summary = self.memory_service.get_user_summary(self._user_id)

        if self.knowledge_graph:
            kg_stats = self.knowledge_graph.get_stats()
            summary['knowledge_graph'] = {
                'entities': kg_stats.get('total_entities', 0),
                'relations': kg_stats.get('total_relations', 0)
            }

        return summary

    def clear_session(self):
        """清空当前会话"""
        if self.short_term_memory:
            self.short_term_memory.clear()

    async def export_memories(self) -> dict[str, Any]:
        """导出所有记忆"""
        export_data = {
            'user_id': self._user_id,
            'exported_at': datetime.now().isoformat(),
            'long_term': [],
            'knowledge_graph': None
        }

        memories = self.memory_service.list_memories(self._user_id, limit=1000)
        export_data['long_term'] = memories

        if self.knowledge_graph:
            export_data['knowledge_graph'] = self.knowledge_graph.to_dict()

        return export_data

    async def import_memories(
        self,
        data: dict[str, Any],
        merge: bool = True
    ) -> dict[str, Any]:
        """
        导入记忆
        
        Args:
            data: 导入数据
            merge: 是否合并
            
        Returns:
            导入结果
        """
        result = {
            'success': True,
            'imported_count': 0,
            'skipped_count': 0,
            'message': ''
        }

        if 'long_term' in data:
            for mem in data['long_term']:
                try:
                    await self.memory_service.extract_and_store(
                        mem.get('content', ''),
                        'user',
                        self._user_id
                    )
                    result['imported_count'] += 1
                except Exception as e:
                    logger.warning(f"导入记忆失败: {e}")
                    result['skipped_count'] += 1

        if self.knowledge_graph and 'knowledge_graph' in data:
            self.knowledge_graph.from_dict(data['knowledge_graph'])

        result['message'] = f"导入完成: {result['imported_count']} 条, 跳过 {result['skipped_count']} 条"

        return result


_enhanced_memory_service: EnhancedMemoryService | None = None


def get_enhanced_memory_service(
    vector_db_path: str = "data/memories",
    enable_knowledge_graph: bool = True,
    enable_short_term: bool = True
) -> EnhancedMemoryService:
    """获取增强记忆服务实例"""
    global _enhanced_memory_service
    if _enhanced_memory_service is None:
        _enhanced_memory_service = EnhancedMemoryService(
            vector_db_path,
            enable_knowledge_graph,
            enable_short_term
        )
    return _enhanced_memory_service


def reset_enhanced_memory_service(
    vector_db_path: str = "data/memories",
    enable_knowledge_graph: bool = True,
    enable_short_term: bool = True
) -> EnhancedMemoryService:
    """重置增强记忆服务"""
    global _enhanced_memory_service
    _enhanced_memory_service = EnhancedMemoryService(
        vector_db_path,
        enable_knowledge_graph,
        enable_short_term
    )
    return _enhanced_memory_service
