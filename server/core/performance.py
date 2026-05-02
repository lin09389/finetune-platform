"""性能监控模块 - 收集和分析本地推理性能指标。"""
import logging
import statistics
import threading
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


def _round(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"avg": None, "min": None, "max": None, "p95": None}

    p95 = None
    if len(values) >= 20:
        try:
            p95 = statistics.quantiles(values, n=20)[-1]
        except statistics.StatisticsError:
            p95 = None

    return {
        "avg": _round(statistics.mean(values)),
        "min": _round(min(values)),
        "max": _round(max(values)),
        "p95": _round(p95),
    }


@dataclass
class PerformanceMetrics:
    """单次推理指标。"""

    tokens_per_second: float
    latency_ms: float
    first_token_latency_ms: float
    vram_used_gb: float
    model_id: str
    engine_type: str
    batch_size: int = 1
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    load_duration_ms: float = 0.0
    queue_wait_ms: float = 0.0
    memory_used_gb: float = 0.0
    memory_peak_gb: float = 0.0
    cpu_percent: float = 0.0
    gpu_util_percent: float = 0.0
    retry_count: int = 0
    fallback_used: bool = False
    cache_hit: bool = False
    warmup: bool = False
    cancelled: bool = False
    error_type: str | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class StreamingMetrics:
    """单次流式推理指标。"""

    total_tokens: int
    total_time_ms: float
    first_token_latency_ms: float = 0.0
    avg_chunk_latency_ms: float = 0.0
    max_chunk_latency_ms: float = 0.0
    min_chunk_latency_ms: float = 0.0
    backpressure_events: int = 0
    queue_wait_ms: float = 0.0
    load_duration_ms: float = 0.0
    model_id: str = ""
    engine_type: str = ""
    retry_count: int = 0
    cancelled: bool = False
    fallback_used: bool = False
    timestamp: float = field(default_factory=time.time)


