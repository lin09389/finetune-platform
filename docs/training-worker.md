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
