from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_registry_renders_low_cardinality_prometheus_004_metrics():
    from core.telemetry import LocalTelemetryRegistry, PROMETHEUS_CONTENT_TYPE

    registry = LocalTelemetryRegistry(max_series=8)
    registry.record_http_request(method="GET", status_code=200, duration_seconds=0.125, profile="agent")

    payload = registry.render_prometheus()

    assert "# TYPE finetune_http_requests_total counter" in payload
    assert 'finetune_http_requests_total{method="GET",profile="agent",status_code="200"} 1' in payload
    assert 'finetune_http_request_duration_seconds_sum{method="GET",profile="agent",status_code="200"} 0.125' in payload
    assert PROMETHEUS_CONTENT_TYPE == "text/plain; version=0.0.4; charset=utf-8"
    assert "path=" not in payload
    assert "correlation_id=" not in payload
    assert "user_id=" not in payload


def test_registry_bounds_series_and_is_thread_safe():
    from core.telemetry import LocalTelemetryRegistry

    registry = LocalTelemetryRegistry(max_series=2)

    def record(index: int) -> None:
        registry.record_counter("test_events_total", {"kind": str(index)}, 1)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(record, range(100)))

    payload = registry.render_prometheus()
    assert payload.count("test_events_total{") <= 2
    assert "finetune_telemetry_dropped_series_total 98" in payload


def test_metrics_route_is_available_from_common_behavior_for_every_profile():
    from apps.factory import _register_common_behavior
    from apps.profiles import ApplicationProfile

    app = FastAPI()
    app.state.profile = "agent"
    _register_common_behavior(app, ApplicationProfile.AGENT)

    response = TestClient(app).get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
    assert "finetune_http_requests_total" in response.text
