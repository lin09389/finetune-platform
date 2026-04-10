"""
RAG 知识库 - 检索质量评估器
实现检索质量指标：MRR、NDCG、MAP、Recall、Precision
"""
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """评估结果"""
    query: str
    retrieved_ids: list[str]
    relevant_ids: list[str]
    metrics: dict[str, float] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchEvaluationResult:
    """批量评估结果"""
    total_queries: int
    avg_metrics: dict[str, float] = field(default_factory=dict)
    individual_results: list[EvaluationResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class RetrievalEvaluator:
    """检索质量评估器"""

    def __init__(self, k_values: list[int] | None = None):
        """
        初始化评估器

        Args:
            k_values: 评估的 K 值列表，如 [1, 3, 5, 10]
        """
        self.k_values = k_values or [1, 3, 5, 10]
        self.evaluation_history: list[BatchEvaluationResult] = []
        self.history_dir = Path("data/evaluation_history")
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def precision_at_k(
        self,
        retrieved_ids: list[str],
        relevant_ids: list[str],
        k: int
    ) -> float:
        """
        计算 Precision@K

        Args:
            retrieved_ids: 检索结果 ID 列表
            relevant_ids: 相关文档 ID 列表
            k: 截断位置

        Returns:
            Precision@K 值
        """
        if k <= 0:
            return 0.0

        retrieved_at_k = retrieved_ids[:k]
        relevant_set = set(relevant_ids)

        relevant_retrieved = sum(1 for doc_id in retrieved_at_k if doc_id in relevant_set)

        return relevant_retrieved / k

    def recall_at_k(
        self,
        retrieved_ids: list[str],
        relevant_ids: list[str],
        k: int
    ) -> float:
        """
        计算 Recall@K

        Args:
            retrieved_ids: 检索结果 ID 列表
            relevant_ids: 相关文档 ID 列表
            k: 截断位置

        Returns:
            Recall@K 值
        """
        if not relevant_ids:
            return 0.0

        retrieved_at_k = retrieved_ids[:k]
        relevant_set = set(relevant_ids)

        relevant_retrieved = sum(1 for doc_id in retrieved_at_k if doc_id in relevant_set)

        return relevant_retrieved / len(relevant_set)

    def mrr(self, retrieved_ids: list[str], relevant_ids: list[str]) -> float:
        """
        计算 MRR (Mean Reciprocal Rank)

        Args:
            retrieved_ids: 检索结果 ID 列表
            relevant_ids: 相关文档 ID 列表

        Returns:
            MRR 值
        """
        relevant_set = set(relevant_ids)

        for i, doc_id in enumerate(retrieved_ids):
            if doc_id in relevant_set:
                return 1.0 / (i + 1)

        return 0.0

    def ndcg_at_k(
        self,
        retrieved_ids: list[str],
        relevant_ids: list[str],
        k: int
    ) -> float:
        """
        计算 NDCG@K (Normalized Discounted Cumulative Gain)

        Args:
            retrieved_ids: 检索结果 ID 列表
            relevant_ids: 相关文档 ID 列表
            k: 截断位置

        Returns:
            NDCG@K 值
        """
        relevant_set = set(relevant_ids)

        dcg = 0.0
        for i, doc_id in enumerate(retrieved_ids[:k]):
            if doc_id in relevant_set:
                dcg += 1.0 / math.log2(i + 2)

        ideal_dcg = 0.0
        for i in range(min(k, len(relevant_ids))):
            ideal_dcg += 1.0 / math.log2(i + 2)

        if ideal_dcg == 0:
            return 0.0

        return dcg / ideal_dcg

    def map_score(
        self,
        retrieved_ids: list[str],
        relevant_ids: list[str]
    ) -> float:
        """
        计算 MAP (Mean Average Precision)

        Args:
            retrieved_ids: 检索结果 ID 列表
            relevant_ids: 相关文档 ID 列表

        Returns:
            MAP 值
        """
        if not relevant_ids:
            return 0.0

        relevant_set = set(relevant_ids)
        precision_sum = 0.0
        relevant_count = 0

        for i, doc_id in enumerate(retrieved_ids):
            if doc_id in relevant_set:
                relevant_count += 1
                precision_sum += relevant_count / (i + 1)

        return precision_sum / len(relevant_set)

    def evaluate(
        self,
        query: str,
        retrieved_ids: list[str],
        relevant_ids: list[str]
    ) -> EvaluationResult:
        """
        评估单个查询

        Args:
            query: 查询文本
            retrieved_ids: 检索结果 ID 列表
            relevant_ids: 相关文档 ID 列表

        Returns:
            评估结果
        """
        metrics = {}

        for k in self.k_values:
            metrics[f"precision@{k}"] = self.precision_at_k(retrieved_ids, relevant_ids, k)
            metrics[f"recall@{k}"] = self.recall_at_k(retrieved_ids, relevant_ids, k)
            metrics[f"ndcg@{k}"] = self.ndcg_at_k(retrieved_ids, relevant_ids, k)

        metrics["mrr"] = self.mrr(retrieved_ids, relevant_ids)
        metrics["map"] = self.map_score(retrieved_ids, relevant_ids)

        return EvaluationResult(
            query=query,
            retrieved_ids=retrieved_ids,
            relevant_ids=relevant_ids,
            metrics=metrics
        )

    def evaluate_batch(
        self,
        queries: list[str],
        retrieved_ids_list: list[list[str]],
        relevant_ids_list: list[list[str]]
    ) -> BatchEvaluationResult:
        """
        批量评估

        Args:
            queries: 查询文本列表
            retrieved_ids_list: 检索结果 ID 列表的列表
            relevant_ids_list: 相关文档 ID 列表的列表

        Returns:
            批量评估结果
        """
        individual_results = []

        for query, retrieved_ids, relevant_ids in zip(
            queries, retrieved_ids_list, relevant_ids_list, strict=False
        ):
            result = self.evaluate(query, retrieved_ids, relevant_ids)
            individual_results.append(result)

        avg_metrics = {}
        metric_names = individual_results[0].metrics.keys() if individual_results else []

        for metric_name in metric_names:
            values = [r.metrics[metric_name] for r in individual_results]
            avg_metrics[metric_name] = sum(values) / len(values) if values else 0.0

        batch_result = BatchEvaluationResult(
            total_queries=len(queries),
            avg_metrics=avg_metrics,
            individual_results=individual_results
        )

        self.evaluation_history.append(batch_result)

        return batch_result

    def save_history(self, filename: str | None = None):
        """保存评估历史"""
        if not filename:
            filename = f"evaluation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        filepath = self.history_dir / filename

        history_data = []
        for batch in self.evaluation_history:
            batch_data = {
                "total_queries": batch.total_queries,
                "avg_metrics": batch.avg_metrics,
                "timestamp": batch.timestamp,
                "individual_results": [
                    {
                        "query": r.query,
                        "retrieved_ids": r.retrieved_ids,
                        "relevant_ids": r.relevant_ids,
                        "metrics": r.metrics
                    }
                    for r in batch.individual_results
                ]
            }
            history_data.append(batch_data)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(history_data, f, indent=2, ensure_ascii=False)

        logger.info(f"评估历史已保存：{filepath}")


class OnlineEvaluator:
    """在线评估器（实时收集反馈）"""

    def __init__(self):
        """初始化在线评估器"""
        self.feedback_data: list[dict[str, Any]] = []
        self.feedback_dir = Path("data/feedback")
        self.feedback_dir.mkdir(parents=True, exist_ok=True)

    def record_feedback(
        self,
        query: str,
        retrieved_ids: list[str],
        clicked_ids: list[str],
        session_id: str | None = None
    ):
        """
        记录用户反馈

        Args:
            query: 查询文本
            retrieved_ids: 检索结果 ID 列表
            clicked_ids: 用户点击的 ID 列表
            session_id: 会话 ID
        """
        feedback = {
            "query": query,
            "retrieved_ids": retrieved_ids,
            "clicked_ids": clicked_ids,
            "session_id": session_id,
            "timestamp": datetime.now().isoformat()
        }

        self.feedback_data.append(feedback)

        logger.debug(f"记录反馈：query={query[:50]}, clicks={len(clicked_ids)}")

    def get_click_through_rate(self, position: int) -> float:
        """
        获取特定位置的点击率

        Args:
            position: 位置索引（从 0 开始）

        Returns:
            点击率
        """
        if not self.feedback_data:
            return 0.0

        total = 0
        clicks = 0

        for feedback in self.feedback_data:
            if position < len(feedback["retrieved_ids"]):
                total += 1
                doc_id = feedback["retrieved_ids"][position]
                if doc_id in feedback["clicked_ids"]:
                    clicks += 1

        return clicks / total if total > 0 else 0.0

    def save_feedback(self, filename: str | None = None):
        """保存反馈数据"""
        if not filename:
            filename = f"feedback_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        filepath = self.feedback_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.feedback_data, f, indent=2, ensure_ascii=False)

        logger.info(f"反馈数据已保存：{filepath}")


_evaluator: RetrievalEvaluator | None = None
_online_evaluator: OnlineEvaluator | None = None


def get_evaluator(k_values: list[int] | None = None) -> RetrievalEvaluator:
    """获取评估器实例"""
    global _evaluator
    if _evaluator is None:
        _evaluator = RetrievalEvaluator(k_values)
    return _evaluator


def get_online_evaluator() -> OnlineEvaluator:
    """获取在线评估器实例"""
    global _online_evaluator
    if _online_evaluator is None:
        _online_evaluator = OnlineEvaluator()
    return _online_evaluator


def reset_evaluator():
    """重置评估器"""
    global _evaluator, _online_evaluator
    _evaluator = None
    _online_evaluator = None
