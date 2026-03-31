# Client `/agent/*` Endpoint Migration Status (2026-03-31)

## Scope
Scanned `client/src/**/*.ts` and `client/src/**/*.tsx` for `/agent/` references.

## Active Endpoints (Aligned)
- `/agent/detect-intent`
- `/agent/detect-intent-multi`
- `/agent/execute`
- `/agent/chat-execute`
- `/agent/capabilities`

## Compatibility Wrappers (Deprecated but Supported)
- `getAgentAuditStats()`
  - old logical target: `/agent/audit/stats` (removed)
  - compatibility target: `/agent-executor/stats`
- `getAgentAuditRecent(limit)`
  - old logical target: `/agent/audit/recent` (removed)
  - compatibility target: `/agent-executor/audit-log`
- `extractParams()`
  - compatibility target: `/agent/detect-intent`
- `evaluateIntentConfidence()`
  - compatibility target: `/agent/detect-intent`

## UI Components
- `IntentClarification.tsx`
  - uses `/api/agent/detect-intent-multi`
  - clarification is now client-side (no backend `/agent/clarification/*` dependency)
- `useAgentExecutor.ts` / `chatStore.ts`
  - use `/agent/chat-execute`

## Remaining Work
- Optional: remove deprecated wrappers after call sites are cleaned and telemetry confirms zero usage.
