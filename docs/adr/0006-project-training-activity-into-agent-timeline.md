# ADR-0006: Project Training Activity into the Agent Timeline

## Status

Accepted

## Context

The platform already has task modes, persisted Agent sessions, training proposal validation, approval-gated submission, SQLite-backed training execution, and run summaries. The remaining product gap is that these capabilities surface mainly as generic tool calls. Building a second training-agent application would duplicate lifecycle, recovery, approval, and observability logic.

The product is single-machine-first but must preserve contracts that can later operate with PostgreSQL and Redis adapters.

## Decision

Keep Agent Session as the sole conversational runtime and project training proposal/submission/run information into stable, display-safe Agent timeline activity. Persist the projection with the session, use the existing DeepAgents interrupt path for approval, and treat `agent_training` plus the training worker as authoritative for state.

Do not introduce a second orchestration engine, database, queue service, or frontend-owned training state machine.

## Consequences

### Positive

- Coding and training share one task narrative, recovery path, and Workbench.
- Refresh recovery uses persisted parts rather than transient client state.
- Stable identifiers and DTOs preserve a future storage/queue migration seam.
- Personal deployment keeps its SQLite and local-GPU operational profile.

### Negative

- The Agent timeline protocol gains training-specific projection fields.
- Backend and frontend must version and test the projection together.
- Long-running training remains dependent on the separate local worker process.

### Neutral

- Existing generic tool activity remains the fallback for old sessions and unknown payloads.
- Training pages remain available as specialist operational views, not the primary Agent journey.

## Alternatives Considered

- A separate training-agent route was rejected because it fragments the unified Workbench and duplicates lifecycle logic.
- Raw generic tool JSON was rejected because it cannot provide a dependable proposal, approval, and run-status experience.
- Immediate PostgreSQL and Redis adoption was rejected because it adds operational cost before team-scale demand exists.

