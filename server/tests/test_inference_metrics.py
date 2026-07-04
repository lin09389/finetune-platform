import os
import sys

import pytest
from fastapi.testclient import TestClient

server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)

from core.performance import PerformanceMetrics, PerformanceMonitor, StreamingMetrics
from api.inference import routes as inference_routes
from api.device import get_device_info
from main import app

pytestmark = pytest.mark.usefixtures("inference_in_process")


def test_performance_monitor_exposes_extended_stats():
    monitor = PerformanceMonitor()
    monitor.record(
        PerformanceMetrics(
            tokens_per_second=42.0,
            latency_ms=300.0,
            first_token_latency_ms=120.0,
            vram_used_gb=3.5,
            model_id="llama.gguf",
            engine_type="llama-cpp",
            prompt_tokens=30,
            completion_tokens=60,
            total_tokens=90,
            load_duration_ms=80.0,
            queue_wait_ms=12.0,
            memory_used_gb=8.0,
            memory_peak_gb=8.5,
            cpu_percent=32.0,
            retry_count=1,
            cache_hit=True,
        )
    )
    monitor.record_streaming(
        StreamingMetrics(
            total_tokens=60,
            total_time_ms=900.0,
            first_token_latency_ms=110.0,
            avg_chunk_latency_ms=25.0,
            max_chunk_latency_ms=40.0,
            min_chunk_latency_ms=10.0,
            model_id="llama.gguf",
            engine_type="llama-cpp",
            load_duration_ms=80.0,
        )
    )

    stats = monitor.get_stats()
    streaming = monitor.get_streaming_stats()

    assert stats["cache_hit_count"] == 1
    assert stats["retry_count"] == 1
    assert stats["load_duration_ms"]["avg"] == 80.0
    assert stats["queue_wait_ms"]["avg"] == 12.0
    assert stats["engine_distribution"]["llama-cpp"] == 1
    assert streaming["load_duration_ms"]["avg"] == 80.0
    assert streaming["engine_distribution"]["llama-cpp"] == 1


def test_performance_monitor_exports_prometheus():
    monitor = PerformanceMonitor()
    monitor.record(
        PerformanceMetrics(
            tokens_per_second=25.0,
            latency_ms=200.0,
            first_token_latency_ms=90.0,
            vram_used_gb=2.0,
            model_id="test-model",
            engine_type="huggingface",
        )
    )
    payload = monitor.export_prometheus()
    assert "finetune_inference_requests_total 1" in payload
    assert "finetune_inference_ttft_ms_avg" in payload


def test_cache_status_uses_sync_scheduler_stats(monkeypatch):
    class FakeScheduler:
        def get_stats(self):
            return {"loaded_models": 1, "default_backend": "huggingface"}

    monkeypatch.setattr(inference_routes, "get_scheduler", lambda: FakeScheduler())

    client = TestClient(app)
    response = client.get("/inference/cache/status")
    assert response.status_code == 200
    assert response.json()["loaded_models"] == 1
    assert "offline_cache" in response.json()


def test_device_info_contains_hardware_profile():
    info = get_device_info()
    assert "hardware_profile" in info
    profile = info["hardware_profile"]
    assert "recommended_backend" in profile
    assert "recommended_quantization" in profile


def test_metrics_alias_returns_prometheus_text():
    client = TestClient(app)
    response = client.get("/inference/metrics")
    assert response.status_code == 200
    assert "finetune_inference_requests_total" in response.text


def test_clear_performance_history_resets_counters():
    monitor = inference_routes.get_performance_monitor()
    monitor.record(
        PerformanceMetrics(
            tokens_per_second=10.0,
            latency_ms=150.0,
            first_token_latency_ms=80.0,
            vram_used_gb=1.0,
            model_id="demo-model",
            engine_type="huggingface",
        )
    )

    client = TestClient(app)
    response = client.post("/inference/performance/clear")

    assert response.status_code == 200
    assert response.json()["message"] == "推理性能历史已清除"
    assert monitor.get_stats()["total_requests"] == 0
