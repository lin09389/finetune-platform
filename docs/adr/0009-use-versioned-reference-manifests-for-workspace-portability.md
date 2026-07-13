# ADR-0009: Use versioned reference manifests for Workspace portability

## Status

Accepted

## Context

Workspace is the long-lived product boundary for Coding Agent, Training Assistant and Hybrid work. Users need to move that boundary between machines while retaining local ownership and the low-operations SQLite/local-GPU experience. Copying application databases would couple the public migration format to internal tables. Bundling source trees, datasets, model weights and checkpoints would create large, sensitive archives and conflict with Git and existing resource managers.

Agent sessions also contain authority-bearing and machine-specific state: approvals, session tool trust, shell/model capability facts and DeepAgents checkpoints. Restoring that state as runnable execution would let a package carry authority from another machine.

## Decision

Use a strict, versioned, reference-only `.ftworkspace` archive as the portable contract.

The archive contains an allowlisted manifest, safe task continuation summaries, typed resource references and SHA-256 checksums. It excludes source content, large resource bytes, secrets, raw terminal output, full diffs, approval grants, session tool trust and runtime checkpoints.

Import is two-phase: inspect validates an untrusted archive without mutation; commit creates a new local Workspace after explicit project/resource binding. Imported tasks are read-only continuation contexts. Continuing a task always creates a new Agent Session under current local policy.

The manifest domain depends on provider Protocols rather than SQLite rows or FastAPI requests so future PostgreSQL and object-store adapters can implement the same contract.

## Consequences

### Positive

- Archives stay small, auditable and safe to back up.
- The public format survives internal SQLite/PostgreSQL migrations.
- Coding and training context share one Workspace narrative.
- Authority and executable runtime state do not cross machines.
- Missing resources can be repaired explicitly instead of silently misresolved.

### Negative

- Import requires user-visible resource rebinding.
- An imported task cannot resume at the exact LangGraph node.
- Task summaries and resource providers need explicit stable schemas.

### Neutral

- SQLite remains the local runtime source of truth.
- A future signed archive may add authenticity; v1 checksums provide integrity, not publisher identity.

## Alternatives Considered

**Bundle the whole project and resources** — rejected because of archive size, source/data leakage and duplication of Git/model/dataset storage.

**Export the SQLite database and runtime directories** — rejected because it exposes internal schema, migrates stale authority and blocks storage-adapter evolution.

**Manifest JSON without a container** — rejected because task contexts and per-entry integrity become awkward; the bounded ZIP container remains simple while retaining a strict allowlist.

## References

- `docs/plans/2026-07-10-personal-ai-engineer-agent-product-design.md`
- `docs/plans/2026-07-10-single-node-team-ready-architecture-evolution-design.md`
- `docs/adr/0008-persist-snapshot-diffs-for-coding-review.md`
- `docs/plans/2026-07-13-workspace-portability-design.md`
