"""
RAG 知识�?- 重排序器
使用 Cross-Encoder 对检索结果进行重排序
"""
from typing import List, Dict, Any, Optional, Tuple
import logging
from dataclasses import dataclass, field
import asyncio
from concurrent.futures import ThreadPoolExecutor
import os

logger = logging.getLogger(__name__)


def _setup_hf_mirror():
    """配置 HuggingFace 镜像源（解决国内访问问题�?""
    from core.config import get_settings
    
    settings = get_settings()
    hf_mirror = settings.hf_mirror
    
    mirrors = {
        "hf-mirror": "https://hf-mirror.com",
        "aliyun": "https://mirrors.aliyun.com/huggingface",
        "modelscope": "https://modelscope.cn/models",
    }
    
    if hf_mirror in mirrors:
        endpoint = mirrors[hf_mirror]
        os.environ["HF_ENDPOINT"] = endpoint
        logger.info(f"已配�?HuggingFace 镜像�? {endpoint}")


@dataclass
class RerankResult:
    """重排序结�?""
    id: str
    content: str
    score: float
    original_score: float
    original_rank: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class CrossEncoderReranker:
    """Cross-Encoder 重排序器"""
    
    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        device: Optional[str] = None,
        max_length: int = 512,
        batch_size: int = 32
    ):
        """
        初始化重排序�?        
        Args:
            model_name: Cross-Encoder 模型名称
                - 中文：cross-encoder/ms-marco-MiniLM-L-6-v2
                - 中文推荐：BAAI/bge-reranker-base
                - 英文：cross-encoder/ms-marco-MiniLM-L-6-v2
            device: 设备（cuda/cpu�?            max_length: 最大序列长�?            batch_size: 批次大小
        """
        self.model_name = model_name
        self.device = device
        self.max_length = max_length
        self.batch_size = batch_size
        
        self.model = None
        self.tokenizer = None
        self._executor = ThreadPoolExecutor(max_workers=1)
    
    def _load_model(self):
        """懒加载模�?""
        if self.model is None:
            _setup_hf_mirror()
            logger.info(f"加载 Cross-Encoder 模型：{self.model_name}")
            
            try:
                from sentence_transformers import CrossEncoder
                self.model = CrossEncoder(
                    self.model_name,
                    max_length=self.max_length
                )
                
                if self.device:
                    self.model.model.to(self.device)
                
                logger.info("Cross-Encoder 模型加载完成")
            except ImportError:
                logger.warning("sentence-transformers 未安装，使用备用重排序方�?)
                self.model = None
            except Exception as e:
                logger.error(f"加载 Cross-Encoder 模型失败：{e}")
                self.model = None
    
    def _compute_similarity_fallback(
        self,
        query: str,
        documents: List[str]
    ) -> List[float]:
        """
        备用相似度计算（当模型不可用时）
        
        Args:
            query: 查询文本
            documents: 文档列表
            
        Returns:
            相似度分数列�?        """
        try:
            from rag.embedder import get_embedder
            embedder = get_embedder()
            
            query_embedding = embedder.embed_single(query)
            doc_embeddings = embedder.embed(documents)
            
            import numpy as np
            query_vec = np.array(query_embedding)
            doc_vecs = np.array(doc_embeddings)
            
            similarities = np.dot(doc_vecs, query_vec) / (
                np.linalg.norm(doc_vecs, axis=1) * np.linalg.norm(query_vec) + 1e-8
            )
            
            return similarities.tolist()
        except Exception as e:
            logger.warning(f"备用相似度计算失败：{e}")
            return [0.5] * len(documents)
    
    def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: Optional[int] = None
    ) -> List[RerankResult]:
        """
        对检索结果进行重排序
        
        Args:
            query: 查询文本
            results: 检索结果列�?            top_k: 返回数量（None 表示返回全部�?            
        Returns:
            重排序后的结�?        """
        if not results:
            return []
        
        self._load_model()
        
        documents = [r.get("content", "") for r in results]
        
        if self.model is not None:
            try:
                pairs = [(query, doc) for doc in documents]
                scores = self.model.predict(pairs, batch_size=self.batch_size)
                
                if hasattr(scores, 'tolist'):
                    scores = scores.tolist()
            except Exception as e:
                logger.warning(f"Cross-Encoder 预测失败：{e}，使用备用方�?)
                scores = self._compute_similarity_fallback(query, documents)
        else:
            scores = self._compute_similarity_fallback(query, documents)
        
        indexed_results = list(enumerate(results))
        indexed_results.sort(key=lambda x: scores[x[0]], reverse=True)
        
        reranked_results = []
        for new_rank, (original_rank, result) in enumerate(indexed_results):
            reranked_results.append(RerankResult(
                id=result.get("id", result.get("content", "")[:50]),
                content=result.get("content", ""),
                score=float(scores[original_rank]),
                original_score=result.get("score", 0),
                original_rank=original_rank,
                metadata=result.get("metadata", {})
            ))
        
        if top_k is not None:
            reranked_results = reranked_results[:top_k]
        
        logger.info(f"重排序完成：{len(reranked_results)} 个结�?)
        
        return reranked_results
    
    async def rerank_async(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: Optional[int] = None
    ) -> List[RerankResult]:
        """
        异步重排�?        
        Args:
            query: 查询文本
            results: 检索结果列�?            top_k: 返回数量
            
        Returns:
            重排序后的结�?        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: self.rerank(query, results, top_k)
        )
    
    def rerank_with_threshold(
        self,
        query: str,
        results: List[Dict[str, Any]],
        threshold: float = 0.5,
        min_results: int = 3
    ) -> List[RerankResult]:
        """
        带阈值的重排�?        
        Args:
            query: 查询文本
            results: 检索结果列�?            threshold: 分数阈�?            min_results: 最小返回数�?            
        Returns:
            重排序后的结�?        """
        reranked = self.rerank(query, results)
        
        filtered = [r for r in reranked if r.score >= threshold]
        
        if len(filtered) < min_results:
            filtered = reranked[:min_results]
        
        return filtered


