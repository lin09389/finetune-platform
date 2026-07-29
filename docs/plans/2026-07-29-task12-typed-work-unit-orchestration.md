# Task 12 Typed Work Unit Orchestration Implementation Plan

> **Execution mode:** implement in small commits on `master`, preserving all
> unrelated worktree changes. Use TDD for every task. Do not start Task 13.

**Goal:** Replace model-decided subagent creation in Controlled Build sessions
with deterministic, durable WorkUnit orchestration while retaining DeepAgents
as the only model/tool loop.

**Architecture:** Compile strict WorkUnits from Goal Plan v1, persist them in
the existing subtask tables, dispatch read-only Explore/Review children through
`AsyncSubagentService`, and invoke the parent DeepAgents runtime in scoped
phase turns. The orchestrator is the only producer of
`typed_work_unit.v1` phase-boundary evidence.

**Design:** `docs/plans/2026-07-29-task12-typed-work-unit-orchestration-design.md`

**ADR:** `docs/adr/0013-use-typed-work-units-for-controlled-build-orchestration.md`

---

## Baseline rules

- Controlled Build only.
- Parent Build is the only writer.
- Explore/Review children are read-only and max concurrency is two.
- No new model call for WorkUnit compilation or delegation.
- Every WorkUnit failure retries `max_phase_retries` times.
- Legacy, Shadow, Train, and Hybrid remain unchanged.
- No worktree, sandbox, Tool Runtime Worker, or new frontend DAG.
- Do not modify unrelated files already dirty in the user worktree.

## Task 12A: Define strict WorkUnit contracts

**Files:**

- Create: `server/agent_session/work_unit.py`
- Create: `server/tests/test_agent_work_unit.py`
- Modify: `server/tests/test_tool_platform_architecture.py`

### Step 1: Write failing schema and immutability tests

Cover:

- `agent.work_unit.v1` and WorkUnitResult version tags;
- strict unknown-field rejection;
- forbidden reasoning/CoT keys;
- recursive JSON immutability;
- safe evidence and artifact references;
- no host absolute paths;
- bounded budgets;
- parent/child ownership enums;
- terminal status monotonicity helpers.

Run:

```powershell
python -m pytest server/tests/test_agent_work_unit.py -q
```

Expected: fail because the module does not exist.

### Step 2: Implement the minimal contracts

Define:

- `WorkUnit`;
- `WorkUnitResult`;
- `WorkUnitBudget`;
- `WorkUnitFileScope`;
- `WorkUnitToolProjection`;
- `WorkUnitDependency`;
- `WorkUnitRunScope`;
- status, owner, verdict, and attempt models;
- safe serialization and parsing helpers.

Do not add repository or runtime behavior.

### Step 3: Verify

```powershell
python -m pytest server/tests/test_agent_work_unit.py server/tests/test_tool_platform_architecture.py -q
python -m ruff check server/agent_session/work_unit.py server/tests/test_agent_work_unit.py
git diff --check
```

### Step 4: Commit

```powershell
git add server/agent_session/work_unit.py server/tests/test_agent_work_unit.py server/tests/test_tool_platform_architecture.py
git commit -m "feat(agent): define typed work unit contracts"
```

## Task 12B: Compile Goal Plans deterministically

**Files:**

- Modify: `server/agent_session/work_unit.py`
- Modify: `server/agent_session/goal_plan.py`
- Modify: `server/agent_session/goal_planner.py`
- Modify: `server/tests/test_agent_work_unit.py`
- Modify: `server/tests/test_agent_goal_plan.py`

### Step 1: Write failing compiler tests

Cover:

- canonical plan fingerprint;
- stable WorkUnit IDs;
- fixed phase-to-owner mapping;
- unknown phases remain parent-owned;
- Inspect/Plan and Review child scopes become read-only;
- Goal Plan paths can narrow but not expand the parent Workspace;
- dependency translation and cycle rejection;
- maximum 12 WorkUnits;
- duplicate IDs with different content fail closed;
- missing/invalid/empty Goal Plan returns parent-only fallback diagnostics;
- compiler does not call a model.

### Step 2: Implement the compiler

