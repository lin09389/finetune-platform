# Phase 7 Implementation Plan: Coding Agent Engineering Loop

> Product guardrail: Coding Agent is a primary product line. This phase contains no new training functionality.

**Goal:** Guarantee a durable edit → diff → verification → review loop and prove it with offline deterministic acceptance tests.

**Architecture:** Generate diff evidence at the existing trajectory write boundary, persist it as versioned session parts, project it through the current REST/SSE Workbench transport, and verify the contract with temporary projects and an injected fake tool-calling model.

**Constraints:** single-machine-first; SQLite and local filesystem remain defaults; DeepAgents remains the sole execution loop; no automatic commit/push; no network/model/CUDA requirement in CI.

## Track A — Backend diff and completion contract

**Primary files**

- Create `server/agent_session/coding_diff.py`
- Modify `server/agent_session/trajectory.py`
- Modify `server/agent_session/deepagents_runtime.py`
- Modify `server/agent_session/state.py` only if the shared part helper needs extension
- Create `server/tests/test_agent_coding_diff.py`
- Extend focused trajectory/runtime tests

**Tasks**

1. Define a versioned, bounded, workspace-relative diff payload and pure snapshot-to-diff builder.
2. Emit an immutable diff part only after write and static validation succeed; never emit for blocked or rolled-back writes.
3. Correlate each record with the successful trajectory write sequence and broadcast through the existing event path.
4. Extend completion scoring so every successful write has diff coverage and final verification is newer than the final relevant write.
5. Cover added/modified/deleted, empty, binary, Unicode, oversized/truncated, repeated edit, rollback, and restart-safe repository cases.

## Track B — Workbench diff review surface

**Primary files**

- Create `client/src/agent/components/AgentDiffReviewCard.tsx`
- Modify `client/src/agent/components/AgentRunTimeline.tsx`
- Extend the existing Agent protocol guard/selectors
- Add focused component/protocol tests and scoped styles

**Tasks**

1. Parse only the versioned backend payload; unknown versions degrade to the existing generic artifact view.
2. Render path, status, additions/deletions, binary/truncated states, and bounded hunks.
3. Group chronological records by file, show latest by default, and expose earlier writes without hiding failures or commands.
4. Prove REST refresh and SSE updates converge to the same card projection.
5. Keep the component read-only: no commit, push, destructive revert, or parallel approval state.

## Track C — Offline engineering-loop acceptance

**Primary files**

- Create `server/tests/fixtures/coding_agent_runtime_scenarios.json`
- Create `server/tests/test_coding_agent_runtime_e2e.py`
- Create `client/src/agent/testing/codingDiffReviewScenarios.ts`
- Create `client/src/test/CodingDiffReviewGoldenPath.test.tsx`
- Create `docs/coding-agent-engineering-loop.md`

**Tasks**

1. Build a deterministic temporary-project harness with an injectable fake tool-calling model; use production session/runtime/repository boundaries wherever the installed DeepAgents contract allows.
2. Cover Python, React/TypeScript, cross-stack multi-file, failed-tool/reread/fix, refresh recovery, and path-isolation scenarios.
3. Assert file results, persisted parts/events, diff coverage, validation ordering, terminal state, and refresh projection—not just fixture snapshots.
4. Document precisely which boundaries are real and which model behavior is simulated.
5. Keep implementation changes out of this track; consume the agreed contract and let the main thread resolve integration dependencies.

## Main-thread integration gate

1. Review every diff for accidental training coupling, absolute-path leakage, unbounded payloads, or a second approval loop.
2. Rebase/cherry-pick tracks in A → B → C order and resolve only shared contract seams centrally.
3. Upgrade cross-track tests after all implementations are present.
4. Run focused backend/frontend suites, full unit suites, typecheck, production build, and bundle budget.
5. Update architecture documentation only after tests demonstrate the completed contract.

## Definition of done

- Every successful Coding Agent write has durable diff evidence.
- A session cannot report successful completion with uncovered writes or stale verification.
- The Workbench presents the same review material live and after refresh.
- Deterministic offline scenarios exercise real production boundaries without network, model downloads, or GPU.
- Existing training activities, approvals, commands, refresh recovery, and capability routing remain green.
