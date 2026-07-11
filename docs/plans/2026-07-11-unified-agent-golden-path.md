# Unified Agent Golden Path Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver one recoverable Workbench journey from Train/Hybrid task creation through proposal review, explicit approval, single submission, and run-summary display.

**Architecture:** Agent Session remains the sole conversational runtime. The backend emits a persisted, safe training activity projection from authoritative `agent_training` state; the frontend renders it in the existing timeline and falls back to generic tool activity. SQLite, the training worker, and current GPU leases remain unchanged.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, SQLite, DeepAgents, React 18, TypeScript, Ant Design, Vitest, pytest.

---

## Parallel Track A: Backend Training Activity Contract

**Owned files:**
- Modify: `server/agent_training/models.py`
- Modify: `server/agent_session/training_tools.py`
- Modify: `server/agent_session/deepagents_events.py`
- Test: `server/tests/test_agent_training_models.py`
- Test: `server/tests/test_agent_session_training_tools.py`
- Test: `server/tests/test_agent_session_deepagents_events.py`

### Task A1: Define the safe projection

1. Write failing model tests for proposal, submission, and run-summary activity payloads with stable IDs and no secret/local-path leakage.
2. Run the focused model test and confirm failure.
3. Add the smallest discriminated Pydantic projection contract and an explicit safe-field serializer.
4. Run the model test and commit.

### Task A2: Persist projected tool outcomes

1. Write failing tests showing successful `propose_training`, `submit_training`, and `get_training_summary` outcomes create reconstructable activity while malformed/failed output retains generic behavior.
2. Run the focused tests and confirm failure.
3. Add projection metadata to the existing tool-result part/event path without adding a second event bus or approval mechanism.
4. Verify blocked, warning, rejected, stale, duplicate, and missing-run outcomes.
5. Run the three owned test modules and commit.

**Verification:**

```powershell
python -m pytest server/tests/test_agent_training_models.py server/tests/test_agent_session_training_tools.py server/tests/test_agent_session_deepagents_events.py -q
```

Expected: all pass.

## Parallel Track B: Workbench Train/Hybrid Experience

**Owned files:**
- Modify: `client/src/agent/protocol/agentProtocol.ts`
- Create: `client/src/agent/components/AgentTrainingActivity.tsx`
- Modify: `client/src/agent/components/AgentRunTimeline.tsx`
- Modify: `client/src/agent/components/AgentTaskComposer.tsx`
- Modify: `client/src/agent/workbench/AgentWorkbench.module.css`
- Test: `client/src/test/AgentFrontendFoundation.test.tsx`
- Test: `client/src/test/AgentWorkbenchRuntime.test.tsx`

### Task B1: Decode without trusting payloads

1. Add failing tests for valid proposal/submission/run projections and malformed projection fallback.
2. Implement narrow TypeScript guards and selectors; do not cast arbitrary payloads.
3. Run the focused protocol/runtime tests and commit.

### Task B2: Render the golden-path states

1. Add failing component tests for ready, warning, blocked, waiting approval, submitted, running, completed, failed, and unknown states.
2. Build an accessible training activity card using existing theme/motion tokens.
3. Integrate it into the virtualized timeline without changing generic execution grouping.
4. Make the composer clearly state the immutable active mode and preserve existing workspace validation behavior.
5. Run tests, typecheck, and commit.

**Verification:**

```powershell
cd client
npx vitest run src/test/AgentFrontendFoundation.test.tsx src/test/AgentWorkbenchRuntime.test.tsx
npm run typecheck
```

Expected: all pass.

## Parallel Track C: Golden-Path Acceptance Guard

**Owned files:**
- Create: `server/tests/fixtures/agent_training_golden_path.json`
- Create: `server/tests/test_agent_training_golden_path.py`
- Create: `client/src/agent/testing/agentTrainingScenarios.ts`
- Create: `client/src/test/AgentTrainingGoldenPath.test.tsx`
- Modify: `docs/agent-training-foundation.md`

### Task C1: Freeze the cross-layer scenarios

1. Define deterministic scenarios for Train approval, rejection, duplicate retry, refresh recovery, Hybrid coexistence, and Build exclusion.
2. Add backend acceptance tests using fakes—never require CUDA, downloads, or a live worker.
3. Add frontend scenario projections that assert ordering, identity stability, and generic fallback.
4. Document the golden path, failure meanings, and manual smoke procedure.
5. Run only the new acceptance tests and commit.

**Verification:**

```powershell
python -m pytest server/tests/test_agent_training_golden_path.py -q
cd client
npx vitest run src/test/AgentTrainingGoldenPath.test.tsx
```

Expected: all pass. If Track A/B contracts are not yet present, commit contract fixtures and clearly report which assertions await integration; do not edit Track A/B implementation files.

## Main-Thread Integration Gate

1. Review each commit for file ownership violations and accidental generated/runtime files.
2. Integrate Track A before B/C when contract dependencies require ordering.
3. Resolve conflicts in the main thread only.
4. Run `git diff --check`.
5. Run the full Agent-training/backend focused suite, frontend focused suite, typecheck, and production build.
6. Confirm `build` has no training tools, submission still requires HITL, duplicate approval cannot create a second task, and persisted activity survives refresh.
7. Update this plan with actual commit IDs and verification results.