class LLMReranker:
    """基于 LLM 的重排序�?""
    
    def __init__(
        self,
        llm_client: Any = None,
        model: str = "gpt-3.5-turbo",
        max_tokens: int = 1000
    ):
        """
        初始�?LLM 重排序器
        
        Args:
            llm_client: LLM 客户�?            model: 模型名称
            max_tokens: 最�?token �?        """
        self.llm_client = llm_client
        self.model = model
        self.max_tokens = max_tokens
    
    def _build_prompt(
        self,
        query: str,
        documents: List[str]
    ) -> str:
        """
        构建重排序提示词
        
        Args:
            query: 查询文本
            documents: 文档列表
            
        Returns:
            提示�?        """
        doc_text = "\n\n".join([
            f"[文档 {i+1}]\n{doc[:500]}..."
            for i, doc in enumerate(documents)
        ])
        
        prompt = f"""请根据查询的相关性对以下文档进行排序�?
查询：{query}

{doc_text}

请返回一�?JSON 格式的排序结果，包含文档编号和相关性分数（0-1）：
```json
[
  {{"rank": 1, "doc_id": 1, "score": 0.95, "reason": "简短说�?}},
  {{"rank": 2, "doc_id": 2, "score": 0.80, "reason": "简短说�?}},
  ...
]
```

