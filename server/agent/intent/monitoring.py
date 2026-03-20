"""
意图检测模型评估与监控体系
支持实时性能监控、准确率评估、异常检测、自动告警
"""
import time
import json
import logging
import threading
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
import statistics

logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class MetricType(str, Enum):
    """指标类型"""
    ACCURACY = "accuracy"
    PRECISION = "precision"
    RECALL = "recall"
    F1_SCORE = "f1_score"
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"
    CONFIDENCE = "confidence"


@dataclass
class MetricPoint:
    """指标数据点"""
    timestamp: datetime
    value: float
    tags: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Alert:
    """告警"""
    level: AlertLevel
    metric_type: MetricType
    message: str
    value: float
    threshold: float
    timestamp: datetime = field(default_factory=datetime.now)
    resolved: bool = False
    resolved_at: Optional[datetime] = None


@dataclass
class EvaluationResult:
    """评估结果"""
    intent_type: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    true_negatives: int = 0
    
    @property
    def precision(self) -> float:
        if self.true_positives + self.false_positives == 0:
            return 0.0
        return self.true_positives / (self.true_positives + self.false_positives)
    
    @property
    def recall(self) -> float:
        if self.true_positives + self.false_negatives == 0:
            return 0.0
        return self.true_positives / (self.true_positives + self.false_negatives)
    
    @property
    def f1_score(self) -> float:
        if self.precision + self.recall == 0:
            return 0.0
        return 2 * self.precision * self.recall / (self.precision + self.recall)
    
    @property
    def accuracy(self) -> float:
        total = self.true_positives + self.false_positives + self.false_negatives + self.true_negatives
        if total == 0:
            return 0.0
        return (self.true_positives + self.true_negatives) / total


class MetricsCollector:
    """指标收集器"""
    
    def __init__(self, max_points: int = 10000):
        self.max_points = max_points
        self.metrics: Dict[str, List[MetricPoint]] = defaultdict(list)
        self.lock = threading.Lock()
    
    def record(self, metric_name: str, value: float, tags: Optional[Dict[str, str]] = None, metadata: Optional[Dict[str, Any]] = None):
        """记录指标"""
        with self.lock:
            point = MetricPoint(
                timestamp=datetime.now(),
                value=value,
                tags=tags or {},
                metadata=metadata or {}
            )
            self.metrics[metric_name].append(point)
            
            if len(self.metrics[metric_name]) > self.max_points:
                self.metrics[metric_name] = self.metrics[metric_name][-self.max_points:]
    
    def get_metrics(self, metric_name: str, since: Optional[datetime] = None) -> List[MetricPoint]:
        """获取指标数据"""
        with self.lock:
            points = self.metrics.get(metric_name, [])
            if since:
                points = [p for p in points if p.timestamp >= since]
            return points
    
    def get_aggregated(self, metric_name: str, window_minutes: int = 5) -> Dict[str, float]:
        """获取聚合指标"""
        since = datetime.now() - timedelta(minutes=window_minutes)
        points = self.get_metrics(metric_name, since)
        
        if not points:
            return {"count": 0, "mean": 0, "min": 0, "max": 0, "std": 0}
        
        values = [p.value for p in points]
        return {
            "count": len(values),
            "mean": statistics.mean(values),
            "min": min(values),
            "max": max(values),
            "std": statistics.stdev(values) if len(values) > 1 else 0,
            "p50": statistics.median(values),
            "p95": sorted(values)[int(len(values) * 0.95)] if len(values) > 20 else max(values),
            "p99": sorted(values)[int(len(values) * 0.99)] if len(values) > 100 else max(values)
        }
    
    def clear(self, metric_name: Optional[str] = None):
        """清除指标"""
        with self.lock:
            if metric_name:
                self.metrics[metric_name] = []
            else:
                self.metrics.clear()


