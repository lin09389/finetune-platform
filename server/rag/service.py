"""
RAG 知识库 - 服务层
整合文档解析、分块、向量化和存储
支持向量检索降级到关键词检索
"""
import logging
import re
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from rag.document_parser import get_parser
from rag.embedder import get_embedder
from rag.text_chunker import get_chunker
from rag.vector_store import get_vector_store

logger = logging.getLogger(__name__)


class SearchMode(str, Enum):
    VECTOR = "vector"
    KEYWORD = "keyword"
    HYBRID = "hybrid"
    FALLBACK = "fallback"


class RAGService:
    """RAG 服务，支持降级策略"""

    def __init__(
        self,
        vector_db_path: str = "data/vectors",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        embedder_model: str = "shibing624/text2vec-base-chinese",
        fallback_threshold: int = 3
    ):
        """
        初始化 RAG 服务

        Args:
            vector_db_path: 向量数据库路径
            chunk_size: 分块大小
            chunk_overlap: 分块重叠
            embedder_model: 嵌入模型
            fallback_threshold: 连续失败次数阈值，超过后自动降级
        """
        self._parser = None
        self._chunker = None
        self._embedder = None
        self._vector_store = None
        self._keyword_index: dict[str, list[dict]] = {}

        self._vector_db_path = vector_db_path
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._embedder_model = embedder_model
        self._fallback_threshold = fallback_threshold

        self._search_failures = 0
        self._last_failure_time = 0

        self.docs_dir = Path("data/documents")
        self.docs_dir.mkdir(parents=True, exist_ok=True)

    @property
    def parser(self):
        """延迟加载解析器"""
        if self._parser is None:
            self._parser = get_parser()
        return self._parser

    @property
    def chunker(self):
        """延迟加载分块器"""
        if self._chunker is None:
            self._chunker = get_chunker(self._chunk_size, self._chunk_overlap)
        return self._chunker

    @property
    def embedder(self):
        """延迟加载嵌入器"""
        if self._embedder is None:
            self._embedder = get_embedder(self._embedder_model)
        return self._embedder

    @property
    def vector_store(self):
        """延迟加载向量存储"""
        if self._vector_store is None:
            self._vector_store = get_vector_store(self._vector_db_path)
        return self._vector_store

    def upload_document(
        self,
        file_path: str,
        collection_name: str,
        metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        上传文档到知识库

        Args:
            file_path: 文件路径
            collection_name: 集合名称（工作空间 ID）
            metadata: 元数据

        Returns:
            处理结果
        """
        logger.info(f"开始处理文档：{file_path}")

        content = self.parser.parse(file_path)
        if not content:
            raise ValueError(f"文档解析失败：{file_path}")

        logger.info(f"文档解析完成：{len(content)} 字符")

        original_filename = metadata.get("original_filename") if metadata else None
        file_name = original_filename or Path(file_path).name
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        dest_path = self.docs_dir / f"{doc_id}_{file_name}"

        try:
            Path(file_path).rename(dest_path)
        except Exception:
            import shutil
            shutil.copy2(file_path, dest_path)

        chunks = self.chunker.chunk(content, metadata)
        logger.info(f"文本分块完成：{len(chunks)} 块")

        if not chunks:
            raise ValueError("文本分块后为空")

        chunk_texts = [chunk.content for chunk in chunks]
        embeddings = self.embedder.embed_chunks(chunk_texts)
        logger.info(f"向量化完成：{len(embeddings)} 向量")

        doc_metadatas = []
        for i, chunk in enumerate(chunks):
            doc_meta = {
                "source": file_name,
                "doc_id": doc_id,
                "chunk_index": i,
                "start_index": chunk.start_index,
                "end_index": chunk.end_index,
                "uploaded_at": datetime.now().isoformat(),
                **(metadata or {})
            }
            doc_metadatas.append(doc_meta)

        ids = self.vector_store.add_documents(
            collection_name=collection_name,
            documents=chunk_texts,
            embeddings=embeddings,
            metadatas=doc_metadatas
        )

        logger.info(f"文档已存储到知识库：{len(ids)} 个向量")

        return {
            "doc_id": doc_id,
            "file_name": file_name,
            "chunk_count": len(chunks),
            "vector_count": len(ids),
            "content_length": len(content),
            "file_path": str(dest_path)
        }

    def search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
        mode: SearchMode = SearchMode.HYBRID
    ) -> list[dict[str, Any]]:
        """
        搜索相关文档，支持降级策略

        Args:
            collection_name: 集合名称
            query: 查询文本
            top_k: 返回数量
            mode: 搜索模式 (vector/keyword/hybrid/fallback)

        Returns:
            搜索结果
        """
        import time
        now = time.time()

        if mode == SearchMode.FALLBACK or self._search_failures >= self._fallback_threshold:
            if self._search_failures >= self._fallback_threshold:
                logger.warning(f"向量检索连续失败 {self._search_failures} 次，使用关键词检索降级")
            return self._keyword_search(collection_name, query, top_k)

        if mode == SearchMode.KEYWORD:
            return self._keyword_search(collection_name, query, top_k)

        try:
            if mode == SearchMode.VECTOR:
                results = self._vector_search(collection_name, query, top_k)
            else:
                results = self._hybrid_search(collection_name, query, top_k)

            self._search_failures = 0
            return results

        except Exception as e:
            logger.warning(f"向量检索失败，降级到关键词检索: {e}")
            self._search_failures += 1
            self._last_failure_time = now
            return self._keyword_search(collection_name, query, top_k)

    def _vector_search(
        self,
        collection_name: str,
        query: str,
        top_k: int
    ) -> list[dict[str, Any]]:
        """向量检索"""
        logger.info(f"向量搜索：{query} (top_k={top_k})")

        query_embedding = self.embedder.embed_single(query)

        results = self.vector_store.search(
            collection_name=collection_name,
            query_embedding=query_embedding,
            top_k=top_k
        )

        logger.info(f"向量搜索完成：{len(results)} 个结果")
        return results

    def _keyword_search(
        self,
        collection_name: str,
        query: str,
        top_k: int
    ) -> list[dict[str, Any]]:
        """关键词检索（BM25风格）"""
        logger.info(f"关键词搜索：{query} (top_k={top_k})")

        keywords = self._extract_keywords(query)
        if not keywords:
            return []

        collection_docs = self._keyword_index.get(collection_name, [])
        if not collection_docs:
            try:
                collection_docs = self._build_keyword_index(collection_name)
            except Exception as e:
                logger.warning(f"构建关键词索引失败: {e}")
                return []

        scored_docs = []
        for doc in collection_docs:
            score = self._calculate_keyword_score(doc.get("content", ""), keywords)
            if score > 0:
                scored_docs.append({**doc, "score": score, "source": "keyword"})

        scored_docs.sort(key=lambda x: x["score"], reverse=True)
        results = scored_docs[:top_k]

        logger.info(f"关键词搜索完成：{len(results)} 个结果")
        return results

    def _hybrid_search(
        self,
        collection_name: str,
        query: str,
        top_k: int
    ) -> list[dict[str, Any]]:
        """混合检索：向量 + 关键词"""
        try:
            vector_results = self._vector_search(collection_name, query, top_k)
            keyword_results = self._keyword_search(collection_name, query, top_k)

            merged = {}
            for r in vector_results:
                key = r.get("id", r.get("content", "")[:50])
                merged[key] = r
                merged[key]["vector_score"] = r.get("score", 0)
                merged[key]["score"] = r.get("score", 0) * 0.7

            for r in keyword_results:
                key = r.get("id", r.get("content", "")[:50])
                if key in merged:
                    merged[key]["keyword_score"] = r.get("score", 0)
                    merged[key]["score"] += r.get("score", 0) * 0.3
                else:
                    merged[key] = r
                    merged[key]["keyword_score"] = r.get("score", 0)
                    merged[key]["score"] = r.get("score", 0) * 0.3

            results = sorted(merged.values(), key=lambda x: x["score"], reverse=True)[:top_k]
            return results

        except Exception as e:
            logger.warning(f"混合检索失败，使用纯向量检索: {e}")
            return self._vector_search(collection_name, query, top_k)

    def _extract_keywords(self, text: str) -> list[str]:
        """提取关键词"""
        text = text.lower()
        words = re.findall(r'\b\w+\b', text)
        stop_words = {'的', '是', '在', '和', '了', '有', '我', '不', '这', '个',
                      'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                      'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                      'would', 'could', 'should', 'may', 'might', 'must', 'shall'}
        keywords = [w for w in words if w not in stop_words and len(w) > 1]
        return keywords

    def _calculate_keyword_score(self, content: str, keywords: list[str]) -> float:
        """计算关键词匹配分数"""
        if not content or not keywords:
            return 0.0

        content_lower = content.lower()
        score = 0.0

        for keyword in keywords:
            count = content_lower.count(keyword)
            if count > 0:
                score += count * (1.0 / len(keywords))

        return min(score, 1.0)

    def _build_keyword_index(self, collection_name: str) -> list[dict]:
        """构建关键词索引"""
        try:
            collection = self.vector_store.get_collection(collection_name)
            if not collection:
                return []

            docs = []
            results = collection.get(include=["documents", "metadatas"])

            for i, doc in enumerate(results.get("documents", [])):
                docs.append({
                    "id": results["ids"][i] if "ids" in results else f"doc_{i}",
                    "content": doc,
                    "metadata": results.get("metadatas", [{}])[i] if results.get("metadatas") else {}
                })

            self._keyword_index[collection_name] = docs
            logger.info(f"关键词索引构建完成：{collection_name} ({len(docs)} 文档)")
            return docs

        except Exception as e:
            logger.error(f"构建关键词索引失败: {e}")
            return []

    def reset_failures(self):
        """重置失败计数"""
        self._search_failures = 0

    def search_with_context(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5
    ) -> str:
        """
        搜索并组装上下文

        Args:
            collection_name: 集合名称
            query: 查询文本
            top_k: 返回数量

        Returns:
            组装的上下文文本
        """
        results = self.search(collection_name, query, top_k)

        if not results:
            return ""

        context_parts = []
        for i, result in enumerate(results):
            part = f"[相关片段 {i+1}]: {result['content']}"
            context_parts.append(part)

        return "\n\n".join(context_parts)

    def delete_document(
        self,
        collection_name: str,
        doc_id: str
    ) -> bool:
        """
        删除文档

        Args:
            collection_name: 集合名称
            doc_id: 文档 ID

        Returns:
            是否成功
        """
        try:
            self.vector_store.delete_documents(collection_name, [doc_id])
            logger.info(f"删除文档：{doc_id}, 集合：{collection_name}")

            return True
        except Exception as e:
            logger.error(f"删除文档失败：{e}")
            return False

    def get_collection_info(self, collection_name: str) -> dict[str, Any]:
        """
        获取集合信息

        Args:
            collection_name: 集合名称

        Returns:
            集合信息
        """
        return self.vector_store.get_collection_stats(collection_name)

    def list_documents(
        self,
        collection_name: str,
        limit: int = 50,
        offset: int = 0
    ) -> list[dict[str, Any]]:
        """
        列出集合中的所有文档

        Args:
            collection_name: 集合名称
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            文档列表
        """
        try:
            collection = self.vector_store.get_or_create_collection(collection_name)

            all_data = collection.get(include=["metadatas"])

            doc_map = {}
            if all_data['metadatas']:
                for i, meta in enumerate(all_data['metadatas']):
                    doc_id = meta.get('doc_id', f'unknown_{i}')
                    if doc_id not in doc_map:
                        doc_map[doc_id] = {
                            "doc_id": doc_id,
                            "source": meta.get('source', 'unknown'),
                            "chunk_count": 0,
                            "uploaded_at": meta.get('uploaded_at', '')
                        }
                    doc_map[doc_id]["chunk_count"] += 1

            docs = list(doc_map.values())
            return docs[offset:offset + limit]
        except Exception as e:
            logger.error(f"列出文档失败: {e}")
            return []

    def list_collections(self) -> list[dict[str, Any]]:
        """
        列出所有集合

        Returns:
            集合列表
        """
        try:
            collection_names = self.vector_store.list_collections()
            collections = []

            for name in collection_names:
                try:
                    stats = self.vector_store.get_collection_stats(name)
                    collections.append({
                        "id": name,
                        "name": name,
                        "document_count": stats.get("count", 0),
                        "created_at": "",
                        "metadata": {}
                    })
                except Exception as e:
                    logger.warning(f"获取集合 {name} 信息失败: {e}")
                    collections.append({
                        "id": name,
                        "name": name,
                        "document_count": 0,
                        "created_at": "",
                        "metadata": {}
                    })

            return collections
        except Exception as e:
            logger.error(f"列出集合失败: {e}")
            return []

    def create_collection(
        self,
        name: str,
        metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        创建集合

        Args:
            name: 集合名称
            metadata: 元数据

        Returns:
            集合信息
        """
        self.vector_store.get_or_create_collection(name)
        return {
            "id": name,
            "name": name,
            "document_count": 0,
            "metadata": metadata or {}
        }

    def delete_collection(self, collection_name: str) -> bool:
        """
        删除集合

        Args:
            collection_name: 集合名称

        Returns:
            是否成功
        """
        try:
            self.vector_store.delete_collection(collection_name)
            return True
        except Exception as e:
            logger.error(f"删除集合失败: {e}")
            return False


_service_instance: RAGService | None = None


def get_rag_service() -> RAGService:
    """获取 RAG 服务实例"""
    global _service_instance
    if _service_instance is None:
        _service_instance = RAGService()
    return _service_instance


def reset_rag_service(config: dict[str, Any]) -> RAGService:
    """重置 RAG 服务"""
    global _service_instance
    _service_instance = RAGService(**config)
    return _service_instance
