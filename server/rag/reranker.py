"""
RAG 知识库 - 重排序器
使用 Cross-Encoder 对检索结果进行重排序
"""
import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


def _setup_hf_mirror():
    """配置 HuggingFace 镜像源（解决国内访问问题）"""
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
        logger.info(f"已配置 HuggingFace 镜像：{endpoint}")


@dataclass
class RerankResult:
    """重排序结果"""
    id: str
    content: str
    score: float
    original_score: float
    original_rank: int
    metadata: dict[str, Any] = field(default_factory=dict)


class CrossEncoderReranker:
    """Cross-Encoder 重排序器"""

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        device: str | None = None,
        max_length: int = 512,
        batch_size: int = 32
    ):
        """
        初始化重排序器
        
        Args:
            model_name: Cross-Encoder 模型名称
            device: 设备（cuda/cpu）
            max_length: 最大序列长度
            batch_size: 批次大小
        """
        self.model_name = model_name
        self.device = device
        self.max_length = max_length
        self.batch_size = batch_size

        self.model = None
        self.tokenizer = None
        self._executor = ThreadPoolExecutor(max_workers=1)

    def _load_model(self):
        """懒加载模型"""
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
                logger.warning("sentence-transformers 未安装，使用备用重排序方法")
                self.model = None
            except Exception as e:
                logger.error(f"加载 Cross-Encoder 模型失败：{e}")
                self.model = None

    def _compute_similarity_fallback(
        self,
        query: str,
        documents: list[str]
    ) -> list[float]:
        """备用相似度计算（无模型时使用）"""
        from rag.embedder import get_embedder

        embedder = get_embedder()
        query_embedding = embedder.embed_single(query)
        doc_embeddings = embedder.embed(documents)

        scores = []
        for doc_emb in doc_embeddings:
            score = sum(a * b for a, b in zip(query_embedding, doc_emb))
            scores.append(score)

        return scores

    def rerank(
        self,
        query: str,
        documents: list[str],
        ids: list[str] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
        top_k: int = 10
    ) -> list[RerankResult]:
        """
        重排序
        
        Args:
            query: 查询文本
            documents: 文档列表
            ids: 文档 ID 列表
            metadatas: 元数据列表
            top_k: 返回结果数量
            
        Returns:
            重排序结果列表
        """
        if not documents:
            return []

        if ids is None:
            ids = [f"doc_{i}" for i in range(len(documents))]

        if metadatas is None:
            metadatas = [{}] * len(documents)

        self._load_model()

        if self.model is not None:
            try:
                pairs = [[query, doc] for doc in documents]
                scores = self.model.predict(pairs)
            except Exception as e:
                logger.warning(f"Cross-Encoder 推理失败：{e}，使用备用方法")
                scores = self._compute_similarity_fallback(query, documents)
        else:
            scores = self._compute_similarity_fallback(query, documents)

        ranked = sorted(
            zip(ids, documents, scores, metadatas),
            key=lambda x: x[2],
            reverse=True
        )

        results = []
        for rank, (doc_id, content, score, metadata) in enumerate(ranked[:top_k]):
            results.append(RerankResult(
                id=doc_id,
                content=content,
                score=float(score),
                original_score=float(score),
                original_rank=rank,
                metadata=metadata
            ))

        return results

    async def arerank(
        self,
        query: str,
        documents: list[str],
        ids: list[str] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
        top_k: int = 10
    ) -> list[RerankResult]:
        """异步重排序"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: self.rerank(query, documents, ids, metadatas, top_k)
        )


class LLMReranker:
    """LLM 重排序器"""

    def __init__(self, llm_client=None):
        """
        初始化 LLM 重排序器
        
        Args:
            llm_client: LLM 客户端
        """
        self.llm_client = llm_client

    def rerank(
        self,
        query: str,
        documents: list[str],
        ids: list[str] | None = None,
        top_k: int = 10
    ) -> list[RerankResult]:
        """使用 LLM 进行重排序"""
        if not documents or not self.llm_client:
            return []

        if ids is None:
            ids = [f"doc_{i}" for i in range(len(documents))]

        prompt = f"""请对以下文档与查询的相关性进行评分（0-10分）：

查询：{query}

文档列表：
{chr(10).join(f"{i+1}. {doc[:200]}..." for i, doc in enumerate(documents))}

请返回一个 JSON 列表，格式为 [{{"index": 0, "score": 8}}, ...]
"""

        try:
            response = self.llm_client.generate(prompt)
            import json
            scores = json.loads(response)

            results = []
            for item in scores:
                idx = item.get("index", 0)
                if 0 <= idx < len(documents):
                    results.append(RerankResult(
                        id=ids[idx],
                        content=documents[idx],
                        score=item.get("score", 0) / 10.0,
                        original_score=0.0,
                        original_rank=idx,
                        metadata={}
                    ))

            return sorted(results, key=lambda x: x.score, reverse=True)[:top_k]
        except Exception as e:
            logger.error(f"LLM 重排序失败：{e}")
            return []


class MultiStageReranker:
    """多阶段重排序器"""

    def __init__(
        self,
        first_stage_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        second_stage_model: str | None = None
    ):
        """
        初始化多阶段重排序器
        
        Args:
            first_stage_model: 第一阶段模型
            second_stage_model: 第二阶段模型（可选）
        """
        self.first_stage = CrossEncoderReranker(model_name=first_stage_model)
        self.second_stage = CrossEncoderReranker(model_name=second_stage_model) if second_stage_model else None

    def rerank(
        self,
        query: str,
        documents: list[str],
        ids: list[str] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
        top_k: int = 10,
        first_stage_k: int = 50
    ) -> list[RerankResult]:
        """多阶段重排序"""
        if not documents:
            return []

        first_results = self.first_stage.rerank(
            query, documents, ids, metadatas, min(first_stage_k, len(documents))
        )

        if self.second_stage and len(first_results) > top_k:
            second_docs = [r.content for r in first_results]
            second_ids = [r.id for r in first_results]
            second_metas = [r.metadata for r in first_results]

            return self.second_stage.rerank(
                query, second_docs, second_ids, second_metas, top_k
            )

        return first_results[:top_k]


_reranker: CrossEncoderReranker | None = None


def get_reranker(
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
    device: str | None = None
) -> CrossEncoderReranker:
    """获取重排序器实例"""
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoderReranker(model_name=model_name, device=device)
    return _reranker


def reset_reranker():
    """重置重排序器"""
    global _reranker
    _reranker = None
