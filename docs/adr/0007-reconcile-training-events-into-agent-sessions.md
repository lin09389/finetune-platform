# ADR-0007: Reconcile Training Events into Agent Sessions

## Status

Accepted

## Context

Agent training submissions and safe timeline cards exist, but later Worker progress appears only when the model explicitly calls the summary tool. The training worker owns durable jobs/events, while Agent Session owns conversation parts/events. Direct cross-domain writes would couple their schemas and failure boundaries.

The personal deployment must retain SQLite and low operations, while preserving an adapter seam for a future team deployment.

## Decision

Persist ownership-bound Agent-to-training links and run one control-plane reconciler that consumes task-scoped training events by monotonically increasing sequence. Reconcile into one stable Agent timeline part and publish through existing Agent SSE.

Define event-source and link-repository boundaries. The local adapters use existing SQLite stores. Do not make the Worker write Agent tables and do not make the browser authoritative for training state.

## Consequences

### Positive

- Refresh and restart recover authoritative progress.
- Replays are idempotent and do not create duplicate cards.
- Worker and Agent schemas remain independently owned.
- Team storage/queue adapters can replace local implementations later.

### Negative

- The API process owns a lightweight reconciliation loop.
- Progress latency is bounded by the local polling interval.
- Link/cursor persistence adds a small schema and lifecycle surface.

### Neutral

- Existing training SSE and specialist Training page remain available.
- SQLite remains the default and requires its existing busy-timeout/retry discipline.

## Alternatives Considered

- Worker dual-write was rejected because it couples the execution plane to Agent persistence and authorization.
- Browser polling was rejected because it cannot provide durable offline/restart reconciliation.
- Redis pub/sub was rejected because it adds operational cost before team-scale deployment is required.

