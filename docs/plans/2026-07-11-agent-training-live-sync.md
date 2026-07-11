# Agent Training Live Sync Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically reconcile authoritative local training progress into one persisted Agent Workbench card with refresh/restart recovery.

**Architecture:** A persisted ownership-bound link joins Agent sessions to training tasks. A lifespan-managed control-plane reconciler reads task-scoped SQLite training events through an interface, advances an idempotent cursor, updates one safe Agent part, and publishes via existing Agent SSE. The browser only renders validated projections.

**Tech Stack:** Python 3.11, asyncio, SQLite, FastAPI lifespan, Pydantic, React 18, TypeScript, Ant Design, pytest, Vitest.

---

## Parallel Track A: Backend Link and Reconciler

**Owned files:**
- Create: `server/agent_session/training_run_sync.py`
- Modify: `server/agent_session/repository.py`
- Modify: `server/agent_session/training_tools.py`
- Modify: `server/agent_training/models.py`
- Modify: `server/apps/lifespan.py`
- Test: `server/tests/test_agent_training_live_sync.py`
- Test: `server/tests/test_agent_session_training_tools.py`
- Test: `server/tests/test_agent_training_models.py`

### Task A1: Persist ownership-bound task links

1. Write failing SQLite tests for unique task/proposal binding, owner/session checks, stable part identity, cursor monotonicity, and terminal lookup.
2. Run the focused test and confirm failure.
3. Add the minimal link schema/repository methods with indexes and compare-and-advance semantics.
4. Run the test and commit.

### Task A2: Define the event-source seam and safe progress projection

1. Write failing tests for ordered events, replay, unknown event, negative/invalid metrics, terminal summary, missing job, and path/worker-id redaction.
2. Add `TrainingEventSource`, the local SQLite adapter, and optional allowlisted progress fields to `run_summary` activity.
3. Never persist raw event payloads; construct a new DTO from allowlisted values.
4. Run model/sync tests and commit.

### Task A3: Reconcile and recover

1. Write failing tests proving approved submission creates one link/card and replay/restart updates that same part.
2. Implement one bounded, cancellable reconciler with backoff and explicit `start()`/`close()`.
3. Register it in the Agent/combined lifespan only; do not start it in the Finetune-only profile.
4. Preserve existing HITL and duplicate submission behavior.
5. Run focused tests and commit.

**Verification:**

```powershell
.\.venv\Scripts\python.exe -m pytest server/tests/test_agent_training_live_sync.py server/tests/test_agent_session_training_tools.py server/tests/test_agent_training_models.py server/tests/test_application_profiles.py -q
```

## Parallel Track B: Live Workbench Progress and Handoff

**Owned files:**
- Modify: `client/src/agent/protocol/agentProtocol.ts`
- Modify: `client/src/agent/components/AgentTrainingActivity.tsx`
- Modify: `client/src/agent/workbench/AgentWorkbench.module.css`
- Test: `client/src/test/AgentFrontendFoundation.test.tsx`
- Test: `client/src/test/AgentWorkbenchRuntime.test.tsx`

### Task B1: Decode the additive progress contract

1. Add failing tests for valid metrics, partial/indeterminate progress, terminal artifact availability, invalid numbers, unknown fields, and generic fallback.
2. Extend narrow guards using `elapsed_time` and other documented snake_case fields.
3. Clamp presentation values without changing the authoritative status.
4. Run focused tests and commit.

### Task B2: Render live progress accessibly

1. Add failing tests for queued/loading/running/completed/failed/missing/degraded states.
2. Add accessible progress, phase, loss, ETA, last-update, and safe artifact handoff to the existing card.
3. Avoid timers per card; use persisted timestamps and existing render cadence.
4. Respect reduced motion and narrow layouts.
5. Run tests, typecheck, build, and commit.

**Verification:**

```powershell
cd client
npx vitest run src/test/AgentFrontendFoundation.test.tsx src/test/AgentWorkbenchRuntime.test.tsx
npm run typecheck
npm run build
```

## Parallel Track C: Recovery and Idempotency Acceptance

**Owned files:**
- Create: `server/tests/fixtures/agent_training_live_sync.json`
- Create: `server/tests/test_agent_training_live_sync_acceptance.py`
- Create: `client/src/agent/testing/agentTrainingLiveScenarios.ts`
- Create: `client/src/test/AgentTrainingLiveSync.test.tsx`
- Modify: `docs/agent-training-foundation.md`

### Task C1: Freeze recovery scenarios

1. Define deterministic scenarios for ordered progress, duplicate replay, API restart cursor recovery, refresh recovery, Worker outage/recovery, missing job grace, cross-user rejection, terminal completion, and safe artifact handoff.
2. Add CPU-only backend acceptance tests using temporary SQLite/fakes.
3. Add frontend scenario projections that assert stable card identity and monotonic progress presentation.
4. Document failure meanings and a local manual smoke procedure.
5. Run only new acceptance tests and commit; do not edit Track A/B implementation files.

## Main-thread integration gate

1. Review every commit for file ownership, raw path/log leakage, cursor races, task/session ownership, and lifecycle cleanup.
2. Integrate A before B/C when required by contract dependencies.
3. Resolve conflicts only in the main thread.
4. Upgrade fixture-only assertions to production integration assertions where possible.
5. Run backend Agent/training/Worker/lifespan suites, frontend Agent suites, typecheck, production build, bundle budget, and `git diff --check`.
6. Record actual commits and verification totals here.

