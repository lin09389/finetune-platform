# Coding Agent engineering loop

The Coding Agent follows one DeepAgents execution loop:

`task → read → write → persisted diff review evidence → verification → summary → refreshable review`

This phase adds no training capability, no second tool loop, and no second approval state machine. Write and command approval continue to use the existing DeepAgents interrupt integration. The review surface is read-only: it does not commit, push, or revert a user's project.

## Durable review contract

After a successful workspace write and its static validation, the trajectory boundary persists one immutable `diff` session part. Its versioned payload contains only a workspace-relative path, change status, bounded unified diff (or metadata-only binary/truncated record), additions/deletions, write sequence, and `review_status: ready`.

Repeated writes intentionally produce chronological records. The final completion gate requires diff coverage for every successful write and a successful verification after the last relevant write. The server-backed session parts are the source of truth for both SSE and a browser refresh; the client must not recompute a temporary diff as the review record.

The normative detail is in [ADR 0008](adr/0008-persist-snapshot-diffs-for-coding-review.md).

## Offline deterministic acceptance

`server/tests/test_coding_agent_runtime_e2e.py` builds temporary projects and injects a scripted tool-calling fake model. It covers Python, React/TypeScript, cross-stack writes, failed verification followed by reread/repair, reload recovery, and workspace-path rejection. The fixture explicitly declares `network: false`, `cuda: false`, and `execution_loop: deepagents`.

Real boundaries exercised by that acceptance test:

- `AgentSessionService` session creation and prompt entry;
- the installed DeepAgents runtime adapter and the single trajectory middleware;
- local workspace filesystem tools and path isolation;
- SQLite session repository, persisted parts, emitted events, terminal state, and a new service instance reloading the same database.

Simulated boundary:

- model reasoning and tool selection. The fake model emits a fixed, valid tool-call sequence; the test does not claim to evaluate the quality, safety, or capability of a hosted model.

The end-to-end parameterized test is gated on the Track A `agent_session.coding_diff` contract so older checkouts report an explicit skip rather than pretending a JSON fixture is E2E coverage. In the integrated Phase 7 baseline, all six runtime scenarios execute and assert final file contents, diff parts/events, coverage, validation ordering, completion, and refresh projection through the real boundaries above. Its fixture-schema test and the client golden-path test remain independently runnable.

Run the focused checks from the repository root:

```powershell
.venv\Scripts\python.exe -m pytest server/tests/test_coding_agent_runtime_e2e.py -q
Set-Location client
npx vitest run src/test/CodingDiffReviewGoldenPath.test.tsx --reporter=basic
```
