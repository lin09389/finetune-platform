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

## Production Entry

`/agent` is the only Agent product surface and the default application entry. There is no rollout flag or legacy fallback. `/chat` is intentionally limited to ordinary conversational inference and must not import Agent Session orchestration.

Session-level diagnostic details remain in bounded, versioned browser storage. The backend receives only hashed-session aggregate counters in SQLite. Platform-wide summaries require administrator access.

## Verification

- `npm run typecheck`
- `npm run test:agent-foundation`
- `npx vitest run --testTimeout=15000`
- `npm run build`
- Backend Agent Session, DeepAgents, execution plan, permission, recovery, workspace, async-task, and terminal contract tests
- Browser verification of create, prompt, SSE state, model failure, node recovery, refresh restoration, desktop layout, and mobile layout
