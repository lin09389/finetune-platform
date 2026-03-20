"""
RAG 知识�?- 混合检索器
支持向量检索和 BM25 关键词检索的融合
"""
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import logging
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """检索结�?""
    id: str
    content: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)
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
        初始�?BM25 索引
        
        Args:
            k1: BM25 参数 k1，控制词频饱和度
            b: BM25 参数 b，控制文档长度归一�?            language: 语言类型（chinese/english�?        """
        self.k1 = k1
        self.b = b
        self.language = language
        
        self.documents: List[str] = []
        self.doc_ids: List[str] = []
        self.metadatas: List[Dict[str, Any]] = []
        
        self.doc_tokens: List[List[str]] = []
        self.doc_lengths: List[int] = []
        self.avg_doc_length: float = 0.0
        
        self.df: Counter = Counter()
        self.idf: Dict[str, float] = {}
        self.N: int = 0
    
    def _tokenize(self, text: str) -> List[str]:
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
        documents: List[str],
        ids: Optional[List[str]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None
    ):
        """
        添加文档到索�?        
        Args:
            documents: 文档列表
            ids: 文档 ID 列表
            metadatas: 元数据列�?        """
        if ids is None:
            ids = [f"doc_{i}" for i in range(len(documents))]
        
        if metadatas is None:
            metadatas = [{} for _ in range(len(documents))]
        
        self.documents.extend(documents)
        self.doc_ids.extend(ids)
        self.metadatas.extend(metadatas)
        
        for doc in documents:
            tokens = self._tokenize(doc)
            self.doc_tokens.append(tokens)
            self.doc_lengths.append(len(tokens))
            
            unique_tokens = set(tokens)
            for token in unique_tokens:
                self.df[token] += 1
        
        self.N = len(self.documents)
        self.avg_doc_length = sum(self.doc_lengths) / self.N if self.N > 0 else 0
        
        self._compute_idf()
        
        logger.info(f"BM25 索引已构建：{self.N} 个文档，{len(self.df)} 个词�?)
    
    def _compute_idf(self):
        """计算 IDF �?""
        self.idf = {}
        for term, df in self.df.items():
            self.idf[term] = math.log((self.N - df + 0.5) / (df + 0.5) + 1)
    
    def _score_document(self, query_tokens: List[str], doc_idx: int) -> float:
        """
        计算文档�?BM25 分数
        
        Args:
            query_tokens: 查询词元
            doc_idx: 文档索引
            
        Returns:
            BM25 分数
        """
        doc_tokens = self.doc_tokens[doc_idx]
        doc_length = self.doc_lengths[doc_idx]
        
        tf = Counter(doc_tokens)
        
        score = 0.0
        for term in query_tokens:
            if term not in self.idf:
                continue
            
            term_tf = tf.get(term, 0)
            if term_tf == 0:
                continue
            
            idf = self.idf[term]
            
            numerator = term_tf * (self.k1 + 1)
            denominator = term_tf + self.k1 * (
                1 - self.b + self.b * (doc_length / self.avg_doc_length)
            )
            
            score += idf * (numerator / denominator)
        
        return score
    
    def search(
        self,
        query: str,
        top_k: int = 10
    ) -> List[Tuple[int, float]]:
        """
        搜索
        
        Args:
            query: 查询文本
            top_k: 返回数量
            
        Returns:
            (文档索引, 分数) 列表
        """
        query_tokens = self._tokenize(query)
        
        if not query_tokens:
            return []
        
        scores = []
        for i in range(self.N):
            score = self._score_document(query_tokens, i)
            if score > 0:
                scores.append((i, score))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        
        return scores[:top_k]
    
    def save(self, path: str):
        """
        保存索引
        
        Args:
            path: 保存路径
        """
        data = {
            "k1": self.k1,
            "b": self.b,
            "language": self.language,
            "documents": self.documents,
            "doc_ids": self.doc_ids,
            "metadatas": self.metadatas,
            "doc_lengths": self.doc_lengths,
            "avg_doc_length": self.avg_doc_length,
            "df": dict(self.df),
            "idf": self.idf,
            "N": self.N
        }
        
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"BM25 索引已保存：{path}")
    
    def load(self, path: str):
        """
        加载索引
        
        Args:
            path: 索引路径
        """
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.k1 = data["k1"]
        self.b = data["b"]
        self.language = data["language"]
        self.documents = data["documents"]
        self.doc_ids = data["doc_ids"]
        self.metadatas = data["metadatas"]
        self.doc_lengths = data["doc_lengths"]
        self.avg_doc_length = data["avg_doc_length"]
        self.df = Counter(data["df"])
        self.idf = data["idf"]
        self.N = data["N"]
        
        self.doc_tokens = [self._tokenize(doc) for doc in self.documents]
        
        logger.info(f"BM25 索引已加载：{path}，{self.N} 个文�?)


class HybridRetriever:
    """混合检索器"""
    
    def __init__(
        self,
        vector_store: Any,
        embedder: Any,
        bm25_k1: float = 1.5,
        bm25_b: float = 0.75,
        language: str = "chinese",
        vector_weight: float = 0.5,
        keyword_weight: float = 0.5,
        fusion_method: str = "rrf"
    ):
        """
        初始化混合检索器
        
        Args:
            vector_store: 向量存储实例
            embedder: 向量化器实例
            bm25_k1: BM25 参数 k1
            bm25_b: BM25 参数 b
            language: 语言类型
            vector_weight: 向量检索权�?            keyword_weight: 关键词检索权�?            fusion_method: 融合方法（rrf/weighted�?        """
        self.vector_store = vector_store
        self.embedder = embedder
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight
        self.fusion_method = fusion_method
        
        self.bm25_indices: Dict[str, BM25Index] = {}
        self.bm25_k1 = bm25_k1
        self.bm25_b = bm25_b
        self.language = language
        
        self.index_dir = Path("data/bm25_indices")
        self.index_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_bm25_index(self, collection_name: str) -> BM25Index:
        """
        获取或创�?BM25 索引
        
        Args:
            collection_name: 集合名称
            
        Returns:
            BM25 索引
        """
        if collection_name not in self.bm25_indices:
            index = BM25Index(
                k1=self.bm25_k1,
                b=self.bm25_b,
                language=self.language
            )
            
            index_path = self.index_dir / f"{collection_name}.json"
            if index_path.exists():
                index.load(str(index_path))
            
            self.bm25_indices[collection_name] = index
        
        return self.bm25_indices[collection_name]
    
    def build_bm25_index(
        self,
        collection_name: str,
        documents: List[str],
        ids: Optional[List[str]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None
    ):
        """
        构建 BM25 索引
        
        Args:
            collection_name: 集合名称
            documents: 文档列表
            ids: 文档 ID 列表
            metadatas: 元数据列�?        """
        index = BM25Index(
            k1=self.bm25_k1,
            b=self.bm25_b,
            language=self.language
        )
        index.add_documents(documents, ids, metadatas)
        
        index_path = self.index_dir / f"{collection_name}.json"
        index.save(str(index_path))
        
        self.bm25_indices[collection_name] = index
        
        logger.info(f"BM25 索引构建完成：{collection_name}")
    
    def _normalize_scores(self, results: List[Dict[str, Any]], score_key: str = "score") -> List[Dict[str, Any]]:
        """
        归一化分�?        
        Args:
            results: 结果列表
            score_key: 分数字段�?            
        Returns:
            归一化后的结�?        """
        if not results:
            return results
        
        scores = [r[score_key] for r in results]
        min_score = min(scores)
        max_score = max(scores)
        
        if max_score == min_score:
            for r in results:
                r["normalized_score"] = 1.0
        else:
            for r in results:
                r["normalized_score"] = (r[score_key] - min_score) / (max_score - min_score)
        
        return results
    
    def _rrf_fusion(
        self,
        vector_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]],
        k: int = 60
    ) -> List[SearchResult]:
        """
        Reciprocal Rank Fusion 融合
        
        Args:
            vector_results: 向量检索结�?            keyword_results: 关键词检索结�?            k: RRF 参数
            
        Returns:
            融合后的结果
        """
        rrf_scores: Dict[str, float] = {}
        result_map: Dict[str, Dict[str, Any]] = {}
        
        for rank, result in enumerate(vector_results):
            doc_id = result.get("id", result.get("content", "")[:50])
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + self.vector_weight / (k + rank + 1)
            result_map[doc_id] = result
        
        for rank, result in enumerate(keyword_results):
            doc_id = result.get("id", result.get("content", "")[:50])
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + self.keyword_weight / (k + rank + 1)
            if doc_id not in result_map:
                result_map[doc_id] = result
        
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
        
        results = []
        for doc_id in sorted_ids:
            result = result_map[doc_id]
            results.append(SearchResult(
                id=doc_id,
                content=result.get("content", ""),
                score=rrf_scores[doc_id],
                metadata=result.get("metadata", {}),
                vector_score=result.get("vector_score", 0),
                keyword_score=result.get("keyword_score", 0),
                source="hybrid"
            ))
        
        return results
    
    def _weighted_fusion(
        self,
        vector_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]]
    ) -> List[SearchResult]:
        """
        加权融合
        
        Args:
            vector_results: 向量检索结�?            keyword_results: 关键词检索结�?            
        Returns:
            融合后的结果
        """
        vector_results = self._normalize_scores(vector_results)
        keyword_results = self._normalize_scores(keyword_results)
        
        combined_scores: Dict[str, float] = {}
        result_map: Dict[str, Dict[str, Any]] = {}
        
        for result in vector_results:
            doc_id = result.get("id", result.get("content", "")[:50])
            combined_scores[doc_id] = combined_scores.get(doc_id, 0) + \
                self.vector_weight * result.get("normalized_score", 0)
            result_map[doc_id] = {**result, "vector_score": result.get("normalized_score", 0)}
        
        for result in keyword_results:
            doc_id = result.get("id", result.get("content", "")[:50])
            combined_scores[doc_id] = combined_scores.get(doc_id, 0) + \
                self.keyword_weight * result.get("normalized_score", 0)
            if doc_id not in result_map:
                result_map[doc_id] = {**result, "vector_score": 0}
            result_map[doc_id]["keyword_score"] = result.get("normalized_score", 0)
        
        sorted_ids = sorted(combined_scores.keys(), key=lambda x: combined_scores[x], reverse=True)
        
        results = []
        for doc_id in sorted_ids:
            result = result_map[doc_id]
            results.append(SearchResult(
                id=doc_id,
                content=result.get("content", ""),
                score=combined_scores[doc_id],
                metadata=result.get("metadata", {}),
                vector_score=result.get("vector_score", 0),
                keyword_score=result.get("keyword_score", 0),
                source="hybrid"
            ))
        
        return results
    
    def search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 10,
        vector_top_k: Optional[int] = None,
        keyword_top_k: Optional[int] = None,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """
        混合检�?        
        Args:
            collection_name: 集合名称
            query: 查询文本
            top_k: 最终返回数�?            vector_top_k: 向量检索数量（默认�?top_k * 2�?            keyword_top_k: 关键词检索数量（默认�?top_k * 2�?            filter_metadata: 元数据过滤条�?            
        Returns:
            检索结果列�?        """
        vector_top_k = vector_top_k or top_k * 2
        keyword_top_k = keyword_top_k or top_k * 2
        
        vector_results = []
        try:
            query_embedding = self.embedder.embed_single(query)
            raw_results = self.vector_store.search(
                collection_name=collection_name,
                query_embedding=query_embedding,
                top_k=vector_top_k,
                filter_metadata=filter_metadata
            )
            for r in raw_results:
                vector_results.append({
                    "id": r.get("id", r.get("content", "")[:50]),
                    "content": r["content"],
                    "score": r.get("score", 0),
                    "metadata": r.get("metadata", {}),
                    "vector_score": r.get("score", 0),
                    "keyword_score": 0
                })
        except Exception as e:
            logger.warning(f"向量检索失败：{e}")
        
        keyword_results = []
        try:
            bm25_index = self._get_bm25_index(collection_name)
            if bm25_index.N > 0:
                raw_results = bm25_index.search(query, top_k=keyword_top_k)
                for idx, score in raw_results:
                    keyword_results.append({
                        "id": bm25_index.doc_ids[idx],
                        "content": bm25_index.documents[idx],
                        "score": score,
                        "metadata": bm25_index.metadatas[idx],
                        "vector_score": 0,
                        "keyword_score": score
                    })
        except Exception as e:
            logger.warning(f"关键词检索失败：{e}")
        
        if not vector_results and not keyword_results:
            return []
        
        if not vector_results:
            return [
                SearchResult(
                    id=r["id"],
                    content=r["content"],
                    score=r["score"],
                    metadata=r["metadata"],
                    keyword_score=r["keyword_score"],
                    source="keyword"
                )
                for r in keyword_results[:top_k]
            ]
        
        if not keyword_results:
            return [
                SearchResult(
                    id=r["id"],
                    content=r["content"],
                    score=r["score"],
                    metadata=r["metadata"],
                    vector_score=r["vector_score"],
                    source="vector"
                )
                for r in vector_results[:top_k]
            ]
        
        if self.fusion_method == "rrf":
            results = self._rrf_fusion(vector_results, keyword_results)
        else:
            results = self._weighted_fusion(vector_results, keyword_results)
        
        return results[:top_k]
    
    def search_vector_only(
        self,
        collection_name: str,
        query: str,
        top_k: int = 10
    ) -> List[SearchResult]:
        """
        仅向量检�?        
        Args:
            collection_name: 集合名称
            query: 查询文本
            top_k: 返回数量
            
        Returns:
            检索结�?        """
        query_embedding = self.embedder.embed_single(query)
        raw_results = self.vector_store.search(
            collection_name=collection_name,
            query_embedding=query_embedding,
            top_k=top_k
        )
        
        return [
            SearchResult(
                id=r.get("id", r.get("content", "")[:50]),
                content=r["content"],
                score=r.get("score", 0),
                metadata=r.get("metadata", {}),
                vector_score=r.get("score", 0),
                source="vector"
            )
            for r in raw_results
        ]
    
    def search_keyword_only(
        self,
        collection_name: str,
        query: str,
        top_k: int = 10
    ) -> List[SearchResult]:
        """
        仅关键词检�?        
        Args:
            collection_name: 集合名称
            query: 查询文本
            top_k: 返回数量
            
        Returns:
            检索结�?        """
        bm25_index = self._get_bm25_index(collection_name)
        
        if bm25_index.N == 0:
            return []
        
        raw_results = bm25_index.search(query, top_k=top_k)
        
        return [
            SearchResult(
                id=bm25_index.doc_ids[idx],
                content=bm25_index.documents[idx],
                score=score,
                metadata=bm25_index.metadatas[idx],
                keyword_score=score,
                source="keyword"
            )
            for idx, score in raw_results
        ]
    
    def set_weights(self, vector_weight: float, keyword_weight: float):
        """
        设置检索权�?        
        Args:
            vector_weight: 向量检索权�?            keyword_weight: 关键词检索权�?        """
        total = vector_weight + keyword_weight
        self.vector_weight = vector_weight / total
        self.keyword_weight = keyword_weight / total
        
        logger.info(f"权重已更新：向量={self.vector_weight:.2f}，关键词={self.keyword_weight:.2f}")
    
    def set_fusion_method(self, method: str):
        """
        设置融合方法
        
        Args:
            method: 融合方法（rrf/weighted�?        """
        if method not in ["rrf", "weighted"]:
            raise ValueError(f"不支持的融合方法：{method}")
        
        self.fusion_method = method
        logger.info(f"融合方法已更新：{method}")


_hybrid_retriever_instance: Optional[HybridRetriever] = None


def get_hybrid_retriever(
    vector_store: Optional[Any] = None,
    embedder: Optional[Any] = None,
    **kwargs
) -> HybridRetriever:
    """
    获取混合检索器实例
    
    Args:
        vector_store: 向量存储实例
        embedder: 向量化器实例
        **kwargs: 其他参数
        
    Returns:
        混合检索器实例
    """
    global _hybrid_retriever_instance
    
    if _hybrid_retriever_instance is None:
        if vector_store is None:
            from rag.vector_store import get_vector_store
            vector_store = get_vector_store()
        
        if embedder is None:
            from rag.embedder import get_embedder
            embedder = get_embedder()
        
        _hybrid_retriever_instance = HybridRetriever(
            vector_store=vector_store,
            embedder=embedder,
            **kwargs
        )
    
    return _hybrid_retriever_instance


def reset_hybrid_retriever(**kwargs) -> HybridRetriever:
    """重置混合检索器"""
    global _hybrid_retriever_instance
    _hybrid_retriever_instance = None
    return get_hybrid_retriever(**kwargs)
