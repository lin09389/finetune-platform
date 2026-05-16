"""
统一上下文管理器 - 整合记忆系统、知识库和项目上下文
实现协同检索、智能融合和会话级缓存
"""
import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ContextOptions:
    """上下文检索配置"""
    use_memory: bool = True
    use_knowledge: bool = False
    use_project_context: bool = False

    memory_top_k: int = 3
    memory_auto_extract: bool = True
    memory_include_types: list[str] | None = None

    knowledge_collection_id: str | None = None
    knowledge_top_k: int = 5
    knowledge_auto_retrieve: bool = True

    project_path: str | None = None
    project_max_length: int = 2000

    max_context_length: int = 4000
    max_total_sources: int = 10


@dataclass
class MemorySource:
    """记忆来源"""
    id: str
    content: str
    source_type: str  # short_term / long_term / knowledge_graph
    memory_type: str | None = None
    relevance: float = 0.0
    importance: float = 0.5
    created_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeSourceItem:
    """知识库来源"""
    id: str
    content: str
    source: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectContextItem:
    """项目上下文项"""
    content: str
    source_type: str  # file / symbol / project_info
    path: str | None = None
    relevance: float = 0.0


@dataclass
class UnifiedContext:
    """统一上下文结果"""
    memory_sources: list[MemorySource] = field(default_factory=list)
    knowledge_sources: list[KnowledgeSourceItem] = field(default_factory=list)
    project_contexts: list[ProjectContextItem] = field(default_factory=list)

    system_prompt: str = ""
    context_text: str = ""

    retrieval_time: float = 0.0
    memory_retrieval_time: float = 0.0
    knowledge_retrieval_time: float = 0.0
    project_retrieval_time: float = 0.0

    total_sources: int = 0
    memory_count: int = 0
    knowledge_count: int = 0
    project_count: int = 0

    def build_system_prompt(self, base_prompt: str = "") -> str:
        """构建增强的系统提示词"""
        parts = []

        if base_prompt:
            parts.append(base_prompt)

        context_sections = []

        if self.memory_sources:
            memory_text = self._format_memory_context()
            context_sections.append(f"【用户记忆】\n{memory_text}")

        if self.knowledge_sources:
            knowledge_text = self._format_knowledge_context()
            context_sections.append(f"【参考资料】\n{knowledge_text}")

        if self.project_contexts:
            project_text = self._format_project_context()
            context_sections.append(f"【项目上下文】\n{project_text}")

        if context_sections:
            parts.append("\n\n" + "\n\n".join(context_sections))
            parts.append("\n\n请根据以上上下文信息回答用户问题。如果引用具体内容，请标注来源。")

        return "\n".join(parts)

    def _format_memory_context(self) -> str:
        """格式化记忆上下文"""
        lines = []
        for i, mem in enumerate(self.memory_sources[:5], 1):
            content_preview = mem.content[:200] + "..." if len(mem.content) > 200 else mem.content
            lines.append(f"{i}. [{mem.source_type}] {content_preview}")
        return "\n".join(lines)

    def _format_knowledge_context(self) -> str:
        """格式化知识库上下文"""
        lines = []
        for i, k in enumerate(self.knowledge_sources, 1):
            content_preview = k.content[:300] + "..." if len(k.content) > 300 else k.content
            lines.append(f"[参考资料 {i}]\n来源: {k.source}\n内容: {content_preview}")
        return "\n\n".join(lines)

    def _format_project_context(self) -> str:
        """格式化项目上下文"""
        lines = []
        for ctx in self.project_contexts[:3]:
            if ctx.path:
                lines.append(f"- {ctx.path}: {ctx.content[:100]}...")
            else:
                lines.append(f"- {ctx.content[:150]}...")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "memory_sources": [
                {
                    "id": m.id,
                    "content": m.content[:100] + "..." if len(m.content) > 100 else m.content,
                    "source_type": m.source_type,
                    "relevance": m.relevance
                }
                for m in self.memory_sources
            ],
            "knowledge_sources": [
                {
                    "id": k.id,
                    "source": k.source,
                    "score": k.score,
                    "content_preview": k.content[:100] + "..." if len(k.content) > 100 else k.content
                }
                for k in self.knowledge_sources
            ],
            "project_contexts": [
                {
                    "source_type": p.source_type,
                    "path": p.path,
                    "content_preview": p.content[:100] + "..." if len(p.content) > 100 else p.content
                }
                for p in self.project_contexts
            ],
            "retrieval_time": self.retrieval_time,
            "total_sources": self.total_sources,
            "memory_count": self.memory_count,
            "knowledge_count": self.knowledge_count,
            "project_count": self.project_count
        }