Add pure functions:

- `fingerprint_goal_plan`;
- `normalize_work_unit_phase`;
- `compile_work_units`;
- `validate_work_unit_graph`;
- `build_parent_only_fallback`.

Do not add `executor` or `subagent_type` to Goal Plan. The fixed platform
mapping is the authority.

### Step 3: Tighten the Goal Planner prompt

Ask for canonical phase IDs/titles where applicable, without making them a
permission source. Preserve Goal Plan v1 compatibility and the existing
two-attempt planner bound.

### Step 4: Verify and commit

```powershell
python -m pytest server/tests/test_agent_work_unit.py server/tests/test_agent_goal_plan.py server/tests/test_agent_execution_plan.py -q
python -m ruff check server/agent_session/work_unit.py server/agent_session/goal_plan.py server/agent_session/goal_planner.py
git diff --check
git add server/agent_session/work_unit.py server/agent_session/goal_plan.py server/agent_session/goal_planner.py server/tests/test_agent_work_unit.py server/tests/test_agent_goal_plan.py
git commit -m "feat(agent): compile goal plans into work units"
```

## Task 12C: Add idempotent WorkUnit persistence

**Files:**

- Modify: `server/agent_session/repository.py`
- Create: `server/tests/test_agent_work_unit_repository.py`
- Modify: `server/tests/test_agent_work_unit.py`

### Step 1: Write failing repository tests

Cover:

- explicit stable WorkUnit ID;
- create-if-absent returns the existing identical envelope;
- same ID with different envelope is rejected;
- list by parent and plan fingerprint;
- transactional attempt increment;
- exactly one active child revision;
- event-ID deduplication;
- monotonic terminal updates;
- legacy async-subtask rows still parse unchanged.

### Step 2: Implement repository helpers

Reuse `agent_subtasks` and `agent_subtask_events`. Store a discriminated
WorkUnit envelope in `input_json`.

Add narrowly scoped methods such as:

- `create_work_unit_if_absent`;
- `get_work_unit_record`;
- `list_work_unit_records`;
- `advance_work_unit_attempt`;
- `transition_work_unit`;
- `add_work_unit_event_once`.

Use existing connection pooling and write-retry conventions. Do not introduce a
new database or table unless a failing concurrency test proves the current
primary-key/event model insufficient.

### Step 3: Verify and commit

```powershell
python -m pytest server/tests/test_agent_work_unit_repository.py server/tests/test_agent_work_unit.py -q
python -m ruff check server/agent_session/repository.py server/tests/test_agent_work_unit_repository.py
git diff --check
git add server/agent_session/repository.py server/tests/test_agent_work_unit_repository.py server/tests/test_agent_work_unit.py
git commit -m "feat(agent): persist typed work units idempotently"
```

## Task 12D: Adapt AsyncSubagentService for typed read-only units

**Files:**

- Modify: `server/agent_session/async_subagents.py`
- Modify: `server/agent_session/async_subagent_policy.py`
- Create: `server/tests/test_agent_async_subagents.py`
- Modify: `server/tests/test_agent_work_unit.py`

### Step 1: Write failing typed-dispatch tests

Cover:

- explicit WorkUnit ID is retained;
- Explore/Review child sessions inherit provider/model/workspace;
- child autonomy is read-only;
- child tool projection is a strict intersection;
- nested delegation tools are absent;
- side-effect requests never create user approval;
- structured WorkUnitResult parsing;
- invalid output is a failed attempt;
- old child revisions cannot update the current attempt;
- legacy `start_task` behavior remains unchanged.

### Step 2: Implement a typed execution adapter

Add an orchestrator-only method such as:

```python
await service.start_work_unit(work_unit, *, attempt)
```

It may call existing child creation and scheduling internals, but model-facing
legacy methods remain separate.

Persist child metadata:

- `parent_session_id`;
- `work_unit_id`;
- `work_unit_attempt`;
- `plan_fingerprint`;
- read-only autonomy;
- narrowed file scope;
- executable-free tool projection.

### Step 3: Verify and commit

