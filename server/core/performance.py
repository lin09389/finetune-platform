"""
性能监控模块 - 收集和分析推理性能指标
"""
import logging
import statistics
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """性能指标数据类"""
    tokens_per_second: float
    latency_ms: float
    first_token_latency_ms: float
    vram_used_gb: float
    model_id: str
    engine_type: str
    batch_size: int = 1
    timestamp: float = field(default_factory=time.time)


@dataclass
class StreamingMetrics:
    """流式输出指标"""
    total_tokens: int
    total_time_ms: float
    avg_chunk_latency_ms: float
    max_chunk_latency_ms: float
    min_chunk_latency_ms: float
    backpressure_events: int = 0


class PerformanceMonitor:
    """
    性能监控器
    
    功能：
    - 收集推理性能指标
    - 计算统计数据
    - 提供优化建议
    """

    def __init__(self, max_history: int = 1000):
        self._history: list[PerformanceMetrics] = []
        self._streaming_history: list[StreamingMetrics] = []
        self._max_history = max_history
        self._lock = threading.Lock()

        self._request_count = 0
        self._error_count = 0
        self._start_time = time.time()

    def record(self, metrics: PerformanceMetrics) -> None:
        """记录性能指标"""
        with self._lock:
            self._history.append(metrics)
            if len(self._history) > self._max_history:
                self._history.pop(0)
            self._request_count += 1

    def record_streaming(self, metrics: StreamingMetrics) -> None:
        """记录流式输出指标"""
        with self._lock:
            self._streaming_history.append(metrics)
            if len(self._streaming_history) > self._max_history:
                self._streaming_history.pop(0)

    def record_error(self) -> None:
        """记录错误"""
        with self._lock:
            self._error_count += 1

    def get_stats(self, model_id: str | None = None) -> dict[str, Any]:
        """获取性能统计"""
        with self._lock:
            history = self._history.copy()

        if not history:
            return {
                "total_requests": self._request_count,
                "error_count": self._error_count,
                "uptime_seconds": time.time() - self._start_time,
            }

        if model_id:
            history = [m for m in history if m.model_id == model_id]

        if not history:
            return {"message": f"No data for model: {model_id}"}

        tokens_per_second = [m.tokens_per_second for m in history]
        latencies = [m.latency_ms for m in history]
        first_token_latencies = [m.first_token_latency_ms for m in history]
        vram_usage = [m.vram_used_gb for m in history]

        return {
            "total_requests": self._request_count,
            "error_count": self._error_count,
            "uptime_seconds": round(time.time() - self._start_time, 2),
            "requests_in_history": len(history),
            "tokens_per_second": {
                "avg": round(statistics.mean(tokens_per_second), 2),
                "min": round(min(tokens_per_second), 2),
                "max": round(max(tokens_per_second), 2),
                "p95": round(statistics.quantiles(tokens_per_second, n=20)[-1], 2) if len(tokens_per_second) >= 20 else None,
            },
            "latency_ms": {
                "avg": round(statistics.mean(latencies), 2),
                "min": round(min(latencies), 2),
                "max": round(max(latencies), 2),
                "p95": round(statistics.quantiles(latencies, n=20)[-1], 2) if len(latencies) >= 20 else None,
            },
            "first_token_latency_ms": {
                "avg": round(statistics.mean(first_token_latencies), 2),
                "min": round(min(first_token_latencies), 2),
                "max": round(max(first_token_latencies), 2),
            },
            "vram_usage_gb": {
                "avg": round(statistics.mean(vram_usage), 2),
                "max": round(max(vram_usage), 2),
            },
            "engine_distribution": self._get_engine_distribution(history),
        }

    def get_streaming_stats(self) -> dict[str, Any]:
        """获取流式输出统计"""
        with self._lock:
            history = self._streaming_history.copy()

        if not history:
            return {"message": "No streaming data available"}

        chunk_latencies = [m.avg_chunk_latency_ms for m in history]

        return {
            "total_streaming_requests": len(history),
            "avg_chunk_latency_ms": round(statistics.mean(chunk_latencies), 2) if chunk_latencies else 0,
            "total_backpressure_events": sum(m.backpressure_events for m in history),
        }

    def get_recommendations(self, vram_total_gb: float | None = None) -> list[dict[str, Any]]:
        """获取优化建议"""
        recommendations = []

        with self._lock:
            history = self._history.copy()

        if not history:
            return [{"type": "info", "message": "暂无性能数据，请先进行推理"}]

        avg_tps = statistics.mean([m.tokens_per_second for m in history])
        avg_latency = statistics.mean([m.first_token_latency_ms for m in history])
        avg_vram = statistics.mean([m.vram_used_gb for m in history])

        if avg_tps < 20:
            recommendations.append({
                "type": "warning",
                "message": "推理速度较低，建议启用 vLLM 引擎或 Flash Attention 2",
                "action": "设置 INFERENCE_ENGINE=vllm 或 ENABLE_FLASH_ATTENTION=true"
            })

        if avg_latency > 500:
            recommendations.append({
                "type": "warning",
                "message": "首字延迟较高，建议使用量化模型或减少 max_tokens",
                "action": "使用 GPTQ/AWQ 量化模型"
            })

        if vram_total_gb and avg_vram > vram_total_gb * 0.9:
            recommendations.append({
                "type": "error",
                "message": "显存使用率过高，可能导致 OOM",
                "action": "启用量化或减少 batch_size"
            })

        if avg_tps > 50:
            recommendations.append({
                "type": "success",
                "message": "推理性能良好"
            })

        return recommendations

    def _get_engine_distribution(self, history: list[PerformanceMetrics]) -> dict[str, int]:
        """获取引擎使用分布"""
        distribution: dict[str, int] = {}
        for m in history:
            distribution[m.engine_type] = distribution.get(m.engine_type, 0) + 1
        return distribution

    def clear_history(self) -> None:
        """清空历史记录"""
        with self._lock:
            self._history.clear()
            self._streaming_history.clear()
            self._request_count = 0
            self._error_count = 0
            self._start_time = time.time()


_performance_monitor: PerformanceMonitor | None = None
_monitor_lock = threading.Lock()


def get_performance_monitor() -> PerformanceMonitor:
    """获取性能监控器实例"""
    global _performance_monitor
    with _monitor_lock:
        if _performance_monitor is None:
            _performance_monitor = PerformanceMonitor()
        return _performance_monitor
