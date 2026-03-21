"""
批处理和性能监控测试

测试覆盖：
- 性能监控器
- 流式输出指标
- 模型调度器
- 批处理逻辑
"""
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import time
import threading
import asyncio

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.performance import (
    PerformanceMetrics,
    StreamingMetrics,
    PerformanceMonitor,
    get_performance_monitor,
)


class TestPerformanceMetrics:
    """性能指标数据类测试"""

    def test_metrics_creation(self):
        metrics = PerformanceMetrics(
            tokens_per_second=50.5,
            latency_ms=200.0,
            first_token_latency_ms=150.0,
            vram_used_gb=4.5,
            model_id="test_model",
            engine_type="huggingface"
        )
        assert metrics.tokens_per_second == 50.5
        assert metrics.latency_ms == 200.0
        assert metrics.first_token_latency_ms == 150.0
        assert metrics.vram_used_gb == 4.5
        assert metrics.model_id == "test_model"
        assert metrics.engine_type == "huggingface"
        assert metrics.batch_size == 1

    def test_metrics_with_batch_size(self):
        metrics = PerformanceMetrics(
            tokens_per_second=100.0,
            latency_ms=300.0,
            first_token_latency_ms=100.0,
            vram_used_gb=8.0,
            model_id="test_model",
            engine_type="vllm",
            batch_size=4
        )
        assert metrics.batch_size == 4

    def test_metrics_timestamp(self):
        before = time.time()
        metrics = PerformanceMetrics(
            tokens_per_second=50.0,
            latency_ms=100.0,
            first_token_latency_ms=50.0,
            vram_used_gb=4.0,
            model_id="test",
            engine_type="huggingface"
        )
        after = time.time()
        assert before <= metrics.timestamp <= after


class TestStreamingMetrics:
    """流式输出指标测试"""

    def test_streaming_metrics_creation(self):
        metrics = StreamingMetrics(
            total_tokens=100,
            total_time_ms=2000.0,
            avg_chunk_latency_ms=20.0,
            max_chunk_latency_ms=50.0,
            min_chunk_latency_ms=10.0
        )
        assert metrics.total_tokens == 100
        assert metrics.total_time_ms == 2000.0
        assert metrics.avg_chunk_latency_ms == 20.0
        assert metrics.backpressure_events == 0

    def test_streaming_metrics_with_backpressure(self):
        metrics = StreamingMetrics(
            total_tokens=200,
            total_time_ms=4000.0,
            avg_chunk_latency_ms=25.0,
            max_chunk_latency_ms=100.0,
            min_chunk_latency_ms=5.0,
            backpressure_events=3
        )
        assert metrics.backpressure_events == 3