```powershell
python -m pytest server/tests/test_agent_async_subagents.py server/tests/test_agent_work_unit.py server/tests/test_agent_session_deepagents_runtime.py -q
python -m ruff check server/agent_session/async_subagents.py server/agent_session/async_subagent_policy.py
git diff --check
git add server/agent_session/async_subagents.py server/agent_session/async_subagent_policy.py server/tests/test_agent_async_subagents.py server/tests/test_agent_work_unit.py
git commit -m "feat(agent): execute typed read-only subagent units"
```

## Task 12E: Implement the durable WorkUnit orchestrator

**Files:**

- Create: `server/agent_session/subagent_orchestrator.py`
- Create: `server/tests/test_agent_subagent_orchestrator.py`
- Modify: `server/agent_session/async_subagents.py`
- Modify: `server/agent_session/phase_controller.py`

### Step 1: Write failing state-machine tests

Cover:

- dependency readiness;
- Explore/Plan concurrency of two;
- parent units are serial;
- Review starts only after Verify passes;
- every failure class retries to `max_phase_retries`;
- each retry creates a new attempt/revision without authority changes;
- exhausted child work degrades to parent fallback;
- Review `changes_required` returns to Implement;
- exhausted correction budget yields `needs_manual_review`;
- parent cancellation cascades;
- terminal state is monotonic;
- stale event/result isolation;
- steering consumed only at a WorkUnit boundary.

### Step 2: Implement pure orchestration decisions

Separate pure decisions from effects:

- `ready_work_units`;
- `next_orchestration_actions`;
- `apply_work_unit_event`;
- `apply_review_verdict`;
- `retry_or_degrade`;
- `cancel_work_unit_graph`.

### Step 3: Implement effectful scheduling

The service:

- reads current SQLite facts;
- claims one parent unit or up to two read-only child units;
- calls `AsyncSubagentService` only for Explore/Review;
- persists events before notifications;
- never treats an in-memory task as authoritative.

### Step 4: Verify and commit

```powershell
python -m pytest server/tests/test_agent_subagent_orchestrator.py server/tests/test_agent_work_unit.py server/tests/test_agent_async_subagents.py -q
python -m ruff check server/agent_session/subagent_orchestrator.py server/tests/test_agent_subagent_orchestrator.py
git diff --check
git add server/agent_session/subagent_orchestrator.py server/agent_session/async_subagents.py server/agent_session/phase_controller.py server/tests/test_agent_subagent_orchestrator.py
git commit -m "feat(agent): orchestrate durable work unit graphs"
```

## Task 12F: Add scoped parent DeepAgents invocation

**Files:**

- Modify: `server/agent_session/deepagents_runtime.py`
- Modify: `server/agent_session/runtime_contract.py`
- Modify: `server/agent_session/deepagents_events.py`
- Modify: `server/agent_session/services/background_task_manager.py`
- Modify: `server/tests/test_agent_session_deepagents_runtime.py`
- Modify: `server/tests/test_agent_tool_runtime_binding.py`
- Modify: `server/tests/test_agent_subagent_orchestrator.py`

### Step 1: Characterize current finalization

Write failing tests proving that current `run_prompt()`:

- marks the parent session complete;
- emits `summary_completed`;
- binds one Runtime Contract for the whole run.

Do not modify behavior until these tests establish the current boundary.

### Step 2: Add WorkUnitRunScope

Add an internal scoped path, for example:

```python
await runner.run_work_unit(
    session_id,
    instruction,
    scope=WorkUnitRunScope(...),
)
```

Required behavior:

- same session and checkpoint;
- rebuild Runtime Contract before each unit;
- bind current `phase_tool_projection`;
- non-Deliver completion does not finalize the session;
- Deliver is the only finalizing scope;
- events carry WorkUnit ID, phase, and attempt;
- HITL resume retains the same WorkUnit attempt.

Do not add another model loop. This method remains a bounded DeepAgents
invocation.

### Step 3: Connect parent units

Let the orchestrator call `run_work_unit` for Implement, Verify, fallback
Review, and Deliver. Feed safe child summaries/evidence into later parent unit
instructions.

### Step 4: Verify and commit