class PerformanceMonitor:
    """线程安全的推理性能监控器。"""

    def __init__(self, max_history: int = 1000):
        self._history: list[PerformanceMetrics] = []
        self._streaming_history: list[StreamingMetrics] = []
        self._max_history = max_history
        self._lock = threading.Lock()

        self._request_count = 0
        self._error_count = 0
        self._cancel_count = 0
        self._fallback_count = 0
        self._cache_hit_count = 0
        self._retry_count = 0
        self._start_time = time.time()

    def record(self, metrics: PerformanceMetrics) -> None:
        """记录单次推理指标。"""
        with self._lock:
            self._history.append(metrics)
            if len(self._history) > self._max_history:
                self._history.pop(0)
            self._request_count += 1
            self._retry_count += metrics.retry_count
            if metrics.cancelled:
                self._cancel_count += 1
            if metrics.fallback_used:
                self._fallback_count += 1
            if metrics.cache_hit:
                self._cache_hit_count += 1
            if metrics.error_type:
                self._error_count += 1

    def record_streaming(self, metrics: StreamingMetrics) -> None:
        """记录流式推理指标。"""
        with self._lock:
            self._streaming_history.append(metrics)
            if len(self._streaming_history) > self._max_history:
                self._streaming_history.pop(0)
            self._retry_count += metrics.retry_count
            if metrics.cancelled:
                self._cancel_count += 1
            if metrics.fallback_used:
                self._fallback_count += 1

    def record_error(self) -> None:
        """兼容旧接口：记录一次错误。"""
        with self._lock:
            self._error_count += 1

    def get_stats(self, model_id: str | None = None) -> dict[str, Any]:
        """获取推理统计。"""
        with self._lock:
            history = self._history.copy()
            total_requests = self._request_count
            error_count = self._error_count
            cancel_count = self._cancel_count
            fallback_count = self._fallback_count
            cache_hit_count = self._cache_hit_count
            retry_count = self._retry_count

        if model_id:
            history = [m for m in history if m.model_id == model_id]

        if not history:
            payload = {
                "total_requests": total_requests,
                "error_count": error_count,
                "cancel_count": cancel_count,
                "fallback_count": fallback_count,
                "cache_hit_count": cache_hit_count,
                "retry_count": retry_count,
                "uptime_seconds": _round(time.time() - self._start_time),
            }
            if model_id:
                payload["message"] = f"No data for model: {model_id}"
            return payload

        return {
            "total_requests": total_requests,
            "error_count": error_count,
            "cancel_count": cancel_count,
            "fallback_count": fallback_count,
            "cache_hit_count": cache_hit_count,
            "retry_count": retry_count,
            "uptime_seconds": _round(time.time() - self._start_time),
            "requests_in_history": len(history),
            "tokens_per_second": _summary([m.tokens_per_second for m in history]),
            "latency_ms": _summary([m.latency_ms for m in history]),
            "first_token_latency_ms": _summary([m.first_token_latency_ms for m in history]),
            "load_duration_ms": _summary([m.load_duration_ms for m in history]),
            "queue_wait_ms": _summary([m.queue_wait_ms for m in history]),
            "batch_size": _summary([float(m.batch_size) for m in history]),
            "memory_used_gb": _summary([m.memory_used_gb for m in history]),
            "memory_peak_gb": _summary([m.memory_peak_gb for m in history]),
            "vram_usage_gb": _summary([m.vram_used_gb for m in history]),
            "cpu_percent": _summary([m.cpu_percent for m in history]),
            "gpu_util_percent": _summary([m.gpu_util_percent for m in history]),
            "model_distribution": dict(Counter(m.model_id for m in history)),
            "engine_distribution": dict(Counter(m.engine_type for m in history)),
            "error_distribution": dict(Counter(m.error_type for m in history if m.error_type)),
        }

    def get_streaming_stats(self, model_id: str | None = None) -> dict[str, Any]:
        """获取流式推理统计。"""
        with self._lock:
            history = self._streaming_history.copy()

        if model_id:
            history = [m for m in history if m.model_id == model_id]

        if not history:
            return {"message": "No streaming data available", "total_streaming_requests": 0}

        return {
            "total_streaming_requests": len(history),
            "first_token_latency_ms": _summary([m.first_token_latency_ms for m in history]),
            "total_time_ms": _summary([m.total_time_ms for m in history]),
            "avg_chunk_latency_ms": _summary([m.avg_chunk_latency_ms for m in history]),
            "queue_wait_ms": _summary([m.queue_wait_ms for m in history]),
            "load_duration_ms": _summary([m.load_duration_ms for m in history]),
            "total_tokens": sum(m.total_tokens for m in history),
            "total_backpressure_events": sum(m.backpressure_events for m in history),
            "engine_distribution": dict(Counter(m.engine_type for m in history if m.engine_type)),
        }

    def get_recommendations(self, vram_total_gb: float | None = None) -> list[dict[str, Any]]:
        """基于近期推理记录给出本地优化建议。"""
        with self._lock:
            history = self._history.copy()
            streaming_history = self._streaming_history.copy()

        if not history:
            return [{"type": "info", "message": "暂无性能数据，请先进行本地推理采样"}]

        recommendations: list[dict[str, Any]] = []
        avg_tps = statistics.mean([m.tokens_per_second for m in history])
        avg_ttft = statistics.mean([m.first_token_latency_ms for m in history])
        avg_vram = statistics.mean([m.vram_used_gb for m in history])
        avg_queue_wait = statistics.mean([m.queue_wait_ms for m in history])
        avg_load_duration = statistics.mean([m.load_duration_ms for m in history])
        avg_batch = statistics.mean([m.batch_size for m in history])
        engines = Counter(m.engine_type for m in history)

        if avg_ttft > 500:
            recommendations.append(
                {
                    "type": "warning",
                    "message": "首字延迟较高，建议启用模型预热并优先使用量化本地后端。",
                    "action": "对本地模型启用 warmup，并为 4-8GB 设备优先选择 llama-cpp 或 HuggingFace 4bit",
                }
            )

        if avg_tps < 20:
            recommendations.append(
                {
                    "type": "warning",
                    "message": "推理速度较低，建议接入动态批处理或降低生成长度。",
                    "action": "启用 DynamicBatcher，或下调 max_tokens / num_ctx",
                }
            )

        if avg_queue_wait > 80:
            recommendations.append(
                {
                    "type": "warning",
                    "message": "请求排队时间偏高，建议调小并发、提升线程数或启用队列可视化。",
                    "action": "根据硬件画像自动调整 batch size 与线程池",
                }
            )

        if avg_load_duration > 500:
            recommendations.append(
                {
                    "type": "warning",
                    "message": "模型冷启动较慢，建议保持热模型或启用预热。",
                    "action": "对常用模型保持租约或预热最小 prompt",
                }
            )

        if vram_total_gb and avg_vram > vram_total_gb * 0.85:
            recommendations.append(
                {
                    "type": "error",
                    "message": "显存使用率过高，建议切换更低量化等级或减少 GPU offload。",
                    "action": "优先 INT4 / GGUF，必要时降低 n_gpu_layers 或 batch_size",
                }
            )

        if engines.get("llama-cpp", 0) == 0 and vram_total_gb and vram_total_gb <= 8:
            recommendations.append(
                {
                    "type": "info",
                    "message": "当前设备属于低显存档位，建议优先尝试 llama-cpp + GGUF。",
                    "action": "切换到 llama-cpp 后端并使用 GGUF 模型",
                }
            )

        if avg_batch <= 1.0 and len(history) >= 10:
            recommendations.append(
                {
                    "type": "info",
                    "message": "当前大多为单请求执行，可尝试启用动态批处理以提高整体吞吐。",
                    "action": "开启 enable_batching 并设置合理的 max_batch_wait_ms",
                }
            )

        if streaming_history:
            avg_stream_ttft = statistics.mean([m.first_token_latency_ms for m in streaming_history])
            if avg_stream_ttft > avg_ttft * 1.2:
                recommendations.append(
                    {
                        "type": "warning",
                        "message": "流式链路首字延迟高于非流式，建议检查流式包装和背压策略。",
                        "action": "减少 SSE 缓冲并优先首字直出",
                    }
                )

        if not recommendations:
            recommendations.append({"type": "success", "message": "本地推理性能表现稳定，可继续扩大采样范围。"})

        return recommendations

    def export_prometheus(self) -> str:
        """导出 Prometheus 文本格式指标。"""
        stats = self.get_stats()
        streaming = self.get_streaming_stats()
        lines = [
            "# HELP finetune_inference_requests_total Total local inference requests.",
            "# TYPE finetune_inference_requests_total counter",
            f"finetune_inference_requests_total {stats.get('total_requests', 0)}",
            "# HELP finetune_inference_errors_total Total local inference errors.",
            "# TYPE finetune_inference_errors_total counter",
            f"finetune_inference_errors_total {stats.get('error_count', 0)}",
            "# HELP finetune_inference_cancellations_total Total local inference cancellations.",
            "# TYPE finetune_inference_cancellations_total counter",
            f"finetune_inference_cancellations_total {stats.get('cancel_count', 0)}",
            "# HELP finetune_inference_fallbacks_total Total fallback usages.",
            "# TYPE finetune_inference_fallbacks_total counter",
            f"finetune_inference_fallbacks_total {stats.get('fallback_count', 0)}",
            "# HELP finetune_inference_ttft_ms_avg Average time to first token in ms.",
            "# TYPE finetune_inference_ttft_ms_avg gauge",
            f"finetune_inference_ttft_ms_avg {stats.get('first_token_latency_ms', {}).get('avg') or 0}",
            "# HELP finetune_inference_tps_avg Average tokens per second.",
            "# TYPE finetune_inference_tps_avg gauge",
            f"finetune_inference_tps_avg {stats.get('tokens_per_second', {}).get('avg') or 0}",
            "# HELP finetune_inference_queue_wait_ms_avg Average queue wait in ms.",
            "# TYPE finetune_inference_queue_wait_ms_avg gauge",
            f"finetune_inference_queue_wait_ms_avg {stats.get('queue_wait_ms', {}).get('avg') or 0}",
            "# HELP finetune_inference_stream_requests_total Total streaming requests.",
            "# TYPE finetune_inference_stream_requests_total counter",
            f"finetune_inference_stream_requests_total {streaming.get('total_streaming_requests', 0)}",
            "# HELP finetune_inference_stream_ttft_ms_avg Average streaming TTFT in ms.",
            "# TYPE finetune_inference_stream_ttft_ms_avg gauge",
            f"finetune_inference_stream_ttft_ms_avg {streaming.get('first_token_latency_ms', {}).get('avg') or 0}",
        ]
        return "\n".join(lines) + "\n"

    def get_recent_history(self) -> list[dict[str, Any]]:
        """返回最近推理记录，用于基线脚本或调试。"""
        with self._lock:
            return [asdict(entry) for entry in self._history]

    def clear_history(self) -> None:
        """清空历史记录。"""
        with self._lock:
            self._history.clear()
            self._streaming_history.clear()
            self._request_count = 0
            self._error_count = 0
            self._cancel_count = 0
            self._fallback_count = 0
            self._cache_hit_count = 0
            self._retry_count = 0
            self._start_time = time.time()


_performance_monitor: PerformanceMonitor | None = None
_monitor_lock = threading.Lock()


def get_performance_monitor() -> PerformanceMonitor:
    """获取性能监控器实例。"""
    global _performance_monitor
    with _monitor_lock:
        if _performance_monitor is None:
            _performance_monitor = PerformanceMonitor()
        return _performance_monitor