class TestPerformanceMonitor:
    """性能监控器测试"""

    def test_monitor_creation(self):
        monitor = PerformanceMonitor()
        assert monitor._request_count == 0
        assert monitor._error_count == 0
        assert len(monitor._history) == 0

    def test_record_metrics(self):
        monitor = PerformanceMonitor()
        metrics = PerformanceMetrics(
            tokens_per_second=50.0,
            latency_ms=100.0,
            first_token_latency_ms=50.0,
            vram_used_gb=4.0,
            model_id="test_model",
            engine_type="huggingface"
        )
        monitor.record(metrics)
        assert len(monitor._history) == 1
        assert monitor._request_count == 1

    def test_record_multiple_metrics(self):
        monitor = PerformanceMonitor()
        for i in range(10):
            metrics = PerformanceMetrics(
                tokens_per_second=50.0 + i,
                latency_ms=100.0 + i * 10,
                first_token_latency_ms=50.0,
                vram_used_gb=4.0,
                model_id=f"model_{i % 3}",
                engine_type="huggingface"
            )
            monitor.record(metrics)
        assert len(monitor._history) == 10
        assert monitor._request_count == 10

    def test_record_streaming_metrics(self):
        monitor = PerformanceMonitor()
        streaming = StreamingMetrics(
            total_tokens=100,
            total_time_ms=2000.0,
            avg_chunk_latency_ms=20.0,
            max_chunk_latency_ms=50.0,
            min_chunk_latency_ms=10.0
        )
        monitor.record_streaming(streaming)
        assert len(monitor._streaming_history) == 1

    def test_record_error(self):
        monitor = PerformanceMonitor()
        monitor.record_error()
        monitor.record_error()
        assert monitor._error_count == 2

    def test_get_stats_empty(self):
        monitor = PerformanceMonitor()
        stats = monitor.get_stats()
        assert stats["total_requests"] == 0
        assert stats["error_count"] == 0
        assert "uptime_seconds" in stats

    def test_get_stats_with_data(self):
        monitor = PerformanceMonitor()
        for i in range(5):
            metrics = PerformanceMetrics(
                tokens_per_second=50.0 + i * 10,
                latency_ms=100.0 + i * 20,
                first_token_latency_ms=50.0 + i * 5,
                vram_used_gb=4.0 + i * 0.5,
                model_id="test_model",
                engine_type="huggingface"
            )
            monitor.record(metrics)
        
        stats = monitor.get_stats()
        assert stats["total_requests"] == 5
        assert stats["requests_in_history"] == 5
        assert "tokens_per_second" in stats
        assert stats["tokens_per_second"]["avg"] == 70.0

    def test_get_stats_by_model(self):
        monitor = PerformanceMonitor()
        
        for i in range(3):
            monitor.record(PerformanceMetrics(
                tokens_per_second=50.0,
                latency_ms=100.0,
                first_token_latency_ms=50.0,
                vram_used_gb=4.0,
                model_id="model_a",
                engine_type="huggingface"
            ))
        
        for i in range(2):
            monitor.record(PerformanceMetrics(
                tokens_per_second=60.0,
                latency_ms=80.0,
                first_token_latency_ms=40.0,
                vram_used_gb=3.0,
                model_id="model_b",
                engine_type="vllm"
            ))
        
        stats_a = monitor.get_stats(model_id="model_a")
        assert stats_a["requests_in_history"] == 3
        
        stats_b = monitor.get_stats(model_id="model_b")
        assert stats_b["requests_in_history"] == 2

    def test_get_stats_nonexistent_model(self):
        monitor = PerformanceMonitor()
        monitor.record(PerformanceMetrics(
            tokens_per_second=50.0,
            latency_ms=100.0,
            first_token_latency_ms=50.0,
            vram_used_gb=4.0,
            model_id="test_model",
            engine_type="huggingface"
        ))
        
        stats = monitor.get_stats(model_id="nonexistent")
        assert "message" in stats

    def test_get_streaming_stats_empty(self):
        monitor = PerformanceMonitor()
        stats = monitor.get_streaming_stats()
        assert "message" in stats

    def test_get_streaming_stats_with_data(self):
        monitor = PerformanceMonitor()
        for i in range(5):
            monitor.record_streaming(StreamingMetrics(
                total_tokens=100 + i * 10,
                total_time_ms=2000.0,
                avg_chunk_latency_ms=20.0 + i,
                max_chunk_latency_ms=50.0,
                min_chunk_latency_ms=10.0,
                backpressure_events=i
            ))
        
        stats = monitor.get_streaming_stats()
        assert stats["total_streaming_requests"] == 5
        assert stats["total_backpressure_events"] == 10

    def test_get_recommendations_empty(self):
        monitor = PerformanceMonitor()
        recommendations = monitor.get_recommendations()
        assert len(recommendations) == 1
        assert recommendations[0]["type"] == "info"

    def test_get_recommendations_low_speed(self):
        monitor = PerformanceMonitor()
        for i in range(5):
            monitor.record(PerformanceMetrics(
                tokens_per_second=15.0,
                latency_ms=100.0,
                first_token_latency_ms=50.0,
                vram_used_gb=4.0,
                model_id="test",
                engine_type="huggingface"
            ))
        
        recommendations = monitor.get_recommendations()
        assert any(r["type"] == "warning" and "推理速度较低" in r["message"] for r in recommendations)

    def test_get_recommendations_high_latency(self):
        monitor = PerformanceMonitor()
        for i in range(5):
            monitor.record(PerformanceMetrics(
                tokens_per_second=50.0,
                latency_ms=100.0,
                first_token_latency_ms=600.0,
                vram_used_gb=4.0,
                model_id="test",
                engine_type="huggingface"
            ))
        
        recommendations = monitor.get_recommendations()
        assert any(r["type"] == "warning" and "首字延迟较高" in r["message"] for r in recommendations)

    def test_get_recommendations_high_vram(self):
        monitor = PerformanceMonitor()
        for i in range(5):
            monitor.record(PerformanceMetrics(
                tokens_per_second=50.0,
                latency_ms=100.0,
                first_token_latency_ms=50.0,
                vram_used_gb=9.5,
                model_id="test",
                engine_type="huggingface"
            ))
        
        recommendations = monitor.get_recommendations(vram_total_gb=10.0)
        assert any(r["type"] == "error" and "显存使用率过高" in r["message"] for r in recommendations)

    def test_get_recommendations_good_performance(self):
        monitor = PerformanceMonitor()
        for i in range(5):
            monitor.record(PerformanceMetrics(
                tokens_per_second=60.0,
                latency_ms=100.0,
                first_token_latency_ms=100.0,
                vram_used_gb=4.0,
                model_id="test",
                engine_type="vllm"
            ))
        
        recommendations = monitor.get_recommendations()
        assert any(r["type"] == "success" for r in recommendations)

    def test_engine_distribution(self):
        monitor = PerformanceMonitor()
        
        for i in range(3):
            monitor.record(PerformanceMetrics(
                tokens_per_second=50.0,
                latency_ms=100.0,
                first_token_latency_ms=50.0,
                vram_used_gb=4.0,
                model_id="test",
                engine_type="huggingface"
            ))
        
        for i in range(2):
            monitor.record(PerformanceMetrics(
                tokens_per_second=60.0,
                latency_ms=80.0,
                first_token_latency_ms=40.0,
                vram_used_gb=3.0,
                model_id="test",
                engine_type="vllm"
            ))
        
        stats = monitor.get_stats()
        assert stats["engine_distribution"]["huggingface"] == 3
        assert stats["engine_distribution"]["vllm"] == 2

    def test_max_history_limit(self):
        monitor = PerformanceMonitor(max_history=10)
        for i in range(20):
            monitor.record(PerformanceMetrics(
                tokens_per_second=50.0,
                latency_ms=100.0,
                first_token_latency_ms=50.0,
                vram_used_gb=4.0,
                model_id="test",
                engine_type="huggingface"
            ))
        assert len(monitor._history) == 10
        assert monitor._request_count == 20

    def test_clear_history(self):
        monitor = PerformanceMonitor()
        for i in range(5):
            monitor.record(PerformanceMetrics(
                tokens_per_second=50.0,
                latency_ms=100.0,
                first_token_latency_ms=50.0,
                vram_used_gb=4.0,
                model_id="test",
                engine_type="huggingface"
            ))
            monitor.record_error()
        
        monitor.clear_history()
        assert len(monitor._history) == 0
        assert monitor._request_count == 0
        assert monitor._error_count == 0

    def test_thread_safety(self):
        monitor = PerformanceMonitor()
        errors = []
        
        def record_metrics(thread_id):
            try:
                for i in range(100):
                    monitor.record(PerformanceMetrics(
                        tokens_per_second=50.0,
                        latency_ms=100.0,
                        first_token_latency_ms=50.0,
                        vram_used_gb=4.0,
                        model_id=f"model_{thread_id}",
                        engine_type="huggingface"
                    ))
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=record_metrics, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert monitor._request_count == 500


class TestGetPerformanceMonitor:
    """性能监控器单例测试"""

    def test_get_performance_monitor_singleton(self):
        monitor1 = get_performance_monitor()
        monitor2 = get_performance_monitor()
        assert monitor1 is monitor2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
