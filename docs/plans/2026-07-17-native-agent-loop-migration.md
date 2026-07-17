# Native Agent Loop and Workbench v2 Implementation Plan

> **Execution note:** Use the `executing-plans` workflow. Each wave begins from a clean `master`, uses explicit
> file ownership, follows TDD, produces atomic commits, and is integrated by the main coordination thread.

**Goal:** Replace DeepAgents with a self-owned Native Build loop, replace the Agent wire protocol and Workbench,
and reach a safe, recoverable, evidence-backed Build cutover without preserving legacy Agent sessions.

**Architecture:** Actor-style Native Session Host, thin Sampling Loop, policy-gated Tool Runtime,
`ExecutionEnvironmentProvider`, append-only event store with snapshots, WebSocket v2, default Goal Workflow,
file mutation ledger/rewind, and a rewritten desktop Workbench.

**Stack:** Python 3.11, FastAPI/Starlette WebSocket, SQLite, Pydantic, existing model providers, React 18,
TypeScript, Zustand or reducer-based normalized store, Vite, Electron, Vitest, pytest.

## 0. Delivery Rules

- No production code imports `grok-build`; it is a design reference only.
- Do not copy prompt text from `grok-prompts` unless licensing is separately established.
- No Native/DeepAgents nesting or dual execution.
- No compatibility adapter for Train/Hybrid or legacy frontend parts.
- No public runtime selector.
- Do not delete DeepAgents until the final removal wave.
- Keep Workspace/model/dataset/training/inference data intact.
- Shared contracts are owned by the main thread and frozen before parallel tracks.
- Every track reports exact tests, changed files, known gaps, and commit range.

## 1. Recommended Delivery Waves

```text
Wave 0  Contract freeze and architecture guards
Wave 1  Event store, snapshots, scoped legacy reset
Wave 2  WebSocket gateway and Native Session Host
Wave 3  Sampling loop, model adapters, prompts, compaction
Wave 4  Tool runtime, approvals, execution environment, mutation ledger
Wave 5  Goal Workflow, rewind, trace collector
Wave 6  Workbench v2 rewrite against frozen fixtures
Wave 7  Native Build integration, security/eval cutover
Wave 8  DeepAgents and legacy frontend removal
Wave 9  Reintroduce Train/Hybrid natively (separate future plan)
```

Waves 1-5 should land as backend vertical slices with a deterministic fake model. Wave 6 may start after the
v2 envelope/event catalog from Waves 0-2 is frozen, using checked-in fixtures; it must not invent backend fields.

## 2. Wave 0 — Freeze Contracts and Guardrails

### Task 0.1: Add the Native domain package skeleton

**Create:**

- `server/native_agent/__init__.py`
- `server/native_agent/contracts.py`
- `server/native_agent/commands.py`
- `server/native_agent/events.py`
- `server/native_agent/errors.py`
- `server/tests/test_native_agent_contracts.py`

**Test first:** Define tests for strict v2 JSON serialization, required identifiers, payload byte limits, unknown
command rejection, unknown event tolerance, monotonic sequence validation, and safe path/error redaction.

**Implementation:** Use discriminated Pydantic models for commands/events. Keep the envelope transport-neutral;
do not import FastAPI or WebSocket types into the domain package.

**Verify:**

```powershell
python -m pytest server/tests/test_native_agent_contracts.py -q
```

### Task 0.2: Add architecture guards

**Create:** `server/tests/test_native_agent_architecture.py`

**Guard assertions:**

- `server/native_agent` cannot import `deepagents`, `langgraph`, FastAPI routers, React artifacts, or training code.
- model adapters cannot import tool implementations;
- tool implementations cannot append session events directly;
- WebSocket gateway cannot instantiate the sampling loop directly;
- trace subscribers cannot import repositories with write access to primary session state.

### Task 0.3: Disable Train/Hybrid at authoritative boundaries

**Modify:**

- `server/api/agent_sessions.py`
- `server/agent_session/models.py` or the current task-mode validator
- `client/src/agent/` only for the temporary disabled-state patch
- relevant backend/frontend tests

Reject new Train/Hybrid Agent sessions with a typed `capability_migrating` response. Remove training tools from
Build manifests and runtime catalogs. UI must show a deliberate migration state, not a generic error.

**Commit:** `feat(native-agent): freeze v2 contracts and migration guards`

## 3. Wave 1 — Event Store, Snapshots, and Scoped Reset

