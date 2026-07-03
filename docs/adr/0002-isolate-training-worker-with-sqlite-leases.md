# ADR-0002: Isolate training execution with a durable SQLite worker queue

## Status

Accepted

## Context

Training currently runs in daemon threads owned by the FastAPI process. A CUDA
OOM, process crash, or API restart can therefore interrupt both training and
interactive Agent/Chat traffic. Queue state is partly stored in JSON and V2
events are process-local, so another process cannot reliably claim work, replay
progress, or continue cancellation handling.

The platform is local-first and maintained by one developer. It needs process
isolation and restart recovery without introducing Redis, Kafka, Celery, or a
distributed deployment requirement.

## Decision

- Store training jobs, events, worker registrations, leases, and cancellation
  intent in the existing SQLite application database.
- Make `worker` the default training execution mode. Keep `in_process` as an
  explicit compatibility mode, not an automatic silent fallback.
- Run GPU training in `python -m server.training_worker`.
- Claim one job atomically with `BEGIN IMMEDIATE`; renew its lease and worker
  heartbeat while training runs.
- Requeue jobs whose worker lease expires, up to a bounded attempt count. Mark
  exhausted jobs interrupted rather than pretending they completed.
- Persist the existing V2 event envelope and use the database sequence for SSE
  replay across API and Worker restarts.
- Keep models, datasets, outputs, TrainingRecord JSON, and the existing training
  engine formats unchanged.

## Consequences

### Positive

- API and Agent traffic survive a training Worker crash or GPU OOM.
- Jobs and progress survive API restarts.
- Cancellation and recovery are observable and auditable.
- SQLite keeps single-machine setup and operations simple.

### Negative

- Training now requires a Worker process in the default mode.
- SQLite remains a single-machine coordination mechanism.
- Existing TrainingState remains inside the Worker for engine compatibility,
  while the durable repository becomes authoritative for API status.

### Neutral

- The in-process queue remains available only when explicitly configured.
- SWIFT training remains on its existing backend process path until it adopts
  the same durable executor contract.

## Alternatives Considered

**Keep daemon threads** — rejected because it does not provide fault isolation.

**Celery/Redis** — rejected for now because it adds services and operational
cost without improving the single-machine target enough to justify them.

**Spawn one subprocess per HTTP request** — rejected because it lacks durable
claiming, replay, bounded recovery, and centralized cancellation semantics.

## References

- `server/apps/` application profiles
- `server/core/training_queue.py` legacy in-process queue
- `server/core/training_events_v2.py` V2 event contract
