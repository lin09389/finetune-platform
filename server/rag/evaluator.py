"""
RAG 知识�?- 检索质量评估器
实现检索质量指标：MRR、NDCG、MAP、Recall、Precision
"""
from typing import List, Dict, Any, Optional, Tuple
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """评估结果"""
    query: str
    retrieved_ids: List[str]
    relevant_ids: List[str]
    metrics: Dict[str, float] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchEvaluationResult:
    """批量评估结果"""
    total_queries: int
    avg_metrics: Dict[str, float] = field(default_factory=dict)
    individual_results: List[EvaluationResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class RetrievalEvaluator:
    """检索质量评估器"""
    
    def __init__(self, k_values: Optional[List[int]] = None):
        """
        初始化评估器
        
        Args:
            k_values: 评估�?K 值列表，�?[1, 3, 5, 10]
        """
        self.k_values = k_values or [1, 3, 5, 10]
        self.evaluation_history: List[BatchEvaluationResult] = []
        self.history_dir = Path("data/evaluation_history")
        self.history_dir.mkdir(parents=True, exist_ok=True)
    
    def precision_at_k(
        self,
        retrieved_ids: List[str],
        relevant_ids: List[str],
        k: int
    ) -> float:
        """
        计算 Precision@K
        
        Args:
            retrieved_ids: 检索结�?ID 列表
            relevant_ids: 相关文档 ID 列表
            k: 截断位置
            
        Returns:
            Precision@K �?        """
        if k <= 0:
            return 0.0
        
        retrieved_at_k = retrieved_ids[:k]
        relevant_set = set(relevant_ids)
        
        relevant_retrieved = sum(1 for doc_id in retrieved_at_k if doc_id in relevant_set)
        
        return relevant_retrieved / k
    
    def recall_at_k(
        self,
        retrieved_ids: List[str],
        relevant_ids: List[str],
        k: int
    ) -> float:
        """
        计算 Recall@K
        
        Args:
            retrieved_ids: 检索结�?ID 列表
            relevant_ids: 相关文档 ID 列表
            k: 截断位置
            
        Returns:
            Recall@K �?        """
        if not relevant_ids:
            return 0.0
        
        retrieved_at_k = retrieved_ids[:k]
        relevant_set = set(relevant_ids)
        
        relevant_retrieved = sum(1 for doc_id in retrieved_at_k if doc_id in relevant_set)
        
        return relevant_retrieved / len(relevant_set)
    
    def mrr(
        self,
        retrieved_ids: List[str],
        relevant_ids: List[str]
    ) -> float:
        """
        计算 Mean Reciprocal Rank (MRR)
        
        Args:
            retrieved_ids: 检索结�?ID 列表
            relevant_ids: 相关文档 ID 列表
            
        Returns:
            MRR �?        """
        relevant_set = set(relevant_ids)
        
        for rank, doc_id in enumerate(retrieved_ids, start=1):
            if doc_id in relevant_set:
                return 1.0 / rank
        
        return 0.0
    
    def average_precision(
        self,
        retrieved_ids: List[str],
        relevant_ids: List[str]
    ) -> float:
        """
        计算 Average Precision (AP)
        
        Args:
            retrieved_ids: 检索结�?ID 列表
            relevant_ids: 相关文档 ID 列表
            
        Returns:
            AP �?        """
        if not relevant_ids:
            return 0.0
        
        relevant_set = set(relevant_ids)
        num_relevant = len(relevant_set)
        
        precisions = []
        relevant_count = 0
        
        for rank, doc_id in enumerate(retrieved_ids, start=1):
            if doc_id in relevant_set:
                relevant_count += 1
                precision_at_rank = relevant_count / rank
                precisions.append(precision_at_rank)
        
        if not precisions:
            return 0.0
        
        return sum(precisions) / num_relevant
    
    def dcg_at_k(
        self,
        retrieved_ids: List[str],
        relevant_ids: List[str],
        relevance_scores: Optional[Dict[str, float]] = None,
        k: int = 10
    ) -> float:
        """
        计算 Discounted Cumulative Gain (DCG@K)
        
        Args:
            retrieved_ids: 检索结�?ID 列表
            relevant_ids: 相关文档 ID 列表
            relevance_scores: 文档相关性分数字典（可选）
            k: 截断位置
            
        Returns:
            DCG@K �?        """
        retrieved_at_k = retrieved_ids[:k]
        relevant_set = set(relevant_ids)
        
        dcg = 0.0
        for rank, doc_id in enumerate(retrieved_at_k, start=1):
            if relevance_scores and doc_id in relevance_scores:
                rel = relevance_scores[doc_id]
            else:
                rel = 1.0 if doc_id in relevant_set else 0.0
            
            dcg += rel / math.log2(rank + 1)
        
        return dcg
    
    def ndcg_at_k(
        self,
        retrieved_ids: List[str],
        relevant_ids: List[str],
        relevance_scores: Optional[Dict[str, float]] = None,
        k: int = 10
    ) -> float:
        """
        计算 Normalized Discounted Cumulative Gain (NDCG@K)
        
        Args:
            retrieved_ids: 检索结�?ID 列表
            relevant_ids: 相关文档 ID 列表
            relevance_scores: 文档相关性分数字典（可选）
            k: 截断位置
            
        Returns:
            NDCG@K �?        """
        dcg = self.dcg_at_k(retrieved_ids, relevant_ids, relevance_scores, k)
        
        ideal_order = sorted(
            relevant_ids,
            key=lambda x: relevance_scores.get(x, 1.0) if relevance_scores else 1.0,
            reverse=True
        ) if relevance_scores else relevant_ids
        
        idcg = self.dcg_at_k(ideal_order, relevant_ids, relevance_scores, k)
        
        if idcg == 0:
            return 0.0
        
        return dcg / idcg
    
    def hit_rate_at_k(
        self,
        retrieved_ids: List[str],
        relevant_ids: List[str],
        k: int
    ) -> float:
        """
        计算 Hit Rate@K（命中率�?        
        Args:
            retrieved_ids: 检索结�?ID 列表
            relevant_ids: 相关文档 ID 列表
            k: 截断位置
            
        Returns:
            Hit Rate@K �?        """
        retrieved_at_k = retrieved_ids[:k]
        relevant_set = set(relevant_ids)
        
        for doc_id in retrieved_at_k:
            if doc_id in relevant_set:
                return 1.0
        
        return 0.0
    
    def evaluate_single(
        self,
        query: str,
        retrieved_ids: List[str],
        relevant_ids: List[str],
        relevance_scores: Optional[Dict[str, float]] = None
    ) -> EvaluationResult:
        """
        评估单个查询
        
        Args:
            query: 查询文本
            retrieved_ids: 检索结�?ID 列表
            relevant_ids: 相关文档 ID 列表
            relevance_scores: 文档相关性分数字典（可选）
            
        Returns:
            评估结果
        """
        metrics = {}
        details = {}
        
        metrics["mrr"] = self.mrr(retrieved_ids, relevant_ids)
        metrics["map"] = self.average_precision(retrieved_ids, relevant_ids)
        
        for k in self.k_values:
            metrics[f"precision@{k}"] = self.precision_at_k(retrieved_ids, relevant_ids, k)
            metrics[f"recall@{k}"] = self.recall_at_k(retrieved_ids, relevant_ids, k)
            metrics[f"ndcg@{k}"] = self.ndcg_at_k(retrieved_ids, relevant_ids, relevance_scores, k)
            metrics[f"hit_rate@{k}"] = self.hit_rate_at_k(retrieved_ids, relevant_ids, k)
        
        details["num_retrieved"] = len(retrieved_ids)
        details["num_relevant"] = len(relevant_ids)
        details["relevant_retrieved"] = len(set(retrieved_ids) & set(relevant_ids))
        
        return EvaluationResult(
            query=query,
            retrieved_ids=retrieved_ids,
            relevant_ids=relevant_ids,
            metrics=metrics,
            details=details
        )
    
    def evaluate_batch(
        self,
        queries: List[str],
        retrieved_ids_list: List[List[str]],
        relevant_ids_list: List[List[str]],
        relevance_scores_list: Optional[List[Dict[str, float]]] = None
    ) -> BatchEvaluationResult:
        """
        批量评估
        
        Args:
            queries: 查询文本列表
            retrieved_ids_list: 检索结�?ID 列表的列�?            relevant_ids_list: 相关文档 ID 列表的列�?            relevance_scores_list: 相关性分数字典列表（可选）
            
        Returns:
            批量评估结果
        """
        if len(queries) != len(retrieved_ids_list) or len(queries) != len(relevant_ids_list):
            raise ValueError("查询、检索结果和相关文档数量不匹�?)
        
        individual_results = []
        all_metrics: Dict[str, List[float]] = {}
        
        for i, (query, retrieved_ids, relevant_ids) in enumerate(
            zip(queries, retrieved_ids_list, relevant_ids_list)
        ):
            relevance_scores = relevance_scores_list[i] if relevance_scores_list else None
            
            result = self.evaluate_single(
                query=query,
                retrieved_ids=retrieved_ids,
                relevant_ids=relevant_ids,
                relevance_scores=relevance_scores
            )
            
            individual_results.append(result)
            
            for metric_name, value in result.metrics.items():
                if metric_name not in all_metrics:
                    all_metrics[metric_name] = []
                all_metrics[metric_name].append(value)
        
        avg_metrics = {
            metric_name: sum(values) / len(values)
            for metric_name, values in all_metrics.items()
        }
        
        batch_result = BatchEvaluationResult(
            total_queries=len(queries),
            avg_metrics=avg_metrics,
            individual_results=individual_results
        )
        
        self.evaluation_history.append(batch_result)
        
        return batch_result
    
    def compare_methods(
        self,
        queries: List[str],
        method_results: Dict[str, List[List[str]]],
        relevant_ids_list: List[List[str]]
    ) -> Dict[str, Dict[str, float]]:
        """
        比较不同检索方法的性能
        
        Args:
            queries: 查询文本列表
            method_results: 方法名称到检索结果的映射
            relevant_ids_list: 相关文档 ID 列表的列�?            
        Returns:
            各方法的平均指标
        """
        comparison = {}
        
        for method_name, retrieved_ids_list in method_results.items():
            batch_result = self.evaluate_batch(
                queries=queries,
                retrieved_ids_list=retrieved_ids_list,
                relevant_ids_list=relevant_ids_list
            )
            
            comparison[method_name] = batch_result.avg_metrics
        
        return comparison
    
    def save_evaluation(self, result: BatchEvaluationResult, name: Optional[str] = None):
        """
        保存评估结果
        
        Args:
            result: 评估结果
            name: 保存名称
        """
        name = name or f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        path = self.history_dir / f"{name}.json"
        
        data = {
            "total_queries": result.total_queries,
            "avg_metrics": result.avg_metrics,
            "timestamp": result.timestamp,
            "individual_results": [
                {
                    "query": r.query,
                    "retrieved_ids": r.retrieved_ids,
                    "relevant_ids": r.relevant_ids,
                    "metrics": r.metrics,
                    "details": r.details
                }
                for r in result.individual_results
            ]
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"评估结果已保存：{path}")
    
    def load_evaluation(self, name: str) -> Optional[BatchEvaluationResult]:
        """
        加载评估结果
        
        Args:
            name: 保存名称
            
        Returns:
            评估结果
        """
        path = self.history_dir / f"{name}.json"
        
        if not path.exists():
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        individual_results = [
            EvaluationResult(
                query=r["query"],
                retrieved_ids=r["retrieved_ids"],
                relevant_ids=r["relevant_ids"],
                metrics=r["metrics"],
                details=r["details"]
            )
            for r in data["individual_results"]
        ]
        
        return BatchEvaluationResult(
            total_queries=data["total_queries"],
            avg_metrics=data["avg_metrics"],
            individual_results=individual_results,
            timestamp=data["timestamp"]
        )
    
    def get_evaluation_history(self) -> List[Dict[str, Any]]:
        """
        获取评估历史
        
        Returns:
            评估历史列表
        """
        history = []
        for path in sorted(self.history_dir.glob("eval_*.json"), reverse=True):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                history.append({
                    "name": path.stem,
                    "timestamp": data.get("timestamp", ""),
                    "total_queries": data.get("total_queries", 0),
                    "avg_metrics": data.get("avg_metrics", {})
                })
            except Exception as e:
                logger.warning(f"读取评估历史失败：{path}，{e}")
        
        return history


class OnlineEvaluator:
    """在线评估器（用于实时监控�?""
    
    def __init__(self, window_size: int = 100):
        """
        初始化在线评估器
        
        Args:
            window_size: 滑动窗口大小
        """
        self.window_size = window_size
        self.recent_results: List[EvaluationResult] = []
        self.feedback_counts: Dict[str, int] = {}
        self.click_counts: Dict[str, int] = {}
    
    def record_feedback(
        self,
        query: str,
        retrieved_ids: List[str],
        clicked_ids: List[str],
        relevant_ids: Optional[List[str]] = None
    ):
        """
        记录用户反馈
        
        Args:
            query: 查询文本
            retrieved_ids: 检索结�?ID 列表
            clicked_ids: 用户点击的文�?ID 列表
            relevant_ids: 用户标记的相关文�?ID 列表（可选）
        """
        relevant_ids = relevant_ids or clicked_ids
        
        result = EvaluationResult(
            query=query,
            retrieved_ids=retrieved_ids,
            relevant_ids=relevant_ids,
            metrics={}
        )
        
        self.recent_results.append(result)
        if len(self.recent_results) > self.window_size:
            self.recent_results.pop(0)
        
        for doc_id in clicked_ids:
            self.click_counts[doc_id] = self.click_counts.get(doc_id, 0) + 1
    
    def get_recent_metrics(self) -> Dict[str, float]:
        """
        获取最近的评估指标
        
        Returns:
            评估指标
        """
        if not self.recent_results:
            return {}
        
        evaluator = RetrievalEvaluator()
        
        all_metrics: Dict[str, List[float]] = {}
        
        for result in self.recent_results:
            eval_result = evaluator.evaluate_single(
                query=result.query,
                retrieved_ids=result.retrieved_ids,
                relevant_ids=result.relevant_ids
            )
            
            for metric_name, value in eval_result.metrics.items():
                if metric_name not in all_metrics:
                    all_metrics[metric_name] = []
                all_metrics[metric_name].append(value)
        
        return {
            metric_name: sum(values) / len(values)
            for metric_name, values in all_metrics.items()
        }
    
    def get_popular_documents(self, top_k: int = 10) -> List[Tuple[str, int]]:
        """
        获取热门文档
        
        Args:
            top_k: 返回数量
            
        Returns:
            (文档ID, 点击次数) 列表
        """
        sorted_docs = sorted(
            self.click_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return sorted_docs[:top_k]


_evaluator_instance: Optional[RetrievalEvaluator] = None
_online_evaluator_instance: Optional[OnlineEvaluator] = None


def get_evaluator(k_values: Optional[List[int]] = None) -> RetrievalEvaluator:
    """
    获取评估器实�?    
    Args:
        k_values: 评估�?K 值列�?        
    Returns:
        评估器实�?    """
    global _evaluator_instance
    
    if _evaluator_instance is None:
        _evaluator_instance = RetrievalEvaluator(k_values=k_values)
    
    return _evaluator_instance


def get_online_evaluator(window_size: int = 100) -> OnlineEvaluator:
    """
    获取在线评估器实�?    
    Args:
        window_size: 滑动窗口大小
        
    Returns:
        在线评估器实�?    """
    global _online_evaluator_instance
    
    if _online_evaluator_instance is None:
        _online_evaluator_instance = OnlineEvaluator(window_size=window_size)
    
    return _online_evaluator_instance


def reset_evaluator(k_values: Optional[List[int]] = None) -> RetrievalEvaluator:
    """重置评估�?""
    global _evaluator_instance
    _evaluator_instance = RetrievalEvaluator(k_values=k_values)
    return _evaluator_instance