class ContextCache:
    """会话级上下文缓存"""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self._cache: dict[str, tuple[UnifiedContext, float]] = {}
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds

    def _make_key(self, query: str, user_id: str, session_id: str, options: ContextOptions) -> str:
        """生成缓存键"""
        key_data = (
            f"{query}:{user_id}:{session_id}:"
            f"{options.use_memory}:{options.use_knowledge}:{options.knowledge_collection_id}:"
            f"{options.use_project_context}:{options.project_path}"
        )
        return hashlib.md5(key_data.encode()).hexdigest()

    def get(self, query: str, user_id: str, session_id: str, options: ContextOptions) -> UnifiedContext | None:
        """获取缓存的上下文"""
        key = self._make_key(query, user_id, session_id, options)
        if key in self._cache:
            context, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl_seconds:
                return context
            else:
                del self._cache[key]
        return None

    def set(self, query: str, user_id: str, session_id: str, options: ContextOptions, context: UnifiedContext):
        """设置缓存"""
        if len(self._cache) >= self._max_size:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]

        key = self._make_key(query, user_id, session_id, options)
        self._cache[key] = (context, time.time())

    def clear_session(self, session_id: str):
        """清除会话相关的缓存"""
        keys_to_remove = [k for k in self._cache if session_id in str(k)]
        for key in keys_to_remove:
            del self._cache[key]

    def clear_all(self):
        """清空所有缓存"""
        self._cache.clear()


