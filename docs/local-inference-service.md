# Isolated local inference service

Local inference runs outside the public API process by default. The React and
Electron clients still use only `http://127.0.0.1:8010`; the control plane
proxies the existing inference URLs to the private native service.

## Local startup

```bash
uv run python -m server.inference_server
uv run python -m server.training_worker
uv run python -m uvicorn server.main:app --host 127.0.0.1 --port 8010
```

The inference service defaults to `127.0.0.1:8020`. Do not bind it to a public
interface outside a private container network. Windows launchers start all
three backend processes automatically; `start-inference-service.bat` starts
only the inference process.

## Contracts

- `GET /v1/models`
- `POST /v1/chat/completions` (sync and SSE)
- `GET /internal/capabilities`
- Legacy `/inference`, `/model-runtime`, and `/inference-engine` URLs remain
  available through the public API proxy.

Every native request except `/health` requires:

```text
Authorization: Bearer ${INFERENCE_INTERNAL_API_KEY}
```

Set a non-default key in production. The control plane removes any user bearer
token before adding the internal credential.

## Reliability and fallback

Connect and read timeouts, retry count, and exponential retry delay are
configurable with `INFERENCE_SERVICE_*` settings. Mid-stream disconnects emit
an OpenAI error SSE event and never emit a false successful `[DONE]`.

Cloud fallback is opt-in:

```text
INFERENCE_CLOUD_FALLBACK_ENABLED=true
INFERENCE_CLOUD_FALLBACK_PROVIDER=<saved provider id>
INFERENCE_CLOUD_FALLBACK_MODEL=<cloud model id>
```

Fallback is used only when the local service is unavailable or returns 503.
Validation and authentication failures are never hidden by fallback.

Set `INFERENCE_EXECUTION_MODE=in_process` only for compatibility or focused
tests; it removes process-level OOM isolation.
