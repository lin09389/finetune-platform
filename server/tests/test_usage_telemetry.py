from __future__ import annotations


def test_usage_facade_records_aggregates_without_sensitive_payloads():
    from core.telemetry import LocalTelemetryRegistry
    from core.usage_telemetry import UsageTelemetry

    registry = LocalTelemetryRegistry(max_series=16)
    usage = UsageTelemetry(registry)

    usage.record_usage(
        component="agent",
        provider="local",
        input_tokens=12,
        output_tokens=34,
        outcome="success",
    )
    payload = registry.render_prometheus()

    assert 'finetune_usage_events_total{component="agent",outcome="success",provider="local"} 1' in payload
    assert 'finetune_usage_input_tokens_total{component="agent",outcome="success",provider="local"} 12' in payload
    assert 'finetune_usage_output_tokens_total{component="agent",outcome="success",provider="local"} 34' in payload
    assert "prompt" not in payload
    assert "session" not in payload


def test_usage_facade_normalizes_unbounded_dimensions_and_rejects_negative_tokens():
    from core.telemetry import LocalTelemetryRegistry
    from core.usage_telemetry import UsageTelemetry

    registry = LocalTelemetryRegistry(max_series=16)
    usage = UsageTelemetry(registry)

    usage.record_usage(component="untrusted-component", provider="untrusted-provider", input_tokens=0, output_tokens=0)
    payload = registry.render_prometheus()

    assert 'component="other"' in payload
    assert 'provider="other"' in payload

    try:
        usage.record_usage(component="agent", provider="local", input_tokens=-1)
    except ValueError as exc:
        assert "non-negative" in str(exc)
    else:
        raise AssertionError("negative token totals must be rejected")
