# ADR 0008: Persist snapshot-based diffs for Coding Agent review

- Status: Accepted
- Date: 2026-07-11
- Deciders: Project owner and architecture coordination thread

## Context

The Coding Agent already snapshots files before writes for trajectory enforcement and static-validation rollback. Successful edits, however, do not necessarily create a durable diff artifact. A Git-only implementation would exclude non-Git workspaces and cannot reliably separate pre-existing user changes from Agent changes.

The product is single-machine-first, must preserve SQLite-backed recovery, and must not introduce a second approval or execution loop beside DeepAgents.

## Decision

After a workspace write succeeds and post-write static validation passes, the trajectory middleware will derive a bounded unified diff from its existing pre-write snapshot and the resulting file content.

Each successful write appends an immutable persisted `diff` part with a versioned payload, workspace-relative path, change kind, line counts, write sequence, truncation/binary indicators, and `review_status: ready`. Binary and oversized edits produce metadata-only records when inline content is unsafe or impractical.

The trajectory completion gate will require persisted diff coverage for every successful write, in addition to the existing final-verification requirement. User acknowledgement is not a completion prerequisite; permissions and approvals continue to use the existing DeepAgents interrupt integration.

The UI will render persisted parts and therefore recover the review surface through the same REST/SSE session projection used by the rest of the Workbench.

## Consequences

### Positive

- Works in Git and non-Git projects, including dirty workspaces.
- Reuses the authoritative write boundary instead of adding a file watcher.
- Survives process and browser restarts through existing SQLite persistence.
- Makes edit-to-diff coverage enforceable and testable.
- Preserves one Agent execution and approval model.

### Negative

- Repeated edits create chronological diff records rather than one task-start aggregate patch.
- Diff payload limits can require a truncated or metadata-only review.
- The repository stores code fragments already present in the local workspace; retention follows session-data retention policy.

## Rejected alternatives

- Shelling out to `git diff`: insufficient for non-Git, untracked, and pre-dirty workspaces.
- Computing diffs only in React: not durable and cannot satisfy backend completion gates.
- Persisting full first-write baselines in session metadata: increases sensitive-data duplication and payload growth.
- Blocking completion on a new review approval state: duplicates existing HITL machinery and harms unattended local workflows.