### Task 1.1: Introduce migration 017

**Create:** `server/core/migrations/017_native_agent_v2.sql`

Create v2 session, event, command-idempotency, snapshot, pending-interaction, mutation, and trace-candidate tables.
Use foreign keys, unique `(session_id, sequence)`, unique `(session_id, command_id)`, schema versions, timestamps,
and indexes for replay and recovery.

The migration must clear only legacy Agent Session rows and related DeepAgents checkpoint/derived rows. Write an
explicit allowlist of affected tables; never use broad name patterns.

**Create tests:** `server/tests/test_native_agent_migration.py`

Seed both Agent and non-Agent product data, run migration, and prove that Workspace, chat, models, datasets,
training jobs, inference records, settings, and user data survive byte-for-byte/logically unchanged.

### Task 1.2: Implement append-only repository

**Create:**

- `server/native_agent/repository.py`
- `server/native_agent/snapshots.py`
- `server/tests/test_native_agent_repository.py`

Required repository operations:

- create/get/list session identity;
- append event with expected previous sequence in one transaction;
- append command acknowledgement/result idempotently;
- load events after cursor with a bounded page;
- save/load checksum-validated snapshots;
- claim/renew/release session ownership lease;
- load pending interactions and file mutations.

No update/delete API for committed events.

### Task 1.3: Recovery projector

**Create:**

- `server/native_agent/projection.py`
- `server/tests/test_native_agent_projection.py`

Project session status, active turn, queue, steering, approval, Goal Graph, usage, mutation ledger, compaction, and
terminal state from events. Validate snapshot + tail replay equals full replay for generated event sequences.

**Commit:** `feat(native-agent): add append-only session persistence`

## 4. Wave 2 — WebSocket Gateway and Session Host

### Task 2.1: Implement actor mailbox and host registry

**Create:**

- `server/native_agent/session_host.py`
- `server/native_agent/host_registry.py`
- `server/native_agent/queueing.py`
- `server/tests/test_native_agent_session_host.py`

Use one serialized async mailbox per active session. Test FIFO follow-up, deferred steering during a tool,
steering during sampling, send-now cancellation ordering, duplicate command idempotency, shutdown, lease loss,
and host rebuild.

### Task 2.2: Add WebSocket v2 route

**Create:** `server/api/native_agent_ws.py`

**Modify:**

- `server/apps/routers.py`
- `server/apps/lifespan.py`
- auth helpers only as needed
- `server/tests/test_native_agent_websocket.py`

Implement authenticated connection bootstrap, typed command dispatch, replay subscription, ping/pong, bounded
outgoing queue, reconnect cursor, snapshot resync, and stable errors. Test disconnect while turn continues and
reconnect without event gaps/duplicates.

### Task 2.3: Background lifecycle

Integrate host registry startup/shutdown into the Agent application lifespan. Shutdown stops accepting commands,
requests turn cancellation, waits for a bounded grace period, snapshots safe state, and releases leases.

**Commit:** `feat(native-agent): add websocket session host`

## 5. Wave 3 — Native Sampling Loop and Context

### Task 3.1: Define model port and deterministic fake

**Create:**

- `server/native_agent/model_port.py`
- `server/native_agent/testing/fake_model.py`
- `server/tests/test_native_agent_sampling_loop.py`

Define provider-neutral request, streaming delta, structured tool call, finish reason, token usage, cancellation,
and classified failure contracts. The fake must script multi-turn tool flows, malformed tool calls, retryable
errors, cancellation, and compaction.

### Task 3.2: Implement prompt/context assembly

**Create:**

- `server/native_agent/context.py`
- `server/native_agent/prompts.py`
- `server/native_agent/compaction.py`
- `server/tests/test_native_agent_context.py`
- `server/tests/test_native_agent_compaction.py`

Separate platform identity, role prompt, Workspace facts, Goal Graph, selected history, tool schemas, safety facts,
and compaction. Never request or persist private chain-of-thought. Store concise assistant rationale/status only.

Compaction output follows the schema in the design document and is replayable. Test that goal, file changes,
failures, queued messages, approvals, and verification survive compaction.

### Task 3.3: Implement thin loop

**Create:** `server/native_agent/sampling_loop.py`

The loop reads a projected turn context, calls the model port, emits proposed facts, requests tools through a
port, and returns a typed terminal/pause outcome. It cannot access repositories, WebSockets, concrete tools, or
FastAPI.

### Task 3.4: Adapt current Build model providers