class AlertManager:
    """告警管理器"""
    
    def __init__(self):
        self.alerts: List[Alert] = []
        self.handlers: List[Callable[[Alert], None]] = []
        self.thresholds: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        
        self._init_default_thresholds()
    
    def _init_default_thresholds(self):
        """初始化默认阈值"""
        self.thresholds = {
            "accuracy": {"warning": 0.85, "error": 0.75, "critical": 0.60},
            "latency_ms": {"warning": 100, "error": 500, "critical": 1000},
            "error_rate": {"warning": 0.05, "error": 0.10, "critical": 0.20},
            "confidence": {"warning": 0.70, "error": 0.50, "critical": 0.30}
        }
    
    def set_threshold(self, metric_name: str, level: AlertLevel, value: float):
        """设置阈值"""
        if metric_name not in self.thresholds:
            self.thresholds[metric_name] = {}
        self.thresholds[metric_name][level.value] = value
    
    def add_handler(self, handler: Callable[[Alert], None]):
        """添加告警处理器"""
        self.handlers.append(handler)
    
    def check_and_alert(self, metric_name: str, value: float, comparison: str = "less") -> Optional[Alert]:
        """检查并触发告警"""
        thresholds = self.thresholds.get(metric_name, {})
        
        alert_level = None
        threshold_value = None
        
        if comparison == "less":
            if value < thresholds.get("critical", 0):
                alert_level = AlertLevel.CRITICAL
                threshold_value = thresholds["critical"]
            elif value < thresholds.get("error", 0):
                alert_level = AlertLevel.ERROR
                threshold_value = thresholds["error"]
            elif value < thresholds.get("warning", 0):
                alert_level = AlertLevel.WARNING
                threshold_value = thresholds["warning"]
        else:
            if value > thresholds.get("critical", float('inf')):
                alert_level = AlertLevel.CRITICAL
                threshold_value = thresholds["critical"]
            elif value > thresholds.get("error", float('inf')):
                alert_level = AlertLevel.ERROR
                threshold_value = thresholds["error"]
            elif value > thresholds.get("warning", float('inf')):
                alert_level = AlertLevel.WARNING
                threshold_value = thresholds["warning"]
        
        if alert_level:
            alert = Alert(
                level=alert_level,
                metric_type=MetricType(metric_name) if metric_name in [m.value for m in MetricType] else MetricType.ACCURACY,
                message=f"{metric_name} {comparison == 'less' and 'below' or 'above'} threshold: {value:.4f} vs {threshold_value}",
                value=value,
                threshold=threshold_value
            )
            
            with self.lock:
                self.alerts.append(alert)
            
            for handler in self.handlers:
                try:
                    handler(alert)
                except Exception as e:
                    logger.error(f"告警处理器执行失败: {e}")
            
            return alert
        
        return None
    
    def get_active_alerts(self) -> List[Alert]:
        """获取活跃告警"""
        with self.lock:
            return [a for a in self.alerts if not a.resolved]
    
    def resolve_alert(self, alert_index: int):
        """解决告警"""
        with self.lock:
            if 0 <= alert_index < len(self.alerts):
                self.alerts[alert_index].resolved = True
                self.alerts[alert_index].resolved_at = datetime.now()


