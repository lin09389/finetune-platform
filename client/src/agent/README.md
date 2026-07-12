# Agent Frontend

This directory owns the production Agent Workbench. `/agent` is the only Agent product surface and the default application entry.

## Modules

- `attention`: the unified user-intervention model
- `config`: versioned Workbench preferences
- `diagnostics`: bounded per-session browser details and aggregate reporting
- `protocol`: wire-contract types and decoders
- `runtime`: normalized state and reducers
- `transport`: REST/SSE connectivity
- `commands`: user-initiated operations
- `selectors`: UI-facing derived state
- `components`: Agent-owned presentation
- `workbench`: route, responsive shell, and page composition
- `testing`: sanitized event fixtures and canonical Store projections

The Workbench consumes the backend workspace aggregate as its authoritative snapshot and uses SSE for incremental updates and refresh triggers.
User actions pass through the typed command executor so endpoint ordering, idempotency, partial-session recovery, stream restarts, and refresh directives stay outside presentation components.

## Business Contract

Phase 7.5 keeps Coding (Build) and Training (Train/Hybrid) inside the same `/agent`
Workbench. The audited UI owner, action, feedback, recovery, responsive status, and
delivery wave for each existing capability live in
[`docs/frontend-capability-parity-2026-07-12.md`](../../../docs/frontend-capability-parity-2026-07-12.md).
The matching typed regression fixture is `testing/workbenchCapabilityParity.ts` and
must remain a record of existing production ownership, not a second feature registry.
Experimental routes remain application-shell concerns guarded by `/api/info`; they are
not default Workbench task modes.

Every workflow below must remain covered before an Agent change is merged:

| Workflow | Rewrite acceptance |
|---|---|
| Session lifecycle | Create, select, stop, refresh, and restore a session without duplicate work |
| Prompt execution | Submit once and continue execution in a background task |
| Event streaming | Merge snapshots and SSE deltas in order, including reconnects with `since_event_id` |
| Permissions | Resolve each pending approval once and resume outside the HTTP request |
| Failure recovery | Surface tool failures, loop guards, and node recovery with actionable state |
| Subagents | Reflect child running, waiting, failed, cancelled, and completed states in the parent |
| Workspace artifacts | Preserve source links for files, diffs, results, risks, and verification evidence |
| Protocol resilience | Retain unknown events for diagnostics without crashing the workbench |
| Large histories | Remain responsive with 10,000 timeline events |
| High-frequency navigation | Search, filter, pin, and restore sessions; filter timeline records; switch panels from the keyboard |
| Session organization | Persist aliases, pins, and archive visibility through the backend session preference contract with browser fallback for old cached state |
| Attention handling | Resolve approvals in batches and retain a bounded local history of user interventions |
| Edit safety | Preserve prompt drafts, manage multiple open files, warn before discarding edits, and support keyboard save |
| Dense output | Collapse long timeline records, expose terminal text match counts, and keep plan dependencies and timings scannable |
| Responsive operation | Keep every production action reachable on desktop, narrow, and touch-only mobile layouts |

## Production Entry

`/agent` is the only Agent product surface and the default application entry. There is no rollout flag or legacy fallback. `/chat` is intentionally limited to ordinary conversational inference and must not import Agent Session orchestration.

Session-level diagnostic details remain in bounded, versioned browser storage and are visible in Attention Center for the active session. The backend receives only hashed-session aggregate counters in SQLite. Platform-wide summaries require administrator access.

Session aliases, pins, and archive visibility are backend-owned preferences stored with the Agent Session metadata in SQLite and exposed on `AgentSessionResponse.preferences`; browser storage is only a compatibility fallback. Drafts, active panels, and Attention Center history remain versioned browser preferences. Execution plan nodes remain read-only except for the backend-supported recovery command; dependencies, ownership, duration, and recovery attempts are rendered from the authoritative workspace snapshot.

## Verification

- `npm run typecheck`
- `npm run test:agent-foundation`
- `npm run test:agent-e2e`
- `npx vitest run --testTimeout=15000`
- `npm run build`
- Backend Agent Session, DeepAgents, execution plan, permission, recovery, workspace, async-task, and terminal contract tests
- Browser verification of create, prompt, SSE state, model failure, node recovery, refresh restoration, session search, timeline filtering, desktop layout, and mobile drawers