**Create:** `server/native_agent/model_adapters.py`

Reuse existing cloud/local model access without importing DeepAgents/LangGraph. Add contract tests for at least
one OpenAI-compatible provider and the local inference provider using mocked HTTP boundaries.

**Commit:** `feat(native-agent): implement native sampling and compaction`

## 6. Wave 4 — Tool Runtime, Approval, and Execution Environment

### Task 4.1: Define tool protocol and registry

**Create:**

- `server/native_agent/tools/contracts.py`
- `server/native_agent/tools/registry.py`
- `server/native_agent/tools/runtime.py`
- `server/tests/test_native_agent_tool_runtime.py`

Tool definitions declare input/output schemas, permission capabilities, timeout class, side-effect class,
cancellation support, and result-size policy. Tool results are structured with safe summary and artifact refs.

### Task 4.2: Permission and pending interaction

**Create:**

- `server/native_agent/policy.py`
- `server/native_agent/approvals.py`
- `server/tests/test_native_agent_approvals.py`

Port existing policy intent, not DeepAgents interrupt code. Test allow/deny/ask, repeated clicks, cross-user
decisions, stale decisions, reconnect recovery, rejection, cancellation while waiting, and command idempotency.

### Task 4.3: Execution environment abstraction

**Create:**

- `server/native_agent/execution/contracts.py`
- `server/native_agent/execution/local.py`
- `server/native_agent/execution/wsl.py`
- `server/tests/test_native_agent_execution_environment.py`

Expose safe path resolution, file operations, process execution, process-tree cancellation, environment injection,
network capability report, output limits, and provider diagnostics. Mark local/WSL as trusted-development modes,
not sandboxes.

### Task 4.4: Native Build tools

**Create:** `server/native_agent/tools/build.py`

Implement list/read/search/write/edit/delete/move, execute, validation, diff reference, and artifact lookup against
the execution provider. Do not wrap DeepAgents tools.

### Task 4.5: Mutation ledger

**Create:**

- `server/native_agent/mutations.py`
- `server/tests/test_native_agent_mutations.py`

Capture bounded text pre-images/hashes before write effects and post-images/hashes afterward. Test encoding,
size cap, deletion, rename, failed writes, symlinks, binary files, external edits, and concurrent mutations.

**Commit:** `feat(native-agent): add policy-gated build tool runtime`

## 7. Wave 5 — Goal Workflow, Rewind, and Trace

### Task 5.1: Replace Build execution plan with Goal Graph

**Create:**

- `server/native_agent/goals/contracts.py`
- `server/native_agent/goals/workflow.py`
- `server/native_agent/goals/roles.py`
- `server/tests/test_native_agent_goal_workflow.py`

Implement Planner/Implementer/Verifier/Strategist state transitions. All roles use the bound Build model but have
separate contexts and usage. Test schema failures, verifier revision, strategist threshold, blocked goals,
cancellation, recovery, and no duplicate active step.

Do not write legacy `execution_plan` rows.

### Task 5.2: Conversation/file rewind

**Create:**

- `server/native_agent/rewind.py`
- `server/tests/test_native_agent_rewind.py`

Preview effects before confirmation. Append a new branch event, restore eligible text mutations in reverse order,
and append per-file outcomes. Test unrelated dirty files, external edits, binary/large/symlink conflicts, rename,
delete, crash halfway through restore, retry idempotency, and no `git reset` invocation.

### Task 5.3: Local redacted trace collector

**Create:**

- `server/native_agent/trace.py`
- `server/tests/test_native_agent_trace.py`

Subscribe asynchronously to committed events. Store structural facts only, enforce redaction, and isolate errors.
Provide select/reject/export-candidate operations for later manual curation; do not start training.

**Commit:** `feat(native-agent): add goal workflow rewind and trace`

## 8. Wave 6 — Workbench v2 Rewrite

This wave uses the frontend design system and browser-based visual acceptance. It starts after the event catalog
is frozen and consumes checked-in v2 fixtures generated from backend schemas.

### Task 6.1: Add v2 protocol and transport

**Create:**

- `client/src/native-agent/protocol/envelope.ts`
- `client/src/native-agent/protocol/events.ts`
- `client/src/native-agent/protocol/commands.ts`
- `client/src/native-agent/transport/websocketTransport.ts`
- `client/src/native-agent/testing/fixtures/`
- corresponding Vitest tests

