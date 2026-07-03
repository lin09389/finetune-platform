# ADR-0003: Isolate local inference behind an authenticated HTTP provider

## Status

Accepted

## Context

The platform already exposes an OpenAI-compatible API, but the routes, runtime
bootstrap, evaluation jobs, model-runtime management, and shutdown lifecycle
still import the in-process scheduler. A CUDA OOM or native backend crash can
therefore terminate the public API and Agent workspace.

The platform is local-first and maintained by one developer. The frontend must
keep one public API URL, and the design must not require Redis, Kafka,
Kubernetes, or a second database.

## Non-functional requirements

- A local inference crash or OOM must not terminate the control-plane API.
- Existing `/v1/models`, `/v1/chat/completions`, `/inference`, and
  `/model-runtime` callers remain compatible through the control-plane proxy.
- Streaming must preserve SSE framing and cancellation.
- Internal traffic is authenticated and the native service is loopback or
  container-network only.
- Connect failures, timeouts, retries, capability discovery, and error codes
  are observable and deterministic.
- Cloud fallback is opt-in and only activates for transport/service
  unavailability, never for invalid user requests.

## Decision

- Run the existing scheduler and local backends only in
  `python -m server.inference_server`.
- Keep the current OpenAI-compatible execution routes as the native service
  contract.
- Register HTTP proxy routes in the public control plane when
  `INFERENCE_EXECUTION_MODE=service` (the default).
- Route evaluation and local Agent providers through the same authenticated
  HTTP provider.
- Keep `INFERENCE_EXECUTION_MODE=in_process` as an explicit compatibility mode.
- Publish a separate `/internal/capabilities` contract for backend/model
  features and runtime limits.
- Bind the native process to `127.0.0.1` for local launches. Docker exposes it
  only on the Compose network and publishes no host port.

## Consequences

### Positive

- GPU/native crashes are isolated from Agent, Chat, Workspace, and job APIs.
- All local inference consumers share one timeout, retry, auth, and error
  contract.
- Existing frontend URLs do not change.

### Negative

- Local inference requires one additional process.
- Streaming proxy cancellation and two-process diagnostics add code paths.
- Agent tool calling remains limited by the selected local model/backend
  capability and is reported explicitly rather than assumed.

### Neutral

- Models and deployment artifacts remain shared filesystem resources.
- Cloud providers remain control-plane integrations and are not hosted by the
  local inference process.

## Failure modes and mitigation

- Connect refused / process crash: bounded retry, stable 503 envelope, optional
  cloud fallback.
- Read timeout: cancel upstream response and return/emit `inference_timeout`.
- Invalid internal key: native service returns 401; the control plane never
  forwards the user's bearer token internally.
- Mid-stream failure: emit an OpenAI error SSE event without a successful
  `[DONE]` marker.
- OOM: native process may fail or die; the control API remains healthy.

## Alternatives considered

**Keep scheduler in the public API** — rejected because it preserves the OOM
failure domain.

**Expose Ollama/vLLM directly to every consumer** — rejected because retry,
auth, capabilities, and error semantics would diverge.

**Introduce a message broker** — rejected because interactive token streaming
is naturally HTTP/SSE and a broker adds unnecessary operations.

## References

- `docs/adr/0002-isolate-training-worker-with-sqlite-leases.md`
- `server/api/inference/openai_routes.py`
- `server/inference_provider/`
- `server/inference_server/`
