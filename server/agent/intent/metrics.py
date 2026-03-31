"""
性能指标模块
评估意图检测性能
"""
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MetricRecord:
    """指标记录"""
    predicted: str
    actual: str | None
    confidence: float
    correct: bool
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class IntentMetrics:
    """意图检测性能指标"""

    def __init__(self):
        self.records: list[MetricRecord] = []
        self.true_positives: dict[str, int] = defaultdict(int)
        self.false_positives: dict[str, int] = defaultdict(int)
        self.false_negatives: dict[str, int] = defaultdict(int)
        self.total_predictions: int = 0
        self.correct_predictions: int = 0

    def record(
        self,
        predicted: str,
        actual: str | None = None,
        confidence: float = 0.0,
        is_correct: bool | None = None
    ):
        """
        记录预测结果
        
        Args:
            predicted: 预测的意图
            actual: 实际意图（如果已知）
            confidence: 置信度
            is_correct: 是否正确（如果已知）
        """
        correct = is_correct if is_correct is not None else (predicted == actual)

        self.records.append(MetricRecord(
            predicted=predicted,
            actual=actual,
            confidence=confidence,
            correct=correct
        ))

        self.total_predictions += 1
        if correct:
            self.correct_predictions += 1
            self.true_positives[predicted] += 1
        else:
            self.false_positives[predicted] += 1
            if actual:
                self.false_negatives[actual] += 1

    def get_accuracy(self) -> float:
        """获取准确率"""
        if self.total_predictions == 0:
            return 0.0
        return self.correct_predictions / self.total_predictions

    def get_precision(self, intent: str | None = None) -> float:
        """获取精确率"""
        if intent:
            tp = self.true_positives[intent]
            fp = self.false_positives[intent]
            if tp + fp == 0:
                return 0.0
            return tp / (tp + fp)
        else:
            total_tp = sum(self.true_positives.values())
            total_fp = sum(self.false_positives.values())
            if total_tp + total_fp == 0:
                return 0.0
            return total_tp / (total_tp + total_fp)

    def get_recall(self, intent: str | None = None) -> float:
        """获取召回率"""
        if intent:
            tp = self.true_positives[intent]
            fn = self.false_negatives[intent]
            if tp + fn == 0:
                return 0.0
            return tp / (tp + fn)
        else:
            total_tp = sum(self.true_positives.values())
            total_fn = sum(self.false_negatives.values())
            if total_tp + total_fn == 0:
                return 0.0
            return total_tp / (total_tp + total_fn)

    def get_f1_score(self, intent: str | None = None) -> float:
        """获取F1分数"""
        precision = self.get_precision(intent)
        recall = self.get_recall(intent)
        if precision + recall == 0:
            return 0.0
        return 2 * precision * recall / (precision + recall)

    def get_confusion_matrix(self) -> dict[str, dict[str, int]]:
        """获取混淆矩阵"""
        matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for record in self.records:
            if record.actual:
                matrix[record.actual][record.predicted] += 1

        return {k: dict(v) for k, v in matrix.items()}

    def get_report(self) -> dict[str, Any]:
        """获取完整报告"""
        intents = set(self.true_positives.keys()) | set(self.false_positives.keys())

        per_intent_metrics = {}
        for intent in intents:
            per_intent_metrics[intent] = {
                "precision": self.get_precision(intent),
                "recall": self.get_recall(intent),
                "f1_score": self.get_f1_score(intent),
                "true_positives": self.true_positives[intent],
                "false_positives": self.false_positives[intent],
                "false_negatives": self.false_negatives[intent]
            }

        return {
            "total_predictions": self.total_predictions,
            "correct_predictions": self.correct_predictions,
            "accuracy": self.get_accuracy(),
            "macro_precision": self.get_precision(),
            "macro_recall": self.get_recall(),
            "macro_f1": self.get_f1_score(),
            "per_intent_metrics": per_intent_metrics,
            "confusion_matrix": self.get_confusion_matrix()
        }

    def export_json(self, filepath: str):
        """导出为JSON"""
        report = self.get_report()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    def reset(self):
        """重置指标"""
        self.records.clear()
        self.true_positives.clear()
        self.false_positives.clear()
        self.false_negatives.clear()
        self.total_predictions = 0
        self.correct_predictions = 0


class MetricsAggregator:
    """指标聚合器"""

    def __init__(self):
        self.metrics_by_session: dict[str, IntentMetrics] = {}
        self.global_metrics = IntentMetrics()

    def get_or_create_session_metrics(self, session_id: str) -> IntentMetrics:
        """获取或创建会话指标"""
        if session_id not in self.metrics_by_session:
            self.metrics_by_session[session_id] = IntentMetrics()
        return self.metrics_by_session[session_id]

    def record(
        self,
        predicted: str,
        actual: str | None = None,
        confidence: float = 0.0,
        is_correct: bool | None = None,
        session_id: str | None = None
    ):
        """记录预测"""
        self.global_metrics.record(predicted, actual, confidence, is_correct)

        if session_id:
            session_metrics = self.get_or_create_session_metrics(session_id)
            session_metrics.record(predicted, actual, confidence, is_correct)

    def get_global_report(self) -> dict[str, Any]:
        """获取全局报告"""
        return self.global_metrics.get_report()

    def get_session_report(self, session_id: str) -> dict[str, Any] | None:
        """获取会话报告"""
        if session_id in self.metrics_by_session:
            return self.metrics_by_session[session_id].get_report()
        return None

    def get_all_sessions(self) -> list[str]:
        """获取所有会话ID"""
        return list(self.metrics_by_session.keys())

    def reset(self):
        """重置所有指标"""
        self.global_metrics.reset()
        self.metrics_by_session.clear()


def create_metrics() -> IntentMetrics:
    """创建指标"""
    return IntentMetrics()


def create_metrics_aggregator() -> MetricsAggregator:
    """创建指标聚合器"""
    return MetricsAggregator()