Use runtime validation at the network edge. Test unknown events, reconnect cursor, duplicate delivery,
out-of-order rejection, snapshot resync, backpressure disconnect, and idempotent commands.

### Task 6.2: Build normalized projection store

**Create:**

- `client/src/native-agent/store/nativeAgentStore.ts`
- `client/src/native-agent/store/projectEvent.ts`
- `client/src/native-agent/selectors/`
- corresponding store/selector tests

Project session, active turn, queue, steering, Goal Graph, timeline, approval, usage, files, terminal, diagnostics,
rewind preview, attention, and connection state. Do not persist mutable server truth in local storage; persist only
safe UI preferences and last cursor/session reference.

### Task 6.3: Establish visual system and shell

**Create:**

- `client/src/native-agent/styles/tokens.css`
- `client/src/native-agent/workbench/NativeWorkbenchPage.tsx`
- `client/src/native-agent/workbench/NativeWorkbenchShell.tsx`
- scoped CSS modules and tests/stories

Define warm editorial surfaces, terra-cotta accent, typography, spacing, states, dock layout, keyboard focus, dark
theme, reduced motion, and desktop/mobile breakpoints. Avoid reuse of legacy layout CSS that encodes old panels.

### Task 6.4: Implement execution surfaces

**Create focused components for:**

- session/history rail;
- Workspace/branch/model/runtime header;
- Goal Graph and step evidence;
- execution narrative timeline;
- follow-up/steering composer and send-now confirmation;
- approval card;
- file/diff dock;
- terminal/log dock;
- diagnostics/usage/context dock;
- rewind preview and conflict resolution;
- loading, empty, reconnecting, degraded, blocked, cancelled, and fatal states;
- Train/Hybrid migration notice.

### Task 6.5: Route cutover without legacy imports

**Modify:**

- `client/src/App.tsx`
- relevant navigation/capability mappings
- route tests

Point `/agent` to Native Workbench v2. Add an architecture test that nothing under `client/src/native-agent` imports
`client/src/agent/protocol`, SSE transport, legacy Agent parts, or training activity types.

### Task 6.6: Visual acceptance

Use Playwright at minimum:

- 1440x900 and 1280x720 desktop;
- 768px compact/tablet;
- 390x844 narrow/mobile fallback;
- light/dark;
- reduced motion;
- long goal, large diff reference, approval, reconnect, rewind conflict, empty and failure states.

Verify keyboard traversal, screen-reader names, contrast, no horizontal overflow, no clipped composer, and existing
bundle budgets. Do not solve bundle failures by raising the budget.

**Commit:** `feat(workbench): replace legacy agent ui with native v2`

## 9. Wave 7 — Vertical Integration and Cutover

### Task 7.1: Bind Native runtime in AgentSessionService

**Modify:**

- `server/agent_session/service.py`
- session lifecycle/application assembly modules
- internal runtime configuration
- integration tests

During development, Native is opt-in through internal configuration. Session runtime kind is immutable. There is
no UI selector. After gates pass, new Build sessions default Native.

### Task 7.2: Real deterministic Build journeys

**Create:** `server/tests/test_native_agent_runtime_e2e.py`

Exercise production Session Host/repository/tools with a deterministic fake model:

1. Python bug fix and verification.
2. React/TypeScript change and typecheck.
3. Multi-file backend/frontend change.
4. Failed command, re-observation, repair, and successful revalidation.
5. Queue then steering while a tool is active.
6. Approval, reconnect, and resume.
7. API crash/restart and snapshot replay.
8. Rewind conversation plus files while preserving unrelated dirty changes.
9. Context compaction then completion.
10. Train/Hybrid rejection.

### Task 7.3: Trusted sandbox gate

Implement the provider selected by the security design in a separate ADR. Native cannot become default while
only local/WSL development providers exist. Required tests cover Workspace escape, network denial, environment
secrets, process descendants, cancellation, resource limits, and fail-closed initialization.

### Task 7.4: Real-model evaluation

Run the versioned Agent Eval suite against the same Build model/config used in the product. Compare success,
verification, unsafe actions, retries, intervention count, tokens, cost, and duration against the Phase 9/Phase B
baseline. Record failures; do not loosen validators to obtain a pass.

### Task 7.5: Native default and soak

After all gates pass, change the internal default to Native for new Build sessions. Keep DeepAgents code dormant
for a bounded soak/recovery period only. Track crash, replay, approval, rewind, tool failure, and completion rates.

