# Isolated training worker

Training uses the SQLite-backed Worker mode by default. The public API remains
the only frontend endpoint: it validates requests, inserts durable jobs, and
streams persisted events. GPU model loading and training run in a separate
process.

## Start locally

Run these in separate terminals from the repository root:

```bash
uv run python -m uvicorn server.main:app --host 127.0.0.1 --port 8010
uv run python -m server.training_worker
```

On Windows, `start.bat` and `start-backend.bat` start the Worker automatically.
`start-training-worker.bat` starts only the Worker.

Docker Compose starts `training-worker` as a dependency of `api` and mounts the
same `data`, `models`, `datasets`, and `outputs` directories into both
containers.

## Runtime contract

- `POST /training/start` writes a `queued` job; it never loads a model.
- The Worker atomically claims one job and renews a SQLite lease.
- Progress is appended to `training_events`, and structured training logs are
  appended to `training_logs`; V2 SSE supports replay through
  `Last-Event-ID` after API restarts.
- Cancellation is durable. A running Worker observes `cancel_requested` and
  asks the training pipeline to stop safely.
- An expired lease is requeued until `TRAINING_WORKER_MAX_ATTEMPTS` is reached;
  the final state is then `interrupted`.
- A recovered attempt selects the latest valid Trainer checkpoint when one is
  available.

Worker health and queue state are exposed by `GET /training/queue/status`.

## Backends

The Worker dispatches jobs by the `backend` field stored on each durable job:

- `native` (default): runs the in-repo `training_thread` pipeline on the
  Worker process. Loads the model and dataset via `TrainingConfigInput`.
- `swift`: runs the SWIFT (阿里 SWIFT 框架) CLI subprocess via
  `SwiftBackend.start_training`. The Worker polls `get_training_status`
  every 2s and forwards `cancel_event` to `backend.stop_training()`.

A job's backend is chosen at enqueue time by the orchestrator based on
the request's `method` and the `/training/check-swift` availability
probe. Unknown backends fall back to `self.executor` (default
`_execute_native`), preserving backward compatibility for custom
executor injection in tests.

## SSE authentication

Training SSE streams (`GET /training/progress/stream`,
`GET /training/v2/events/stream`) are authenticated via
`services.training.policy.authenticate_training_sse`:

- `ENABLE_AUTH=false` (default in dev/tests): no auth, returns `None`.
- `ENABLE_AUTH=true`: requires a JWT bearer token via either
  - `?token=<jwt>` query param (primary — `EventSource` API cannot set
    custom headers), or
  - `Authorization: Bearer <jwt>` header (for non-browser clients like curl).

Missing or invalid token → `HTTPException(401)`. The same pattern applies
to training WebSocket endpoints via `authenticate_training_websocket`.

## Watchdog configuration

The in-pipeline watchdog monitors heartbeat staleness and force-stops
hung training. Thresholds are configurable in `Settings`:

```text
TRAINING_WATCHDOG_STALL_SECONDS=300    # warn + emit training_stall_detected
TRAINING_WATCHDOG_TIMEOUT_SECONDS=600  # force request_stop()
TRAINING_CLEANUP_TIMEOUT_SECONDS=60    # cleanup thread join timeout
```

Defaults match the historical hardcoded values (300/600/60). When
`cleanup_thread.join(timeout)` times out, the pipeline sets
`cleanup_dangled = True` (observable via `pipeline.cleanup_dangled`) and
logs an ERROR; GPU memory may leak until the next process restart.

## API recover loop

In Worker mode, the API process runs `_training_recover_loop`
(lifespan.py) with the following strategy:

- Every 60s, query `repository.worker_status(stale_after_seconds=2 * lease_seconds)`.
- If at least one Worker is `online`, do nothing — the Worker self-heals
  via `recover_expired()` in its own poll loop. This avoids racing with
  the Worker on lease recovery.
- If no alive Worker is observed, call `repository.recover_expired()` to
  hard-requeue expired leases (final state `interrupted` after
  `TRAINING_WORKER_MAX_ATTEMPTS`).

This guards against the scenario where the Worker process dies and
never restarts, leaving running jobs stuck in `leased`/`running` forever.

## Cleanup dangled

When the training pipeline's cleanup thread (which releases GPU memory
and finalizes checkpoints) does not finish within
`TRAINING_CLEANUP_TIMEOUT_SECONDS`, the pipeline sets
`cleanup_dangled = True` and continues rather than blocking the Worker
poll loop. The Worker can observe this flag via
`pipeline.cleanup_dangled` (property) and log/metric accordingly.

This is a graceful-degradation path: the dangled cleanup thread
continues running in the background (it is a daemon thread), but the
Worker is free to claim the next job. A subsequent process restart
will hard-release any leaked GPU memory.

## Compatibility mode

Set `TRAINING_EXECUTION_MODE=in_process` to use the legacy daemon-thread queue.
This is an explicit fallback and does not provide GPU process isolation.

Useful settings:

```text
TRAINING_EXECUTION_MODE=worker
TRAINING_WORKER_POLL_SECONDS=1
TRAINING_WORKER_HEARTBEAT_SECONDS=5
TRAINING_WORKER_LEASE_SECONDS=30
TRAINING_WORKER_MAX_ATTEMPTS=3
TRAINING_WORKER_STALE_SECONDS=30
```
