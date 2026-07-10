# Local-First Observability

The backend exposes a small, process-local observability foundation. It does not require Prometheus, OpenTelemetry, a database, or any external service. Restarting the process clears all aggregates.

## Request correlation and logs

Every app profile accepts `X-Correlation-Id`. For backwards compatibility, an inbound `X-Trace-Id` becomes the correlation ID when `X-Correlation-Id` is absent. Both `X-Correlation-Id` and `X-Trace-Id` are returned on a successful response and identify the same request. Values with characters outside `[A-Za-z0-9._-]` or more than 128 characters are replaced with a generated UUID.

The request middleware resets all context variables in `finally`, including when the wrapped application raises. Request-completion logs contain only these structured fields:

- `correlation_id`
- `http_method`
- `http_status_code`
- `duration_ms`
- `application_profile`

It deliberately does not log the route/path, query string, request body, prompts, user/session/request identifiers, or authorization material.

## Metrics

`GET /metrics` is public and available in the `combined`, `agent`, and `finetune` profiles. It returns `text/plain; version=0.0.4; charset=utf-8`.

| Metric | Type | Labels |
| --- | --- | --- |
| `finetune_http_requests_total` | counter | `method`, `profile`, `status_code` |
| `finetune_http_request_duration_seconds_sum` / `_count` | summary components | `method`, `profile`, `status_code` |
| `finetune_usage_events_total` | counter | `component`, `provider`, `outcome` |
| `finetune_usage_input_tokens_total` | counter | `component`, `provider`, `outcome` |
| `finetune_usage_output_tokens_total` | counter | `component`, `provider`, `outcome` |
| `finetune_telemetry_dropped_series_total` | counter | none |

All labels are fixed low-cardinality values. The registry also has a process-wide maximum number of stored series, set by `OBSERVABILITY_MAX_SERIES` (default `256`, range `16`–`4096`). A new series after the limit is discarded and counted by `finetune_telemetry_dropped_series_total`; existing series continue to update. No path, prompt, token content, user/session/request ID, or authorization data can be used as a telemetry label.

The existing inference-specific metrics endpoints remain separate and unchanged.

## Usage facade

Future Agent, training, and model-provider code should use the safe facade:

```python
from core.usage_telemetry import record_usage

record_usage(
    component="agent",
    provider="local",
    input_tokens=120,
    output_tokens=45,
    outcome="success",
)
```

The facade stores no events. It emits only counters through the local registry and normalizes unknown component, provider, and outcome values to `other`. It has no parameters for prompts, sessions, paths, request IDs, user IDs, model payloads, or authorization data. Token totals must be non-negative.