**Commit:** `feat(native-agent): make native build runtime default`

## 10. Wave 8 — Remove DeepAgents and Legacy Agent UI

### Task 8.1: Remove backend runtime

**Delete after soak:**

- `server/agent_session/deepagents_runtime.py`
- `server/agent_session/deepagents_events.py`
- `server/agent_session/deepagents_compat.py`
- `server/agent_session/deepagents_checkpoint.py`
- obsolete DeepAgents-only factory/contract/prompt paths
- DeepAgents/LangGraph dependencies no longer required elsewhere
- obsolete tests and migrations only when safe to retain history

Update `pyproject.toml`, `uv.lock`, exported requirements, Electron runtime profiles, Docker profiles, README,
AGENTS.md, capability truth table, and architecture documentation.

### Task 8.2: Remove legacy frontend

Delete old SSE/parts transport, protocol decoders, legacy Workbench components/styles, and tests after confirming
no non-Agent route imports them. Preserve generic shared design components only when they are genuinely reused.

### Task 8.3: Architecture proof

Add repository-wide guards proving no production import/reference to DeepAgents, LangGraph checkpoints, old Agent
SSE endpoints, old parts protocol, legacy Build `execution_plan`, or legacy runtime selector remains.

**Commit:** `refactor(agent): remove deepagents and legacy workbench`

## 11. Final Verification Matrix

### Backend

```powershell
python -m pytest server/tests/test_native_agent_contracts.py -q
python -m pytest server/tests/test_native_agent_repository.py -q
python -m pytest server/tests/test_native_agent_session_host.py -q
python -m pytest server/tests/test_native_agent_websocket.py -q
python -m pytest server/tests/test_native_agent_sampling_loop.py -q
python -m pytest server/tests/test_native_agent_tool_runtime.py -q
python -m pytest server/tests/test_native_agent_goal_workflow.py -q
python -m pytest server/tests/test_native_agent_rewind.py -q
python -m pytest server/tests/test_native_agent_runtime_e2e.py -q
python -m pytest server/tests -m "not integration and not e2e" -q
```

### Frontend

```powershell
Set-Location client
npm run typecheck
npx vitest run src/native-agent src/test
npm run build
```

### Desktop and packaging

```powershell
Set-Location ..
npm run test:desktop
npm run test:runtime-pack
npm run test:package-policy
```

### Static and documentation

```powershell
git diff --check
rg -n "deepagents|DeepAgents|langgraph|events/stream" server client README.md README_EN.md AGENTS.md docs
```

Any remaining match must be an explicit historical migration/ADR reference, not a production dependency or a
claim that DeepAgents is still the target runtime.

## 12. Parallel Ownership after Contract Freeze

### Safe parallel tracks

- Event repository/snapshots vs. frontend fixture-driven protocol/store.
- Model port/sampling loop vs. execution-environment contract/tool schemas.
- Visual shell/components vs. backend deterministic fake-model scenarios.
- Trace privacy fixtures vs. primary runtime, provided trace stays subscriber-only.

### Must remain serialized

- Event envelope/catalog changes.
- Session state and command semantics.
- Goal Graph schema.
- Permission/approval transition model.
- Mutation/rewind ownership semantics.
- `/agent` route cutover and deletion of legacy code.
- Native default switch and DeepAgents removal.

## 13. Stop Conditions

Stop integration and return to design if any implementation:

- creates a second authoritative transcript, plan, approval, or current-state table;
- lets WebSocket connection lifetime control turn lifetime;
- runs tools before a durable policy/approval decision;
- silently falls back from trusted sandbox to local execution;
- overwrites a file whose current hash is not the expected Agent-produced hash;
- stores secrets, absolute paths, raw source, or full prompts in default traces;
- keeps Train/Hybrid usable through hidden legacy routes;
- requires both DeepAgents and Native to execute one Build turn;
- weakens validators, security, or test criteria to make the Native benchmark pass;
- raises frontend bundle budgets instead of splitting the rewritten Workbench.

## 14. Completion Definition

The migration is complete when Build uses Native by default, Workbench v2 is the only Agent UI, old Agent
sessions are removed by scoped migration, real-model and security gates pass, recovery/rewind are trustworthy,
DeepAgents and legacy Agent protocol dependencies are deleted, and the repository documentation describes the
Native architecture as current fact.

Train/Hybrid reintroduction is a separate post-migration plan. It must use Native tools/events/approvals and may
not restore DeepAgents or the old protocol.
