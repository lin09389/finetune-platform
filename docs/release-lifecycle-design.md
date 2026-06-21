# Release Lifecycle Redesign

## Objective

Turn the training, comparison, evaluation, inference, and deployment pages into one
evidence-backed release lifecycle. A release may become active only when the exact
artifact evaluated is the exact artifact served.

## Core invariants

1. Training produces an immutable release manifest with content hashes for the
   source dataset, held-out evaluation snapshot, and final model artifact.
2. Training-linked evaluation uses the held-out snapshot, never the training
   source dataset. An explicitly selected independent dataset is also allowed.
3. Deployment requires a minimum sample count, sufficient score coverage, no
   relative quality regression, and matching artifact content.
4. Creating a deployment package does not make it live. Packages move through
   `draft -> active -> inactive`; only one active package may own an alias.
5. Inference resolves active aliases only. Model leases are never force-unloaded
   while requests are in flight.

## Data flow

```text
dataset source
  -> deterministic raw split
  -> tokenized train/eval split
  -> held-out raw evaluation_snapshot.json
  -> training artifact + artifact_manifest.json
  -> evaluation run with provenance and artifact digest
  -> quality gate
  -> deployment draft
  -> health check
  -> activation / deactivation / rollback
  -> active inference alias
```

## Operational trade-offs

The current HuggingFace backend is process-local and stateful. The scheduler
therefore serializes incompatible runtime variants and waits for active leases
instead of trying to serve multiple variants from one mutable backend instance.
True same-backend parallelism should later be implemented as a backend-instance
pool keyed by model path, adapter digest, quantization, and runtime policy.

JSON release files remain for compatibility and portability. They now carry an
explicit state machine and audit trail. Moving the release registry to SQLite is
the next persistence step once legacy JSON migration is introduced.

## Frontend

The deployment page becomes a release control console with:

- a four-stage lifecycle rail;
- release creation based on training and evaluation IDs;
- version history with draft, active, and inactive states;
- quality evidence and artifact identity;
- health, activation, deactivation, and rollback controls;
- code examples and environment configuration.

Visual reference: `docs/design/release-console-concept.png`.

## Verification

- Unit tests for deterministic held-out snapshots and content hashes.
- Gate tests for provenance, sample count, score coverage, and regressions.
- Scheduler concurrency test proving active leases cannot be unloaded.
- Deployment lifecycle tests proving draft aliases are not served.
- Typecheck, frontend build, backend unit/integration tests, and browser QA.