```powershell
python -m pytest server/tests/test_agent_session_deepagents_runtime.py server/tests/test_agent_tool_runtime_binding.py server/tests/test_agent_subagent_orchestrator.py server/tests/test_agent_phase_controller.py -q
python -m ruff check server/agent_session/deepagents_runtime.py server/agent_session/runtime_contract.py server/agent_session/deepagents_events.py server/agent_session/services/background_task_manager.py
git diff --check
git add server/agent_session/deepagents_runtime.py server/agent_session/runtime_contract.py server/agent_session/deepagents_events.py server/agent_session/services/background_task_manager.py server/tests/test_agent_session_deepagents_runtime.py server/tests/test_agent_tool_runtime_binding.py server/tests/test_agent_subagent_orchestrator.py
git commit -m "feat(agent): run deepagents in scoped work units"
```

## Task 12G: Wire Controlled Build lifecycle, recovery, and cancellation

**Files:**

- Modify: `server/agent_session/services/background_task_manager.py`
- Modify: `server/agent_session/services/recovery_service.py`
- Modify: `server/agent_session/services/session_lifecycle.py`
- Modify: `server/agent_session/services/event_broadcast.py`
- Modify: `server/agent_session/service.py`
- Modify: `server/agent_session/phase_control_events.py`
- Modify: `server/agent_session/phase_tool_router.py`
- Modify: `server/tests/test_agent_subagent_orchestrator.py`
- Modify: `server/tests/test_agent_execution_plan_recovery.py`
- Modify: `server/tests/test_agent_phase_controller.py`

### Step 1: Write failing lifecycle tests

Cover:

- compile after Goal Plan attachment;
- persist graph before activation;
- only an active durable graph writes
  `phase_boundary_driver=typed_work_unit.v1`;
- compilation failure keeps Controlled Gateway and parent-only execution;
- restart reconciles pending/running attempts exactly once;
- parent cancellation cancels all non-terminal units and children;
- HITL resume re-enters the current unit;
- duplicate startup/recovery calls are idempotent;
- WorkUnit boundary advances the phase once;
- stale plan fingerprint cancels old units.

### Step 2: Wire prompt startup

Controlled Build order:

```text
attach Goal Plan
→ bootstrap phase state
→ compile and persist WorkUnits
→ activate orchestrator and boundary driver
→ schedule ready units
```

Fallback order:

```text
Goal Plan/compile/orchestrator unavailable
→ keep Controlled Gateway
→ omit typed boundary driver
→ run parent-only Build
```

### Step 3: Wire recovery and shutdown

Reuse existing lifecycle ownership. Do not start a second global scheduler.
The one service-level orchestrator reconciles persisted WorkUnits.

### Step 4: Verify and commit

```powershell
python -m pytest server/tests/test_agent_subagent_orchestrator.py server/tests/test_agent_execution_plan_recovery.py server/tests/test_agent_phase_controller.py server/tests/test_agent_goal_plan.py -q
python -m ruff check server/agent_session/services server/agent_session/phase_control_events.py server/agent_session/phase_tool_router.py
git diff --check
git add server/agent_session/services server/agent_session/service.py server/agent_session/phase_control_events.py server/agent_session/phase_tool_router.py server/tests/test_agent_subagent_orchestrator.py server/tests/test_agent_execution_plan_recovery.py server/tests/test_agent_phase_controller.py
git commit -m "feat(agent): bind work units to controlled build lifecycle"
```

## Task 12H: Remove model-decided delegation in active Controlled mode

**Files:**

- Modify: `server/agent_session/deepagents_runtime.py`
- Modify: `server/agent_session/async_subagent_policy.py`
- Modify: `server/agent_session/runtime_contract.py`
- Modify: `server/tests/test_agent_session_deepagents_runtime.py`
- Modify: `server/tests/test_tool_platform_architecture.py`

### Step 1: Write failing visibility tests

For active typed WorkUnit orchestration, assert the model cannot see:

- `start_async_task`;
- `check_async_task`;
- `list_async_tasks`;
- `update_async_task`;
- `cancel_async_task`;
- any nested delegation alias.

Assert Legacy and Shadow still expose their current catalog where authorized.

