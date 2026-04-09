"""
RAG 知识库 - 混合检索器
支持向量检索和 BM25 关键词检索的融合
"""
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """检索结果"""
    id: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)
    vector_score: float = 0.0
    keyword_score: float = 0.0
    source: str = "hybrid"


class BM25Index:
    """BM25 索引"""

    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        language: str = "chinese"
    ):
        """
        初始化 BM25 索引

        Args:
            k1: BM25 参数 k1，控制词频饱和度
            b: BM25 参数 b，控制文档长度归一化
            language: 语言类型（chinese/english）
        """
        self.k1 = k1
        self.b = b
        self.language = language

        self.documents: list[str] = []
        self.doc_ids: list[str] = []
        self.metadatas: list[dict[str, Any]] = []

        self.doc_tokens: list[list[str]] = []
        self.doc_lengths: list[int] = []
        self.avg_doc_length: float = 0.0

        self.df: Counter = Counter()
        self.idf: dict[str, float] = {}
        self.N: int = 0

    def _tokenize(self, text: str) -> list[str]:
        """
        分词

        Args:
            text: 输入文本

        Returns:
            词元列表
        """
        text = text.lower()

        if self.language == "chinese":
            try:
                import jieba
                tokens = list(jieba.cut(text))
                tokens = [t.strip() for t in tokens if t.strip() and len(t.strip()) > 1]
            except ImportError:
                tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', text)
                tokens = [t for t in tokens if len(t) > 1]
        else:
            tokens = re.findall(r'\b\w+\b', text)
            tokens = [t for t in tokens if len(t) > 1]

        return tokens

    def add_documents(
        self,
        documents: list[str],
        ids: list[str] | None = None,
        metadatas: list[dict[str, Any]] | None = None
    ):
        """
        添加文档到索引

        Args:
            documents: 文档列表
            ids: 文档 ID 列表
            metadatas: 元数据列表
        """
        if ids is None:
            ids = [f"doc_{i}" for i in range(len(documents))]

        if metadatas is None:
            metadatas = [{}] * len(documents)

        self.documents.extend(documents)
        self.doc_ids.extend(ids)
        self.metadatas.extend(metadatas)

        for doc in documents:
            tokens = self._tokenize(doc)
            self.doc_tokens.append(tokens)
            self.doc_lengths.append(len(tokens))
            self.df.update(set(tokens))

        self.N = len(self.documents)
        self.avg_doc_length = sum(self.doc_lengths) / self.N if self.N > 0 else 0

        for term, df in self.df.items():
            self.idf[term] = math.log((self.N - df + 0.5) / (df + 0.5) + 1)

        logger.info(f"BM25 索引已构建：{self.N} 个文档")

    def search(self, query: str, top_k: int = 10) -> list[SearchResult]:
        """
        搜索

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            搜索结果列表
        """
        query_tokens = self._tokenize(query)
        scores = []

        for i, doc_tokens in enumerate(self.doc_tokens):
            score = 0.0
            doc_len = self.doc_lengths[i]

            for term in query_tokens:
                if term not in self.idf:
                    continue

                tf = doc_tokens.count(term)
                idf = self.idf[term]

                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avg_doc_length)

                score += idf * numerator / denominator

            scores.append((i, score))

        scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for i, score in scores[:top_k]:
            results.append(SearchResult(
                id=self.doc_ids[i],
                content=self.documents[i],
                score=score,
                metadata=self.metadatas[i],
                keyword_score=score,
                source="bm25"
            ))

        return results


class HybridRetriever:
    """混合检索器"""

    def __init__(
        self,
        vector_weight: float = 0.5,
        keyword_weight: float = 0.5,
        language: str = "chinese"
    ):
        """
        初始化混合检索器

        Args:
            vector_weight: 向量检索权重
            keyword_weight: 关键词检索权重
            language: 语言类型
        """
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight
        self.language = language

        self.bm25_index = BM25Index(language=language)
        self.vector_store = None
        self.embedder = None

    def set_vector_store(self, vector_store):
        """设置向量存储"""
        self.vector_store = vector_store

    def set_embedder(self, embedder):
        """设置嵌入器"""
        self.embedder = embedder

    def add_documents(
        self,
        documents: list[str],
        ids: list[str] | None = None,
        metadatas: list[dict[str, Any]] | None = None
    ):
        """添加文档"""
        self.bm25_index.add_documents(documents, ids, metadatas)

    def search(
        self,
        query: str,
        collection_name: str = "default",
        top_k: int = 10
    ) -> list[SearchResult]:
        """
        混合搜索

        Args:
            query: 查询文本
            collection_name: 集合名称
            top_k: 返回结果数量

        Returns:
            搜索结果列表
        """
        keyword_results = self.bm25_index.search(query, top_k * 2)

        vector_results = []
        if self.vector_store and self.embedder:
            query_embedding = self.embedder.embed_single(query)
            vector_results = self.vector_store.search(
                collection_name=collection_name,
                query_embedding=query_embedding,
                top_k=top_k * 2
            )

        merged = {}

        for result in keyword_results:
            if result.id not in merged:
                merged[result.id] = result
            merged[result.id].keyword_score = result.score

        for result in vector_results:
            doc_id = result.get("id", result.get("content", "")[:50])
            if doc_id not in merged:
                merged[doc_id] = SearchResult(
                    id=doc_id,
                    content=result.get("content", ""),
                    score=0.0,
                    metadata=result.get("metadata", {})
                )
            merged[doc_id].vector_score = result.get("score", 0.0)

        max_keyword = max((r.keyword_score for r in merged.values()), default=1.0) or 1.0
        max_vector = max((r.vector_score for r in merged.values()), default=1.0) or 1.0

        for result in merged.values():
            normalized_keyword = result.keyword_score / max_keyword
            normalized_vector = result.vector_score / max_vector
            result.score = (
                self.keyword_weight * normalized_keyword +
                self.vector_weight * normalized_vector
            )

        results = sorted(merged.values(), key=lambda x: x.score, reverse=True)

        return results[:top_k]


_hybrid_retriever: HybridRetriever | None = None


def get_hybrid_retriever(
    vector_weight: float = 0.5,
    keyword_weight: float = 0.5,
    language: str = "chinese"
) -> HybridRetriever:
    """获取混合检索器实例"""
    global _hybrid_retriever
    if _hybrid_retriever is None:
        _hybrid_retriever = HybridRetriever(vector_weight, keyword_weight, language)
    return _hybrid_retriever


def reset_hybrid_retriever():
    """重置混合检索器"""
    global _hybrid_retriever
    _hybrid_retriever = None
