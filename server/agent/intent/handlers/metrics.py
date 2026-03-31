"""
意图检测处理器 - 性能指标

收集和分析意图检测的性能指标
"""
import logging
import threading
import time
from typing import Any

from ..models import DetectionMethod, DetectionMetrics

logger = logging.getLogger(__name__)


class MetricsHandler:
    """性能指标处理器"""

    def __init__(self):
        self._metrics = DetectionMetrics()
        self._lock = threading.Lock()
        self._start_time: float | None = None

    def start_timer(self):
        self._start_time = time.time()

    def stop_timer(self) -> float:
        if self._start_time is None:
            return 0.0

        elapsed_ms = (time.time() - self._start_time) * 1000
        self._start_time = None
        return elapsed_ms

    def record_success(
        self,
        method: DetectionMethod,
        intent_type: str,
        confidence: float,
        response_time_ms: float | None = None,
        is_correct: bool | None = None
    ):
        with self._lock:
            if response_time_ms is None:
                response_time_ms = self.stop_timer()

            self._metrics.record_detection(
                method=method,
                intent_type=intent_type,
                confidence=confidence,
                response_time_ms=response_time_ms,
                is_correct=is_correct
            )

    def record_failure(self, response_time_ms: float | None = None, is_false_negative: bool = True):
        with self._lock:
            if response_time_ms is None:
                response_time_ms = self.stop_timer()

            self._metrics.record_failure(response_time_ms, is_false_negative=is_false_negative)

    def get_metrics(self) -> dict[str, Any]:
        with self._lock:
            return self._metrics.get_report()

    def reset(self):
        with self._lock:
            self._metrics.reset()

    def get_success_rate(self) -> float:
        with self._lock:
            if self._metrics.total_requests == 0:
                return 0.0
            return self._metrics.successful_detections / self._metrics.total_requests

    def get_average_response_time(self) -> float:
        with self._lock:
            return self._metrics.total_response_time_ms

    def get_method_distribution(self) -> dict[str, float]:
        with self._lock:
            total = sum(self._metrics.method_usage.values())
            if total == 0:
                return {}

            return {
                method: count / total
                for method, count in self._metrics.method_usage.items()
            }

    def get_intent_distribution(self) -> dict[str, int]:
        with self._lock:
            return dict(self._metrics.intent_distribution)

    def get_confidence_distribution(self) -> dict[str, int]:
        with self._lock:
            return dict(self._metrics.confidence_distribution)

    def log_summary(self):
        metrics = self.get_metrics()
        logger.info(f"意图检测指标摘要: {metrics}")


metrics_handler = MetricsHandler()