### Step 2: Implement mode-aware filtering

Filter only when the durable WorkUnit orchestrator is active. Do not infer
activation solely from user-supplied metadata.

### Step 3: Add architecture guards

Assert:

- no second Agent/model loop;
- no new approval state machine;
- orchestrator calls `AsyncSubagentService` directly;
- child sessions cannot delegate;
- only the orchestrator can persist the typed boundary driver.

### Step 4: Verify and commit

```powershell
python -m pytest server/tests/test_agent_session_deepagents_runtime.py server/tests/test_tool_platform_architecture.py server/tests/test_agent_subagent_orchestrator.py -q
python -m ruff check server/agent_session/deepagents_runtime.py server/agent_session/async_subagent_policy.py server/agent_session/runtime_contract.py
git diff --check
git add server/agent_session/deepagents_runtime.py server/agent_session/async_subagent_policy.py server/agent_session/runtime_contract.py server/tests/test_agent_session_deepagents_runtime.py server/tests/test_tool_platform_architecture.py
git commit -m "feat(agent): remove model delegation from controlled work units"
```

## Task 12I: Event compatibility and final acceptance

**Files:**

- Modify: `server/agent_session/events.py`
- Modify: `server/agent_session/services/event_broadcast.py`
- Modify: `server/tests/test_agent_subagent_orchestrator.py`
- Modify: `server/tests/test_agent_session_deepagents_events.py`
- Modify: `client/src/test/AgentWorkbenchRuntime.test.tsx` only if the existing
  generic fallback fails
- Modify: `docs/coding-agent-engineering-loop.md`
- Modify: `docs/plans/2026-07-18-controlled-tool-platform-integration.md`

### Step 1: Add event contract tests

Cover versioned, redacted WorkUnit events; stable event IDs; safe evidence
references; existing `async_subtask_*` compatibility; and generic Workbench
fallback behavior.

Do not add a new WorkUnit DAG UI.

### Step 2: Run focused backend acceptance

```powershell
python -m pytest `
  server/tests/test_agent_work_unit.py `
  server/tests/test_agent_work_unit_repository.py `
  server/tests/test_agent_subagent_orchestrator.py `
  server/tests/test_agent_async_subagents.py `
  server/tests/test_agent_session_deepagents_runtime.py `
  server/tests/test_agent_session_deepagents_events.py `
  server/tests/test_agent_phase_controller.py `
  server/tests/test_agent_tool_runtime_binding.py `
  server/tests/test_agent_execution_plan_recovery.py `
  server/tests/test_agent_goal_plan.py `
  server/tests/test_tool_platform_architecture.py -q
```

### Step 3: Run adjacent regression

```powershell
python -m pytest `
  server/tests/test_agent_permission.py `
  server/tests/test_agent_autonomy_mode.py `
  server/tests/test_agent_tool_trust.py `
  server/tests/test_agent_controlled_cutover.py `
  server/tests/test_agent_session_deepagents_runtime.py -q

Set-Location client
npx vitest run src/test/AgentWorkbenchRuntime.test.tsx src/test/CodingAgentGoldenPath.test.tsx
npm run typecheck
npm run build
Set-Location ..

python -m ruff check server/agent_session server/tests/test_agent_work_unit.py server/tests/test_agent_subagent_orchestrator.py
git diff --check
```

### Step 4: Document actual results and commit

Update the original integration plan with:

- actual commit hashes;
- focused and adjacent test counts;
- known limitations;
- confirmation that Task 13 was not started.

```powershell
git add server client/src/test docs/coding-agent-engineering-loop.md docs/plans/2026-07-18-controlled-tool-platform-integration.md
git commit -m "docs(agent): complete typed work unit orchestration"
```

## Rollback

Rollback affects only new Controlled Build runs:

- disable typed WorkUnit orchestration;
- omit `phase_boundary_driver=typed_work_unit.v1`;
- retain Controlled Gateway in parent-only mode;
- do not reinterpret already running sessions;
- leave durable WorkUnit history readable.

No rollback path may silently restore model-visible delegation tools inside an
already active typed WorkUnit session.