只返�?JSON，不要其他内容�?""
        
        return prompt
    
    def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: Optional[int] = None
    ) -> List[RerankResult]:
        """
        使用 LLM 进行重排�?        
        Args:
            query: 查询文本
            results: 检索结果列�?            top_k: 返回数量
            
        Returns:
            重排序后的结�?        """
        if not results:
            return []
        
        if self.llm_client is None:
            logger.warning("LLM 客户端未设置，返回原始结�?)
            return [
                RerankResult(
                    id=r.get("id", r.get("content", "")[:50]),
                    content=r.get("content", ""),
                    score=r.get("score", 0),
                    original_score=r.get("score", 0),
                    original_rank=i,
                    metadata=r.get("metadata", {})
                )
                for i, r in enumerate(results)
            ]
        
        documents = [r.get("content", "") for r in results]
        prompt = self._build_prompt(query, documents)
        
        try:
            response = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
                temperature=0
            )
            
            import json
            import re
            
            content = response.choices[0].message.content
            
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = content
            
            rankings = json.loads(json_str)
            
            reranked_results = []
            for item in rankings:
                doc_id = item.get("doc_id", 1) - 1
                if 0 <= doc_id < len(results):
                    result = results[doc_id]
                    reranked_results.append(RerankResult(
                        id=result.get("id", result.get("content", "")[:50]),
                        content=result.get("content", ""),
                        score=item.get("score", 0.5),
                        original_score=result.get("score", 0),
                        original_rank=doc_id,
                        metadata=result.get("metadata", {})
                    ))
            
            if top_k is not None:
                reranked_results = reranked_results[:top_k]
            
            return reranked_results
            
        except Exception as e:
            logger.error(f"LLM 重排序失败：{e}")
            return [
                RerankResult(
                    id=r.get("id", r.get("content", "")[:50]),
                    content=r.get("content", ""),
                    score=r.get("score", 0),
                    original_score=r.get("score", 0),
                    original_rank=i,
                    metadata=r.get("metadata", {})
                )
                for i, r in enumerate(results)
            ]


class MultiStageReranker:
    """多阶段重排序�?""
    
    def __init__(
        self,
        cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        llm_client: Any = None,
        llm_model: str = "gpt-3.5-turbo",
        use_llm: bool = False,
        cross_encoder_top_k: int = 20,
        final_top_k: int = 10
    ):
        """
        初始化多阶段重排序器
        
        Args:
            cross_encoder_model: Cross-Encoder 模型名称
            llm_client: LLM 客户�?            llm_model: LLM 模型名称
            use_llm: 是否使用 LLM 重排�?            cross_encoder_top_k: Cross-Encoder 阶段保留数量
            final_top_k: 最终返回数�?        """
        self.cross_encoder = CrossEncoderReranker(model_name=cross_encoder_model)
        self.llm_reranker = LLMReranker(llm_client=llm_client, model=llm_model) if use_llm else None
        self.use_llm = use_llm
        self.cross_encoder_top_k = cross_encoder_top_k
        self.final_top_k = final_top_k
    
    def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: Optional[int] = None
    ) -> List[RerankResult]:
        """
        多阶段重排序
        
        Args:
            query: 查询文本
            results: 检索结果列�?            top_k: 返回数量
            
        Returns:
            重排序后的结�?        """
        if not results:
            return []
        
        top_k = top_k or self.final_top_k
        
        cross_encoder_results = self.cross_encoder.rerank(
            query=query,
            results=results,
            top_k=min(self.cross_encoder_top_k, len(results))
        )
        
        if not self.use_llm or self.llm_reranker is None:
            return cross_encoder_results[:top_k]
        
        llm_results = self.llm_reranker.rerank(
            query=query,
            results=[{
                "id": r.id,
                "content": r.content,
                "score": r.score,
                "metadata": r.metadata
            } for r in cross_encoder_results],
            top_k=top_k
        )
        
        return llm_results


_reranker_instance: Optional[CrossEncoderReranker] = None


def get_reranker(
    model_name: Optional[str] = None,
    **kwargs
) -> CrossEncoderReranker:
    """
    获取重排序器实例
    
    Args:
        model_name: 模型名称
        **kwargs: 其他参数
        
    Returns:
        重排序器实例
    """
    global _reranker_instance
    
    if _reranker_instance is None:
        model = model_name or "cross-encoder/ms-marco-MiniLM-L-6-v2"
        _reranker_instance = CrossEncoderReranker(model_name=model, **kwargs)
    
    return _reranker_instance


def reset_reranker(model_name: str, **kwargs) -> CrossEncoderReranker:
    """重置重排序器"""
    global _reranker_instance
    _reranker_instance = CrossEncoderReranker(model_name=model_name, **kwargs)
    return _reranker_instance