class UnifiedContextManager:
    """统一上下文管理器"""

    def __init__(self):
        self._memory_service = None
        self._knowledge_integrator = None
        self._context_service = None
        self._cache = ContextCache()

    def _get_memory_service(self):
        """获取记忆服务"""
        if self._memory_service is None:
            from memory.enhanced_memory_service import EnhancedMemoryService
            self._memory_service = EnhancedMemoryService()
        return self._memory_service

    def _get_knowledge_integrator(self):
        """获取知识库集成器"""
        if self._knowledge_integrator is None:
            from context.knowledge_integration import get_knowledge_integrator
            self._knowledge_integrator = get_knowledge_integrator()
        return self._knowledge_integrator

    def _get_context_service(self):
        """获取项目上下文服务"""
        if self._context_service is None:
            from context.service import get_context_service
            from rag.embedder import get_embedder
            from rag.vector_store import get_vector_store

            try:
                embedder = get_embedder()
                vector_store = get_vector_store()
            except Exception as e:
                logger.error(f"项目上下文依赖初始化失败（嵌入器/向量存储）: {e}")
                self._context_service = False
                return None

            try:
                self._context_service = get_context_service(embedder=embedder, vector_store=vector_store)
            except Exception as e:
                logger.error(f"项目上下文服务初始化失败: {e}")
                self._context_service = False

        if self._context_service is False:
            return None
        return self._context_service

    async def build_context(
        self,
        query: str,
        user_id: str = "default",
        session_id: str | None = None,
        options: ContextOptions | None = None
    ) -> UnifiedContext:
        """
        构建统一上下文

        Args:
            query: 用户查询
            user_id: 用户ID
            session_id: 会话ID
            options: 上下文配置

        Returns:
            统一上下文结果
        """
        start_time = time.time()
        options = options or ContextOptions()
        session_id = session_id or "default"

        cached = self._cache.get(query, user_id, session_id, options)
        if cached:
            logger.debug(f"使用缓存的上下文: {session_id}")
            return cached

        context = UnifiedContext()

        tasks = []
        task_names = []

        if options.use_memory:
            tasks.append(self._retrieve_memory(query, user_id, session_id, options))
            task_names.append("memory")

        if options.use_knowledge and options.knowledge_collection_id:
            tasks.append(self._retrieve_knowledge(query, options))
            task_names.append("knowledge")

        if options.use_project_context and options.project_path:
            tasks.append(self._retrieve_project_context(query, options))
            task_names.append("project")

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for name, result in zip(task_names, results, strict=False):
                if isinstance(result, Exception):
                    logger.warning(f"{name} 检索失败: {result}")
                    continue

                if name == "memory":
                    context.memory_sources = result.get("sources", [])
                    context.memory_retrieval_time = result.get("time", 0)
                    context.memory_count = len(context.memory_sources)

                elif name == "knowledge":
                    context.knowledge_sources = result.get("sources", [])
                    context.knowledge_retrieval_time = result.get("time", 0)
                    context.knowledge_count = len(context.knowledge_sources)

                elif name == "project":
                    context.project_contexts = result.get("sources", [])
                    context.project_retrieval_time = result.get("time", 0)
                    context.project_count = len(context.project_contexts)

        context.total_sources = context.memory_count + context.knowledge_count + context.project_count
        context.retrieval_time = time.time() - start_time

        context.context_text = self._merge_and_deduplicate(context, options)

        self._cache.set(query, user_id, session_id, options, context)

        logger.info(
            f"上下文构建完成: memory={context.memory_count}, "
            f"knowledge={context.knowledge_count}, project={context.project_count}, "
            f"time={context.retrieval_time:.3f}s"
        )

        return context

    async def _retrieve_memory(
        self,
        query: str,
        user_id: str,
        session_id: str,
        options: ContextOptions
    ) -> dict[str, Any]:
        """检索记忆"""
        start_time = time.time()
        sources = []

        try:
            memory_service = self._get_memory_service()
            memory_service.set_session(session_id=session_id, user_id=user_id)

            memories = await memory_service.recall(
                query=query,
                session_id=session_id,
                top_k=options.memory_top_k,
                memory_type=options.memory_include_types[0] if options.memory_include_types else None
            )

            for mem in memories:
                sources.append(MemorySource(
                    id=mem.get("id", ""),
                    content=mem.get("content", ""),
                    source_type=mem.get("source", "long_term_memory"),
                    memory_type=mem.get("type"),
                    relevance=mem.get("relevance", 0.5),
                    importance=mem.get("importance", 0.5),
                    created_at=mem.get("created_at"),
                    metadata=mem.get("metadata", {})
                ))

        except Exception as e:
            logger.warning(f"记忆检索失败: {e}")

        return {
            "sources": sources,
            "time": time.time() - start_time
        }

    async def _retrieve_knowledge(
        self,
        query: str,
        options: ContextOptions
    ) -> dict[str, Any]:
        """检索知识库"""
        start_time = time.time()
        sources = []

        try:
            integrator = self._get_knowledge_integrator()

            should_retrieve, reason = integrator.should_retrieve_knowledge(
                query=query,
                collection_id=options.knowledge_collection_id,
                force_retrieve=not options.knowledge_auto_retrieve
            )

            if should_retrieve:
                result = integrator.retrieve_knowledge(
                    query=query,
                    collection_id=options.knowledge_collection_id,
                    top_k=options.knowledge_top_k
                )

                for source in result.sources:
                    sources.append(KnowledgeSourceItem(
                        id=source.id,
                        content=source.content,
                        source=source.source,
                        score=source.score,
                        metadata=source.metadata
                    ))

                logger.debug(f"知识库检索: {reason}, 结果数={len(sources)}")
            else:
                logger.debug(f"知识库检索跳过: {reason}")

        except Exception as e:
            logger.warning(f"知识库检索失败: {e}")

        return {
            "sources": sources,
            "time": time.time() - start_time
        }

    async def _retrieve_project_context(
        self,
        query: str,
        options: ContextOptions
    ) -> dict[str, Any]:
        """检索项目上下文"""
        start_time = time.time()
        sources = []

        try:
            if not options.project_path:
                logger.warning("项目上下文检索跳过: project_path 为空，请先扫描并设置项目路径")
                return {"sources": sources, "time": time.time() - start_time}

            context_service = self._get_context_service()

            if context_service is None:
                logger.warning("项目上下文检索跳过: 上下文服务不可用（向量存储或嵌入器初始化失败）")
                return {"sources": sources, "time": time.time() - start_time}

            context_text = context_service.get_context_for_chat(
                query=query,
                project_path=options.project_path,
                max_length=options.project_max_length
            )

            if context_text:
                sources.append(ProjectContextItem(
                    content=context_text,
                    source_type="project_info",
                    relevance=0.8
                ))
            else:
                logger.debug(f"项目上下文检索无结果: project_path={options.project_path}, query={query[:50]}")

        except Exception as e:
            logger.warning(f"项目上下文检索失败: {e}")

        return {
            "sources": sources,
            "time": time.time() - start_time
        }

    def _merge_and_deduplicate(
        self,
        context: UnifiedContext,
        options: ContextOptions
    ) -> str:
        """合并和去重上下文"""
        all_items = []

        for mem in context.memory_sources:
            all_items.append({
                "type": "memory",
                "content": mem.content,
                "relevance": mem.relevance,
                "importance": mem.importance
            })

        for k in context.knowledge_sources:
            all_items.append({
                "type": "knowledge",
                "content": k.content,
                "relevance": k.score,
                "importance": 0.7
            })

        for p in context.project_contexts:
            all_items.append({
                "type": "project",
                "content": p.content,
                "relevance": p.relevance,
                "importance": 0.6
            })

        all_items.sort(key=lambda x: x["relevance"] * x["importance"], reverse=True)

        seen_contents = set()
        unique_items = []
        for item in all_items:
            content_hash = hashlib.md5(item["content"][:100].encode()).hexdigest()
            if content_hash not in seen_contents:
                seen_contents.add(content_hash)
                unique_items.append(item)

        unique_items = unique_items[:options.max_total_sources]

        parts = []
        total_length = 0

        for item in unique_items:
            content = item["content"]
            if total_length + len(content) > options.max_context_length:
                content = content[:options.max_context_length - total_length]

            if item["type"] == "memory":
                parts.append(f"[记忆] {content}")
            elif item["type"] == "knowledge":
                parts.append(f"[知识] {content}")
            else:
                parts.append(f"[项目] {content}")

            total_length += len(content)
            if total_length >= options.max_context_length:
                break

        return "\n\n".join(parts)

    async def extract_and_store_memory(
        self,
        message: str,
        role: str,
        user_id: str = "default",
        session_id: str | None = None
    ) -> dict[str, Any]:
        """
        从消息中提取并存储记忆

        Args:
            message: 消息内容
            role: 角色 (user/assistant)
            user_id: 用户ID
            session_id: 会话ID

        Returns:
            提取结果
        """
        try:
            memory_service = self._get_memory_service()
            memory_service.set_session(session_id=session_id or "default", user_id=user_id)

            result = await memory_service.process_message(
                message=message,
                role=role,
                extract=True
            )

            self._cache.clear_session(session_id or "default")

            return result

        except Exception as e:
            logger.warning(f"记忆提取失败: {e}")
            return {"extracted": 0, "error": str(e)}

    def clear_cache(self, session_id: str | None = None):
        """清除缓存"""
        if session_id:
            self._cache.clear_session(session_id)
        else:
            self._cache.clear_all()


_manager_instance: UnifiedContextManager | None = None


def get_unified_context_manager() -> UnifiedContextManager:
    """获取统一上下文管理器实例"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = UnifiedContextManager()
    return _manager_instance
