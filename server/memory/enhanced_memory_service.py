"""
增强版智能记忆服�?集成知识图谱、短期记忆、智能提取和记忆合并
"""
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import uuid
import logging
import os
from pathlib import Path
import json

from .memory_extractor import MemoryExtractor
from .models import MemoryType, MEMORY_IMPORTANCE, MEMORY_TYPE_LABELS
from .knowledge_graph import KnowledgeGraph, Entity, Relation, get_knowledge_graph
from .short_term_memory import ShortTermMemory, get_short_term_memory, get_stm_manager
from .intelligent_extractor import IntelligentMemoryExtractor, ExtractionResult
from .memory_merger import MemoryMerger, MemoryUpdater, get_memory_merger

logger = logging.getLogger(__name__)


def _setup_hf_mirror():
    """配置 HuggingFace 镜像�?""
    from core.config import get_settings
    
    settings = get_settings()
    hf_mirror = settings.hf_mirror
    
    mirrors = {
        "hf-mirror": "https://hf-mirror.com",
        "aliyun": "https://mirrors.aliyun.com/huggingface",
        "modelscope": "https://modelscope.cn/models",
    }
    
    if hf_mirror in mirrors:
        os.environ["HF_ENDPOINT"] = mirrors[hf_mirror]
        logger.info(f"已配�?HuggingFace 镜像�? {mirrors[hf_mirror]}")


class EnhancedMemoryService:
    """增强版智能记忆服�?- 三级记忆架构"""
    
    def __init__(
        self,
        vector_db_path: str = "data/memories",
        use_llm_extraction: bool = False,
        llm_client=None
    ):
        """
        初始化增强版记忆服务
        
        Args:
            vector_db_path: 向量数据库路�?            use_llm_extraction: 是否使用LLM辅助提取
            llm_client: LLM客户�?        """
        self.embedder = None
        self.vector_store = None
        self._embedding_available = False
        
        try:
            _setup_hf_mirror()
            
            from rag.embedder import get_embedder
            from rag.vector_store import get_vector_store
            
            self.embedder = get_embedder("shibing624/text2vec-base-chinese")
            self.vector_store = get_vector_store(vector_db_path)
            self._embedding_available = True
            logger.info("嵌入模型加载成功")
        except Exception as e:
            logger.warning(f"嵌入模型加载失败，使用简化模�? {e}")
        
        self.legacy_extractor = MemoryExtractor()
        self.intelligent_extractor = IntelligentMemoryExtractor(
            llm_client=llm_client if use_llm_extraction else None,
            use_llm=use_llm_extraction
        )
        
        self.knowledge_graph = get_knowledge_graph()
        self.short_term_memory = get_short_term_memory()
        self.memory_merger = get_memory_merger()
        self.memory_updater = MemoryUpdater(self.knowledge_graph, self.memory_merger)
        
        self.simple_memories: Dict[str, List[Dict]] = {}
        
        self.data_dir = Path(vector_db_path).parent
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self._load_knowledge_graph()
        
        logger.info("增强版记忆服务已初始�?)
    
    def process_message(
        self,
        message: str,
        role: str,
        user_id: str = "default",
        session_id: str = None,
        extract_memories: bool = True
    ) -> Dict[str, Any]:
        """
        处理消息 - 完整的记忆处理流�?        
        Args:
            message: 消息内容
            role: 角色 (user/assistant)
            user_id: 用户ID
            session_id: 会话ID
            extract_memories: 是否提取记忆
            
        Returns:
            处理结果
        """
        result = {
            'message_stored': False,
            'entities_extracted': [],
            'relations_extracted': [],
            'facts_extracted': [],
            'active_entities': [],
            'context': ''
        }
        
        stm = get_short_term_memory(session_id)
        stm.add_message(role, message)
        result['message_stored'] = True
        
        if extract_memories and role == 'user':
            extraction = self.intelligent_extractor.extract(message, role)
            
            if not extraction.is_empty():
                stored = self._store_extraction_result(extraction, user_id)
                result['entities_extracted'] = stored['entities']
                result['relations_extracted'] = stored['relations']
                result['facts_extracted'] = stored['facts']
                
                entity_ids = [e.get('id') for e in stored['entities'] if e.get('id')]
                stm.add_message(role, message, entities=entity_ids)
        
        result['active_entities'] = stm.get_active_entities()
        result['context'] = self._build_enhanced_context(message, user_id, session_id)
        
        return result
    
    def _store_extraction_result(
        self,
        extraction: ExtractionResult,
        user_id: str
    ) -> Dict[str, List[Dict]]:
        """存储提取结果"""
        stored = {'entities': [], 'relations': [], 'facts': []}
        
        for entity_data in extraction.entities:
            try:
                entity_id, is_new = self.knowledge_graph.add_entity(
                    name=entity_data.get('name', ''),
                    entity_type=entity_data.get('type', 'concept'),
                    attributes=entity_data.get('attributes', {}),
                    confidence=entity_data.get('confidence', 0.5),
                    source=entity_data.get('source', 'extraction')
                )
                
                entity_data['id'] = entity_id
                entity_data['is_new'] = is_new
                stored['entities'].append(entity_data)
                
            except Exception as e:
                logger.warning(f"存储实体失败: {e}")
        
        for relation_data in extraction.relations:
            try:
                relation_id = self.knowledge_graph.add_relation(
                    source_name=relation_data.get('source', ''),
                    target_name=relation_data.get('target', ''),
                    relation_type=relation_data.get('relation', 'related_to'),
                    evidence=relation_data.get('evidence', ''),
                    weight=1.0,
                    confidence=relation_data.get('confidence', 0.5)
                )
                
                if relation_id:
                    relation_data['id'] = relation_id
                    stored['relations'].append(relation_data)
                    
            except Exception as e:
                logger.warning(f"存储关系失败: {e}")
        
        for fact_data in extraction.facts:
            try:
                memory_id = self._store_fact(fact_data, user_id)
                fact_data['id'] = memory_id
                stored['facts'].append(fact_data)
                
            except Exception as e:
                logger.warning(f"存储事实失败: {e}")
        
        return stored
    
    def _store_fact(self, fact: Dict, user_id: str) -> str:
        """存储事实到长期记�?""
        memory_id = f"mem_{uuid.uuid4().hex[:8]}"
        
        metadata = {
            'user_id': user_id,
            'type': fact.get('type', 'knowledge'),
            'importance': fact.get('confidence', 0.5),
            'source': fact.get('source', 'extraction'),
            'created_at': datetime.now().isoformat(),
            'access_count': 0
        }
        
        if self._embedding_available and self.embedder and self.vector_store:
            try:
                embedding = self.embedder.embed_single(fact.get('content', ''))
                
                self.vector_store.add_documents(
                    collection_name=f"memories_{user_id}",
                    documents=[fact.get('content', '')],
                    embeddings=[embedding],
                    metadatas=[metadata],
                    ids=[memory_id]
                )
                return memory_id
            except Exception as e:
                logger.warning(f"向量存储失败: {e}")
        
        if user_id not in self.simple_memories:
            self.simple_memories[user_id] = []
        
        self.simple_memories[user_id].append({
            'id': memory_id,
            'content': fact.get('content', ''),
            **metadata
        })
        
        return memory_id
    
    def recall(
        self,
        query: str,
        user_id: str = "default",
        session_id: str = None,
        top_k: int = 5,
        memory_type: Optional[str] = None,
        include_graph: bool = True
    ) -> List[Dict[str, Any]]:
        """
        增强版记忆检�?        
        Args:
            query: 查询文本
            user_id: 用户ID
            session_id: 会话ID
            top_k: 返回数量
            memory_type: 记忆类型过滤
            include_graph: 是否包含知识图谱检�?            
        Returns:
            相关记忆列表
        """
        memories = []
        
        stm = get_short_term_memory(session_id)
        stm_messages = stm.find_relevant_messages(query, top_k=3)
        for msg in stm_messages:
            memories.append({
                'id': f"stm_{uuid.uuid4().hex[:4]}",
                'content': msg.content,
                'type': 'short_term',
                'importance': msg.importance,
                'source': 'short_term_memory',
                'relevance': 0.9
            })
        
        if self._embedding_available and self.embedder and self.vector_store:
            try:
                query_embedding = self.embedder.embed_single(query)
                
                filter_metadata = None
                if memory_type:
                    filter_metadata = {"type": memory_type}
                
                results = self.vector_store.search(
                    collection_name=f"memories_{user_id}",
                    query_embedding=query_embedding,
                    top_k=top_k,
                    filter_metadata=filter_metadata
                )
                
                for result in results:
                    meta = result.get('metadata', {})
                    memories.append({
                        'id': meta.get('id', ''),
                        'content': result['content'],
                        'type': meta.get('type', 'knowledge'),
                        'importance': meta.get('importance', 0.5),
                        'created_at': meta.get('created_at', ''),
                        'access_count': meta.get('access_count', 0),
                        'source': 'long_term_memory',
                        'relevance': result.get('score', 0)
                    })
                    
            except Exception as e:
                logger.warning(f"向量检索失�? {e}")
        
        if include_graph:
            graph_memories = self._search_knowledge_graph(query, top_k=3)
            memories.extend(graph_memories)
        
        memories.sort(key=lambda x: x.get('relevance', 0), reverse=True)
        return memories[:top_k]
    
    def _search_knowledge_graph(self, query: str, top_k: int = 5) -> List[Dict]:
        """在知识图谱中搜索"""
        memories = []
        
        query_lower = query.lower()
        
        for entity in self.knowledge_graph.get_all_entities():
            if entity.name.lower() in query_lower or query_lower in entity.name.lower():
                context = self.knowledge_graph.get_entity_context(entity.id, depth=1)
                
                related_info = []
                for rel in context.get('relations', []):
                    related_info.append(f"{rel.get('relation_type', '')}: {rel.get('target_id', '')}")
                
                memory_content = f"实体: {entity.name} ({entity.entity_type})"
                if entity.attributes:
                    memory_content += f" | 属�? {json.dumps(entity.attributes, ensure_ascii=False)}"
                if related_info:
                    memory_content += f" | 关系: {', '.join(related_info[:3])}"
                
                memories.append({
                    'id': entity.id,
                    'content': memory_content,
                    'type': 'entity',
                    'importance': entity.confidence,
                    'source': 'knowledge_graph',
                    'relevance': 0.8
                })
        
        return memories[:top_k]
    
    def _build_enhanced_context(
        self,
        query: str,
        user_id: str,
        session_id: str = None
    ) -> str:
        """构建增强版上下文"""
        context_parts = []
        
        stm = get_short_term_memory(session_id)
        stm_context = stm.get_context(max_tokens=1000)
        if stm_context:
            context_parts.append("【近期对话�?)
            context_parts.append(stm_context)
        
        active_entities = stm.get_active_entities()
        if active_entities:
            context_parts.append("\n【活跃实体�?)
            for entity_id in active_entities[:5]:
                entity = self.knowledge_graph.get_entity(entity_id)
                if entity:
                    context_parts.append(f"- {entity.name} ({entity.entity_type})")
        
        relevant_memories = self.recall(
            query, user_id, session_id, top_k=3, include_graph=False
        )
        if relevant_memories:
            context_parts.append("\n【相关记忆�?)
            for mem in relevant_memories:
                context_parts.append(f"- {mem['content'][:100]}")
        
        return "\n".join(context_parts)
    
    def get_entity_context(
        self,
        entity_name: str,
        depth: int = 2
    ) -> Dict[str, Any]:
        """
        获取实体的完整上下文（多跳关系）
        
        Args:
            entity_name: 实体名称
            depth: 遍历深度
            
        Returns:
            实体上下�?        """
        entity = self.knowledge_graph.find_entity_by_name(entity_name)
        if not entity:
            return {'error': f'Entity not found: {entity_name}'}
        
        return self.knowledge_graph.get_entity_context(entity.id, depth)
    
    def find_entity_path(
        self,
        source_name: str,
        target_name: str,
        max_depth: int = 4
    ) -> List[List[Dict]]:
        """
        查找两个实体之间的关系路�?        
        Args:
            source_name: 源实体名�?            target_name: 目标实体名称
            max_depth: 最大搜索深�?            
        Returns:
            路径列表
        """
        source = self.knowledge_graph.find_entity_by_name(source_name)
        target = self.knowledge_graph.find_entity_by_name(target_name)
        
        if not source or not target:
            return []
        
        return self.knowledge_graph.find_path(source.id, target.id, max_depth)
    
    def list_memories(
        self,
        user_id: str = "default",
        memory_type: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """列出所有记�?""
        memories = []
        
        if self._embedding_available and self.vector_store:
            try:
                collection = self.vector_store.get_or_create_collection(
                    f"memories_{user_id}"
                )
                
                all_data = collection.get(include=["metadatas", "documents"])
                
                if all_data['metadatas'] and all_data['documents']:
                    for i, (meta, doc) in enumerate(
                        zip(all_data['metadatas'], all_data['documents'])
                    ):
                        if memory_type and meta.get('type') != memory_type:
                            continue
                        
                        memories.append({
                            'id': all_data['ids'][i],
                            'content': doc,
                            'type': meta.get('type', 'knowledge'),
                            'importance': meta.get('importance', 0.5),
                            'created_at': meta.get('created_at', ''),
                            'access_count': meta.get('access_count', 0)
                        })
            except Exception as e:
                logger.warning(f"向量存储读取失败: {e}")
        
        if user_id in self.simple_memories:
            for mem in self.simple_memories[user_id]:
                if memory_type and mem.get('type') != memory_type:
                    continue
                memories.append(mem)
        
        memories.sort(key=lambda x: x['importance'], reverse=True)
        
        return memories[:limit]
    
    def forget(self, user_id: str, memory_id: str) -> bool:
        """删除记忆"""
        success = False
        
        if self._embedding_available and self.vector_store:
            try:
                self.vector_store.delete_documents(
                    collection_name=f"memories_{user_id}",
                    ids=[memory_id]
                )
                success = True
            except Exception as e:
                logger.warning(f"向量存储删除失败: {e}")
        
        if user_id in self.simple_memories:
            self.simple_memories[user_id] = [
                m for m in self.simple_memories[user_id]
                if m['id'] != memory_id
            ]
            success = True
        
        if success:
            logger.info(f"记忆已删�? {memory_id}")
        
        return success
    
    def clear_all(self, user_id: str = "default") -> bool:
        """清除用户所有记�?""
        try:
            if self.vector_store:
                self.vector_store.delete_collection(f"memories_{user_id}")
            
            if user_id in self.simple_memories:
                del self.simple_memories[user_id]
            
            logger.info(f"已清除用�?{user_id} 的所有记�?)
            return True
        except Exception as e:
            logger.error(f"清除记忆失败: {e}")
            return False
    
    def get_context_with_memory(
        self,
        query: str,
        user_id: str = "default",
        max_memories: int = 5
    ) -> str:
        """获取包含记忆的上下文"""
        return self._build_enhanced_context(query, user_id)
    
    def get_user_summary(self, user_id: str = "default") -> Dict[str, Any]:
        """获取用户记忆摘要"""
        memories = self.list_memories(user_id, limit=100)
        
        by_type: Dict[str, List[str]] = {}
        for mem in memories:
            mem_type = mem['type']
            if mem_type not in by_type:
                by_type[mem_type] = []
            by_type[mem_type].append(mem['content'])
        
        kg_stats = self.knowledge_graph.get_stats()
        
        summary = {
            'total_count': len(memories),
            'by_type': {
                MEMORY_TYPE_LABELS.get(MemoryType(k), k): v
                for k, v in by_type.items()
            },
            'recent_memories': memories[:5] if memories else [],
            'knowledge_graph': kg_stats
        }
        
        return summary
    
    def get_stats(self, user_id: str = "default") -> Dict[str, Any]:
        """获取记忆统计"""
        stats = {
            'total_memories': 0,
            'knowledge_graph': self.knowledge_graph.get_stats(),
            'short_term_memory': get_short_term_memory().summarize()
        }
        
        try:
            if self.vector_store:
                vs_stats = self.vector_store.get_collection_stats(f"memories_{user_id}")
                stats['total_memories'] = vs_stats.get('count', 0)
        except Exception:
            pass
        
        if user_id in self.simple_memories:
            stats['total_memories'] += len(self.simple_memories[user_id])
        
        return stats
    
    def export_state(self, user_id: str = "default") -> Dict[str, Any]:
        """导出记忆状�?""
        return {
            'memories': self.list_memories(user_id, limit=1000),
            'knowledge_graph': self.knowledge_graph.to_dict(),
            'short_term_memory': get_short_term_memory().export_state(),
            'exported_at': datetime.now().isoformat()
        }
    
    def import_state(self, state: Dict[str, Any], user_id: str = "default"):
        """导入记忆状�?""
        if 'knowledge_graph' in state:
            self.knowledge_graph.from_dict(state['knowledge_graph'])
        
        if 'short_term_memory' in state:
            get_short_term_memory().import_state(state['short_term_memory'])
        
        if 'memories' in state:
            for mem in state['memories']:
                self._store_fact(mem, user_id)
        
        logger.info(f"导入记忆状态完�?)
    
    def _load_knowledge_graph(self):
        """加载知识图谱（从文件�?""
        kg_file = self.data_dir / "knowledge_graph.json"
        if kg_file.exists():
            try:
                with open(kg_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.knowledge_graph.from_dict(data)
                logger.info(f"加载知识图谱: {len(self.knowledge_graph.entities)} 实体")
            except Exception as e:
                logger.warning(f"加载知识图谱失败: {e}")
    
    def save_knowledge_graph(self):
        """保存知识图谱到文�?""
        kg_file = self.data_dir / "knowledge_graph.json"
        try:
            with open(kg_file, 'w', encoding='utf-8') as f:
                json.dump(self.knowledge_graph.to_dict(), f, ensure_ascii=False, indent=2)
            logger.info("知识图谱已保�?)
        except Exception as e:
            logger.error(f"保存知识图谱失败: {e}")


_enhanced_memory_service: Optional[EnhancedMemoryService] = None


def get_enhanced_memory_service(
    vector_db_path: str = "data/memories",
    use_llm_extraction: bool = False,
    llm_client=None
) -> EnhancedMemoryService:
    """获取增强版记忆服务实�?""
    global _enhanced_memory_service
    if _enhanced_memory_service is None:
        _enhanced_memory_service = EnhancedMemoryService(
            vector_db_path, use_llm_extraction, llm_client
        )
    return _enhanced_memory_service


def reset_enhanced_memory_service(
    vector_db_path: str = "data/memories"
) -> EnhancedMemoryService:
    """重置增强版记忆服�?""
    global _enhanced_memory_service
    _enhanced_memory_service = EnhancedMemoryService(vector_db_path)
    return _enhanced_memory_service
