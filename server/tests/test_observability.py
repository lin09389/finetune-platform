from __future__ import annotations

import asyncio
import logging

from fastapi import Request
from starlette.responses import Response


def _request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (key.lower().encode("ascii"), value.encode("ascii"))
        for key, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/sensitive/customer-path",
            "headers": raw_headers,
            "client": ("127.0.0.1", 9000),
            "scheme": "http",
            "server": ("testserver", 80),
            "query_string": b"secret=do-not-log",
        }
    )


def test_trace_middleware_accepts_legacy_header_and_resets_context():
    from apps.factory import trace_middleware

    from core.tracing import correlation_id_var, trace_id_var, user_id_var

    async def endpoint(_request):
        assert correlation_id_var.get() == "legacy-trace"
        assert trace_id_var.get() == "legacy-trace"
        assert user_id_var.get() == "anonymous"
        return Response(status_code=204)

    response = asyncio.run(trace_middleware(_request({"X-Trace-Id": "legacy-trace"}), endpoint))

    assert response.headers["X-Trace-Id"] == "legacy-trace"
    assert response.headers["X-Correlation-Id"] == "legacy-trace"
    assert correlation_id_var.get() == ""
    assert trace_id_var.get() == ""
    assert user_id_var.get() == ""


def test_correlation_header_takes_precedence_and_context_resets_on_error():
    from apps.factory import trace_middleware

    from core.tracing import correlation_id_var, trace_id_var

    async def endpoint(_request):
        assert correlation_id_var.get() == "corr-123"
        assert trace_id_var.get() == "corr-123"
        raise RuntimeError("expected")

    try:
        asyncio.run(
            trace_middleware(
                _request({"X-Correlation-Id": "corr-123", "X-Trace-Id": "old-trace"}),
                endpoint,
            )
        )
    except RuntimeError as exc:
        assert str(exc) == "expected"
    else:
        raise AssertionError("trace middleware should preserve endpoint failures")

    assert correlation_id_var.get() == ""
    assert trace_id_var.get() == ""


def test_request_logging_contains_only_safe_structured_fields(caplog):
    from apps.factory import logging_middleware

    from core.tracing import correlation_id_var

    token = correlation_id_var.set("corr-safe")
    try:
        async def endpoint(_request):
            return Response(status_code=202)

        with caplog.at_level(logging.INFO, logger="finetune-platform"):
            response = asyncio.run(logging_middleware(_request(), endpoint))
    finally:
        correlation_id_var.reset(token)

    assert response.headers["X-Process-Time"]
    record = next(record for record in caplog.records if record.getMessage() == "http_request_completed")
    assert record.correlation_id == "corr-safe"
    assert record.http_method == "GET"
    assert record.http_status_code == 202
    assert isinstance(record.duration_ms, float)
    assert not hasattr(record, "path")
    assert not hasattr(record, "user_id")