class IntentMonitor:
    """意图检测监控器"""
    
    def __init__(self, collector: Optional[MetricsCollector] = None, alert_manager: Optional[AlertManager] = None):
        self.collector = collector or MetricsCollector()
        self.alert_manager = alert_manager or AlertManager()
        
        self.evaluation_results: Dict[str, EvaluationResult] = {}
        self.detection_history: List[Dict[str, Any]] = []
        self.max_history = 10000
        
        self._start_time = datetime.now()
        self._total_detections = 0
        self._correct_detections = 0
        self._failed_detections = 0
        self._total_latency_ms = 0.0
    
    def record_detection(
        self,
        predicted_intent: str,
        actual_intent: Optional[str],
        confidence: float,
        latency_ms: float,
        method: str,
        success: bool,
        session_id: Optional[str] = None
    ):
        """记录检测结果"""
        self._total_detections += 1
        self._total_latency_ms += latency_ms
        
        if success:
            self._correct_detections += 1
        else:
            self._failed_detections += 1
        
        self.collector.record("detection_latency_ms", latency_ms, {"method": method})
        self.collector.record("detection_confidence", confidence, {"intent": predicted_intent})
        
        if actual_intent is not None:
            is_correct = predicted_intent == actual_intent
            self.collector.record("detection_accuracy", 1.0 if is_correct else 0.0)
            
            if predicted_intent not in self.evaluation_results:
                self.evaluation_results[predicted_intent] = EvaluationResult(intent_type=predicted_intent)
            result = self.evaluation_results[predicted_intent]
            if is_correct:
                result.true_positives += 1
            else:
                result.false_positives += 1
                if actual_intent in self.evaluation_results:
                    self.evaluation_results[actual_intent].false_negatives += 1
                else:
                    self.evaluation_results[actual_intent] = EvaluationResult(intent_type=actual_intent)
                    self.evaluation_results[actual_intent].false_negatives += 1
        
        self.detection_history.append({
            "timestamp": datetime.now().isoformat(),
            "predicted": predicted_intent,
            "actual": actual_intent,
            "confidence": confidence,
            "latency_ms": latency_ms,
            "method": method,
            "success": success,
            "session_id": session_id
        })
        
        if len(self.detection_history) > self.max_history:
            self.detection_history = self.detection_history[-self.max_history:]
        
        self._check_alerts()
    
    def _check_alerts(self):
        """检查告警条件"""
        if self._total_detections % 100 == 0:
            accuracy = self._correct_detections / self._total_detections if self._total_detections > 0 else 0
            self.alert_manager.check_and_alert("accuracy", accuracy, "less")
        
        if self._total_detections > 0:
            avg_latency = self._total_latency_ms / self._total_detections
            self.alert_manager.check_and_alert("latency_ms", avg_latency, "greater")
        
        if self._total_detections > 0:
            error_rate = self._failed_detections / self._total_detections
            self.alert_manager.check_and_alert("error_rate", error_rate, "greater")
    
    def get_real_time_stats(self) -> Dict[str, Any]:
        """获取实时统计"""
        uptime = (datetime.now() - self._start_time).total_seconds()
        
        return {
            "uptime_seconds": uptime,
            "total_detections": self._total_detections,
            "correct_detections": self._correct_detections,
            "failed_detections": self._failed_detections,
            "accuracy": self._correct_detections / self._total_detections if self._total_detections > 0 else 0,
            "error_rate": self._failed_detections / self._total_detections if self._total_detections > 0 else 0,
            "average_latency_ms": self._total_latency_ms / self._total_detections if self._total_detections > 0 else 0,
            "throughput_per_second": self._total_detections / uptime if uptime > 0 else 0
        }
    
    def get_latency_stats(self, window_minutes: int = 5) -> Dict[str, float]:
        """获取延迟统计"""
        return self.collector.get_aggregated("detection_latency_ms", window_minutes)
    
    def get_confidence_stats(self, window_minutes: int = 5) -> Dict[str, float]:
        """获取置信度统计"""
        return self.collector.get_aggregated("detection_confidence", window_minutes)
    
    def get_per_intent_metrics(self) -> Dict[str, Dict[str, float]]:
        """获取每个意图的指标"""
        metrics = {}
        for intent_type, result in self.evaluation_results.items():
            metrics[intent_type] = {
                "precision": result.precision,
                "recall": result.recall,
                "f1_score": result.f1_score,
                "accuracy": result.accuracy,
                "true_positives": result.true_positives,
                "false_positives": result.false_positives,
                "false_negatives": result.false_negatives
            }
        return metrics
    
    def get_evaluation_report(self) -> Dict[str, Any]:
        """获取评估报告"""
        per_intent = self.get_per_intent_metrics()
        
        total_tp = sum(r.true_positives for r in self.evaluation_results.values())
        total_fp = sum(r.false_positives for r in self.evaluation_results.values())
        total_fn = sum(r.false_negatives for r in self.evaluation_results.values())
        
        macro_precision = statistics.mean([m["precision"] for m in per_intent.values()]) if per_intent else 0
        macro_recall = statistics.mean([m["recall"] for m in per_intent.values()]) if per_intent else 0
        macro_f1 = statistics.mean([m["f1_score"] for m in per_intent.values()]) if per_intent else 0
        
        micro_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
        micro_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        micro_f1 = 2 * micro_precision * micro_recall / (micro_precision + micro_recall) if (micro_precision + micro_recall) > 0 else 0
        
        return {
            "summary": {
                "total_detections": self._total_detections,
                "correct_detections": self._correct_detections,
                "accuracy": self._correct_detections / self._total_detections if self._total_detections > 0 else 0,
                "macro_precision": macro_precision,
                "macro_recall": macro_recall,
                "macro_f1": macro_f1,
                "micro_precision": micro_precision,
                "micro_recall": micro_recall,
                "micro_f1": micro_f1
            },
            "latency_stats": self.get_latency_stats(),
            "confidence_stats": self.get_confidence_stats(),
            "per_intent_metrics": per_intent,
            "active_alerts": len(self.alert_manager.get_active_alerts()),
            "timestamp": datetime.now().isoformat()
        }
    
    def export_history(self, filepath: str):
        """导出历史记录"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.detection_history, f, ensure_ascii=False, indent=2)
        logger.info(f"检测历史已导出到: {filepath}")
    
    def reset(self):
        """重置监控数据"""
        self.evaluation_results.clear()
        self.detection_history.clear()
        self._total_detections = 0
        self._correct_detections = 0
        self._failed_detections = 0
        self._total_latency_ms = 0
        self._start_time = datetime.now()
        self.collector.clear()


class IntentEvaluator:
    """意图检测评估器"""
    
    def __init__(self, monitor: Optional[IntentMonitor] = None):
        self.monitor = monitor or IntentMonitor()
        self.test_cases: List[Dict[str, Any]] = []
    
    def add_test_case(
        self,
        message: str,
        expected_intent: str,
        expected_params: Optional[Dict[str, Any]] = None,
        description: str = ""
    ):
        """添加测试用例"""
        self.test_cases.append({
            "message": message,
            "expected_intent": expected_intent,
            "expected_params": expected_params or {},
            "description": description
        })
    
    def load_test_cases(self, filepath: str):
        """加载测试用例"""
        with open(filepath, 'r', encoding='utf-8') as f:
            cases = json.load(f)
            for case in cases:
                self.add_test_case(
                    case["message"],
                    case["expected_intent"],
                    case.get("expected_params"),
                    case.get("description", "")
                )
    
    def run_evaluation(
        self,
        detector,
        verbose: bool = False
    ) -> Dict[str, Any]:
        """
        运行评估
        
        Args:
            detector: 意图检测器实例
            verbose: 是否输出详细信息
            
        Returns:
            评估结果
        """
        results = []
        correct = 0
        total = len(self.test_cases)
        
        for case in self.test_cases:
            start_time = time.time()
            result = detector.detect(case["message"])
            latency_ms = (time.time() - start_time) * 1000
            
            predicted_intent = result.intent_type if hasattr(result, 'intent_type') else result.action
            expected_intent = case["expected_intent"]
            is_correct = predicted_intent == expected_intent
            
            if is_correct:
                correct += 1
            
            self.monitor.record_detection(
                predicted_intent=predicted_intent,
                actual_intent=expected_intent,
                confidence=result.confidence,
                latency_ms=latency_ms,
                method=result.method.value if hasattr(result.method, 'value') else str(result.method),
                success=is_correct
            )
            
            results.append({
                "message": case["message"],
                "expected": expected_intent,
                "predicted": predicted_intent,
                "confidence": result.confidence,
                "latency_ms": latency_ms,
                "correct": is_correct
            })
            
            if verbose:
                status = "✓" if is_correct else "✗"
                logger.info(f"{status} '{case['message']}' -> {predicted_intent} (expected: {expected_intent})")
        
        return {
            "total": total,
            "correct": correct,
            "accuracy": correct / total if total > 0 else 0,
            "results": results,
            "report": self.monitor.get_evaluation_report()
        }
    
    def generate_report(self, output_path: Optional[str] = None) -> str:
        """生成评估报告"""
        report = self.monitor.get_evaluation_report()
        
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        
        return json.dumps(report, ensure_ascii=False, indent=2)


def create_monitor(collector: Optional[MetricsCollector] = None, alert_manager: Optional[AlertManager] = None) -> IntentMonitor:
    """创建监控器"""
    return IntentMonitor(collector=collector, alert_manager=alert_manager)


def create_evaluator(monitor: Optional[IntentMonitor] = None) -> IntentEvaluator:
    """创建评估器"""
    return IntentEvaluator(monitor=monitor)


_default_monitor: Optional[IntentMonitor] = None


def get_default_monitor() -> IntentMonitor:
    """获取默认监控器"""
    global _default_monitor
    if _default_monitor is None:
        _default_monitor = create_monitor()
    return _default_monitor
