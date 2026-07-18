# Controlled Tool Platform Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task.

**Goal:** Integrate the existing typed tool-platform foundation into current `master`, then make the platform own Build planning, phase tool routing, and subagent work units while retaining DeepAgents as the only model/tool loop.

**Architecture:** Port only the semantic Task 1/2 files from `codex/tool-platform`, establish a canonical Tool Gateway, bind a typed Goal Plan to the existing execution-plan/session facts, and run DeepAgents with a phase-specific catalog. Keep legacy Build as a rollback path and leave Train/Hybrid on their current behavior until a separate migration gate.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLite, DeepAgents/LangGraph, pytest, React 18/TypeScript/Vitest for later projections.

---

## Preconditions and ownership

- Implement from a fresh branch/worktree based on the current `master` (`8b2477e` at plan creation).
- Treat `codex/tool-platform` commit `87cf803` as a source reference, not as a branch to merge.
- Do not cherry-pick `8888bd3` or `96f0b93`; they contain an older, mixed Agent Session baseline.
- Do not change current Train/Hybrid tool behavior during Build cutover.
- Do not add Redis, a Tool Runtime Worker, LSP, Web, Scheduler, or a frontend transport rewrite in this plan.
- Preserve existing DeepAgents HITL and session approval persistence; no second approval engine.

## Milestone 1: Selective semantic foundation

Detailed execution sequencing, file ownership, and reusable external-Agent prompts are defined in:

- `docs/plans/2026-07-18-milestone1-selective-tool-foundation.md`
- `docs/plans/2026-07-18-milestone1-agent-prompts.md`

Those documents refine this milestone into one audit task, three dependency-ordered implementation tasks, and one read-only review task. They supersede the commit sequencing below when the two descriptions differ.

### Task 1: Freeze the integration baseline and branch provenance

**Files:**
- Create: `docs/audits/2026-07-18-tool-platform-integration-baseline.md`
- Test: `server/tests/test_tool_platform_architecture.py`

**Step 1: Write the failing architecture test**

Assert that production imports use only `tool_platform.*`, and that no new module defines a second `ToolKind`, Agent loop, or approval store.

**Step 2: Run the test and confirm it fails**

Run:

```powershell
python -m pytest server/tests/test_tool_platform_architecture.py -q
```

Expected: FAIL because `tool_platform` is not present on current `master`.

**Step 3: Record provenance**

Document:

- current merge base and branch heads;
- files owned by commits `acdd7d2`, `d517fea`, `b697e87`, `6e4b390`, `910f2fb`, and `87cf803`;
- explicit exclusion of mixed baseline commits `8888bd3` and `96f0b93`;
- current targeted regression suites and known streaming-test limitation.

**Step 4: Commit**

```powershell
git add docs/audits/2026-07-18-tool-platform-integration-baseline.md server/tests/test_tool_platform_architecture.py
git commit -m "test(tools): freeze tool platform integration boundary"
```

### Task 2: Port canonical taxonomy and models

**Files:**
- Create: `server/tool_platform/__init__.py`
- Create: `server/tool_platform/taxonomy.py`
- Create: `server/tool_platform/models.py`
- Create: `server/tests/test_tool_platform_taxonomy.py`
- Create: `server/tests/test_tool_platform_models.py`

**Step 1: Port tests first**

Use the final versions at `codex/tool-platform:server/tests/test_tool_platform_{taxonomy,models}.py` as references. Retain the canonical top-level import identity assertion.

**Step 2: Confirm failure**

```powershell
python -m pytest server/tests/test_tool_platform_taxonomy.py server/tests/test_tool_platform_models.py -q
```

Expected: import failure.

**Step 3: Port the final hardened implementations**

Preserve:

- exhaustive `ToolKind` defaults;
- separate data-mutation and composable execution-effect axes;
- fail-closed risk defaults;
- strict Pydantic v2 models;
- recursively frozen JSON;
- nested token/header/URL-query redaction;
- stable event ID, attempt, sequence, and UTC timestamps.

Do not port changes to Agent Session files from the old branch.

**Step 4: Verify and commit**

```powershell
python -m pytest server/tests/test_tool_platform_taxonomy.py server/tests/test_tool_platform_models.py -q
python -m ruff check server/tool_platform server/tests/test_tool_platform_taxonomy.py server/tests/test_tool_platform_models.py
git diff --check
git add server/tool_platform server/tests/test_tool_platform_taxonomy.py server/tests/test_tool_platform_models.py
git commit -m "feat(tools): port canonical tool contracts"
```

### Task 3: Port typed definitions, registry, and catalog

**Files:**
- Create: `server/tool_platform/definition.py`
- Create: `server/tool_platform/registry.py`
- Create: `server/tool_platform/catalog.py`
- Create: `server/tests/test_tool_platform_registry.py`

**Step 1: Port the final tests from `87cf803`**

Cover strict async handlers/probes, alias and version conflicts, absent facts failing closed, explicit availability refresh, JSON-only snapshots, deep immutability, and strict input/output validation.

**Step 2: Confirm failure**

```powershell
python -m pytest server/tests/test_tool_platform_registry.py -q
```

**Step 3: Port the hardened code**

Catalog reads must not run probes. `freeze()` freezes definitions but explicit availability refresh remains possible. Required runtime, capability, agent, provider, model, and platform facts fail closed.

**Step 4: Verify and commit**

```powershell
python -m pytest server/tests/test_tool_platform_taxonomy.py server/tests/test_tool_platform_models.py server/tests/test_tool_platform_registry.py -q
python -m ruff check server/tool_platform server/tests/test_tool_platform_*.py
git diff --check
git add server/tool_platform server/tests/test_tool_platform_registry.py
git commit -m "feat(tools): port typed registry and catalog"
```

### Task 4: Compile Agent Manifest selectors into projection context

**Files:**
- Modify: `server/agent_session/execution_context.py`
- Modify: `server/agent_session/agent_registry.py`
- Modify: `server/tests/test_agent_registry.py`

**Step 1: Add failing selector tests**

Cover three distinct `allowed` states:

- absent: no name restriction;
- explicit empty: deny all in controlled projection;
- non-empty: authoritative allow list.

Also cover kinds, denied names, risk ceiling, runtime, capability, and provider/model/platform facts.

**Step 2: Implement a pure bridge**

Add a bridge equivalent to `AgentRegistry.tool_projection_context(...)`, but keep `enforcement_status="legacy_runtime"`. It must not claim that DeepAgents is already enforcing the projection.

**Step 3: Verify compatibility**

```powershell
python -m pytest server/tests/test_agent_registry.py server/tests/test_agent_permission.py -q
git diff --check
```

**Step 4: Commit**

```powershell
git add server/agent_session/execution_context.py server/agent_session/agent_registry.py server/tests/test_agent_registry.py
git commit -m "feat(agent): compile manifest tool projections"
```

## Milestone 2: DeepAgents compatibility and Tool Gateway

### Task 5: Characterize the installed DeepAgents tool surface

**Files:**
- Create: `server/tool_platform/adapters/__init__.py`
- Create: `server/tool_platform/adapters/deepagents.py`
- Create: `server/tests/test_tool_platform_deepagents_adapter.py`
- Create: `docs/audits/2026-07-18-deepagents-tool-surface.md`

**Step 1: Write contract tests using an injected fake factory**

The tests must identify:

- which tool schemas are passed through `AgentRuntimeContract.tools`;
- which filesystem/execute tools DeepAgents synthesizes from the backend;
- whether individual built-ins can be hidden;
- where middleware can intercept invocation before side effects;
- how interrupt metadata names tools.

No test may require network access or the real model.

**Step 2: Implement a catalog adapter only**

The adapter converts known DeepAgents tools into canonical definitions and records an explicit enforcement capability:

```python
class DeepAgentsEnforcementCapability(str, Enum):
    HIDDEN_AND_ENFORCED = "hidden_and_enforced"
    VISIBLE_BUT_ENFORCED = "visible_but_enforced"
    UNSUPPORTED = "unsupported"
```

Unsupported tools must block controlled-mode startup.

**Step 3: Verify and commit**

```powershell
python -m pytest server/tests/test_tool_platform_deepagents_adapter.py server/tests/test_agent_session_deepagents_runtime.py -q
git add server/tool_platform/adapters server/tests/test_tool_platform_deepagents_adapter.py docs/audits/2026-07-18-deepagents-tool-surface.md
git commit -m "test(tools): characterize deepagents tool enforcement"
```

### Task 6: Implement deterministic tool policy decisions

**Files:**
- Create: `server/tool_platform/policy.py`
- Create: `server/tests/test_tool_platform_policy.py`
- Modify: `server/agent_session/permission.py`
- Modify: `server/tests/test_agent_permission.py`

**Step 1: Define the decision DTO**

```python
class ToolPolicyDecision(BaseModel):
    decision: Literal["allow", "ask", "deny"]
    reason_code: str
    canonical_name: str
    risk: ToolRisk
    matched_rules: tuple[str, ...] = ()
```

**Step 2: Write table-driven failing tests**

Test read-only defaults, workspace writes, process/network effects, credentials, destructive operations, explicit denies, risk ceiling, missing facts, session trust, and unknown tools.

**Step 3: Implement the evaluator**

The evaluator is pure and cannot persist approval state. Adapt existing autonomy/HITL metadata into policy facts; do not remove existing `resolve_deepagents_interrupt_on` behavior yet.

**Step 4: Verify and commit**

```powershell
python -m pytest server/tests/test_tool_platform_policy.py server/tests/test_agent_permission.py -q
git add server/tool_platform/policy.py server/tests/test_tool_platform_policy.py server/agent_session/permission.py server/tests/test_agent_permission.py
git commit -m "feat(tools): add deterministic tool policy"
```

### Task 7: Implement the canonical Tool Gateway

**Files:**
- Create: `server/tool_platform/gateway.py`
- Create: `server/tool_platform/handlers.py`
- Create: `server/tests/test_tool_platform_gateway.py`
- Modify: `server/agent_session/deepagents_events.py`
- Modify: `server/tests/test_agent_session_deepagents_events.py`

**Step 1: Write failing invocation-pipeline tests**

Cover resolution, strict input validation, policy allow/ask/deny, handler timeout, cancellation, output validation, redaction, canonical started/completed/failed events, and idempotent terminal-event handling.

**Step 2: Implement the gateway pipeline**

```text
resolve -> availability -> input validate -> policy -> approval adapter
        -> dispatch -> output validate -> redact -> canonical event
```

The first dispatcher is in-process only. It accepts injected handlers and an injected event sink. It does not create a Worker or database tables.

**Step 3: Project canonical events through the existing event mapper**

Reuse `AgentSessionRepository.add_event` and current part/event projection. Do not add a second event log.

**Step 4: Verify and commit**

```powershell
python -m pytest server/tests/test_tool_platform_gateway.py server/tests/test_agent_session_deepagents_events.py -q
git add server/tool_platform/gateway.py server/tool_platform/handlers.py server/tests/test_tool_platform_gateway.py server/agent_session/deepagents_events.py server/tests/test_agent_session_deepagents_events.py
git commit -m "feat(tools): route canonical tool invocations"
```

## Milestone 3: Shadow binding and controlled Build

### Task 8: Bind catalog snapshots to the runtime contract

**Files:**
- Modify: `server/agent_session/runtime_contract.py`
- Modify: `server/agent_session/runtime_factory.py`
- Modify: `server/agent_session/deepagents_runtime.py`
- Modify: `server/core/config.py`
- Create: `server/tests/test_agent_tool_runtime_binding.py`

**Step 1: Add orchestration mode**

Use a creation-time value:

```python
Literal["legacy", "shadow", "controlled"]
```

Persist it in session metadata. Running sessions cannot switch mode.

**Step 2: Add failing shadow tests**

Assert that shadow mode executes the legacy path, records catalog differences safely, never changes approval behavior, and never runs availability probes during contract construction.

**Step 3: Compile the runtime binding**

Add immutable catalog/policy/enforcement facts to `AgentRuntimeContract`. Keep `tools=` behavior unchanged in shadow mode.

**Step 4: Verify and commit**

```powershell
python -m pytest server/tests/test_agent_tool_runtime_binding.py server/tests/test_agent_session_deepagents_runtime.py server/tests/test_agent_permission.py -q
git add server/agent_session/runtime_contract.py server/agent_session/runtime_factory.py server/agent_session/deepagents_runtime.py server/core/config.py server/tests/test_agent_tool_runtime_binding.py
git commit -m "feat(agent): bind shadow tool catalogs to sessions"
```

### Task 9: Migrate Build tools incrementally

**Files:**
- Create: `server/tool_platform/builtins/filesystem.py`
- Create: `server/tool_platform/builtins/git.py`
- Create: `server/tool_platform/builtins/execute.py`
- Create: `server/tests/test_tool_platform_build_tools.py`
- Create: `server/tests/test_agent_session_git_tools.py`
- Modify: `server/agent_session/runtime_contract.py`
- Modify: `server/agent_session/deepagents_runtime.py`

**Step 1: Register read/search and Git-read tools**

Use canonical metadata and adapters; preserve `/workspace/` virtual paths. Port `git_tools.py` behavior only after reviewing it independently against current `master`.

**Step 2: Register write/edit and execute/test**

All side effects must pass Gateway policy. If a DeepAgents built-in cannot be hidden, its backend/middleware path must still enforce the same decision.

**Step 3: Keep training tools legacy**

Do not change `server/agent_session/training_tools.py` in this task.

**Step 4: Verify and commit**

```powershell
python -m pytest server/tests/test_tool_platform_build_tools.py server/tests/test_agent_session_deepagents_runtime.py server/tests/test_agent_session_git_tools.py server/tests/test_agent_permission.py -q
git commit -m "feat(agent): enforce controlled build tool routing"
```

## Milestone 4: Typed planning and subagent work units

### Task 10: Add the typed Goal Plan

**Files:**
- Create: `server/agent_session/goal_plan.py`
- Create: `server/agent_session/goal_planner.py`
- Create: `server/tests/test_agent_goal_plan.py`
- Modify: `server/agent_session/execution_plan.py`
- Modify: `server/tests/test_agent_execution_plan.py`
- Modify: `server/agent_session/services/model_call_coordinator.py`

**Step 1: Define a versioned visible plan schema**

Include goal, constraints, phases, work-unit candidates, dependencies, file scopes, evidence requirements, risk summaries, and bounded retry policy. Exclude hidden reasoning.

**Step 2: Implement one bounded planning call**

Use the current Build model through the existing model-call coordinator. The planner has no tools. Strictly validate output and permit one repair/replan attempt.

**Step 3: Persist through the existing execution-plan fact source**

Do not create another plan database. Add backward-compatible normalization/migration for older execution plans.

**Step 4: Verify and commit**

```powershell
python -m pytest server/tests/test_agent_goal_plan.py server/tests/test_agent_execution_plan.py server/tests/test_agent_execution_plan_recovery.py -q
git commit -m "feat(agent): add typed goal planning"
```

### Task 11: Add deterministic phase routing

**Files:**
- Create: `server/agent_session/phase_controller.py`
- Create: `server/agent_session/phase_tool_router.py`
- Create: `server/tests/test_agent_phase_controller.py`
- Modify: `server/agent_session/runtime_contract.py`
- Modify: `server/agent_session/services/background_task_manager.py`

**Step 1: Test the phase state machine**

Cover Inspect, Plan, Implement, Verify, Review, Deliver; verification failure returning to Implement; retry exhaustion; approval wait; steering queued at boundaries; and restart recovery.

**Step 2: Compile phase-specific projection context**

The router combines Agent Manifest, Goal Plan phase, runtime facts, provider/model facts, autonomy mode, and session trust. Missing facts block controlled startup.

**Step 3: Verify and commit**

```powershell
python -m pytest server/tests/test_agent_phase_controller.py server/tests/test_agent_tool_runtime_binding.py server/tests/test_agent_execution_plan_recovery.py -q
git commit -m "feat(agent): route tools by execution phase"
```

### Task 12: Replace model-decided subagent creation in controlled mode

**Files:**
- Create: `server/agent_session/work_unit.py`
- Create: `server/agent_session/subagent_orchestrator.py`
- Create: `server/tests/test_agent_subagent_orchestrator.py`
- Modify: `server/agent_session/async_subagents.py`
- Modify: `server/agent_session/async_subagent_policy.py`
- Modify: `server/agent_session/deepagents_runtime.py`
- Modify: `server/tests/test_agent_session_deepagents_runtime.py`

**Step 1: Define `WorkUnit`**

Bind parent session, plan node, role, model, environment, file scope, tool projection, budget, dependencies, artifacts, retry, and cancellation.

**Step 2: Test orchestration rules**

- Explore/Review are read-only and may run concurrently.
- Implement writes are serial until worktrees exist.
- Children cannot exceed parent authority or Workspace.
- Parent cancellation interrupts children.
- Child failure does not corrupt the parent session.
- Restart recovery is idempotent.

**Step 3: Use `AsyncSubagentService` as execution plumbing**

Controlled mode removes `start_async_task`, `update_async_task`, and related tools from the model catalog. The orchestrator calls the service directly. Legacy mode remains unchanged.

**Step 4: Verify and commit**

```powershell
python -m pytest server/tests/test_agent_subagent_orchestrator.py server/tests/test_agent_session_deepagents_runtime.py server/tests/test_agent_execution_plan_recovery.py -q
git commit -m "feat(agent): orchestrate typed subagent work units"
```

## Milestone 5: Execution boundary and cutover

### Task 13: Introduce the execution-environment interface

**Files:**
- Create: `server/agent_session/execution_environment.py`
- Create: `server/agent_session/environments/local_workspace.py`
- Create: `server/tests/test_agent_execution_environment.py`
- Modify: `server/agent_session/runtime.py`
- Modify: `server/agent_session/runtime_contract.py`

**Step 1: Define the interface**

It exposes environment identity, Workspace root, filesystem backend, shell backend, cancellation, cleanup, and mutation-evidence hooks. The first implementation wraps current local behavior.

**Step 2: Add path, cancellation, and cleanup tests**

Do not implement Docker, sandboxing, or worktrees yet. Preserve current virtual `/workspace/` semantics.

**Step 3: Verify and commit**

```powershell
python -m pytest server/tests/test_agent_execution_environment.py server/tests/test_agent_session_deepagents_runtime.py -q
git commit -m "refactor(agent): abstract execution environments"
```

### Task 14: Cut over new Build sessions with rollback

**Files:**
- Modify: `server/core/config.py`
- Modify: `server/api/agent_sessions.py`
- Modify: `server/agent_session/services/session_lifecycle.py`
- Create: `server/tests/test_agent_controlled_build_cutover.py`
- Modify: `docs/coding-agent-engineering-loop.md`
- Modify: `README.md`
- Modify: `README_EN.md`

**Step 1: Define cutover rules**

- New Build sessions default to controlled only after all gates pass.
- Existing sessions retain their creation mode.
- Train/Hybrid remain on current behavior.
- One configuration switch can return new Build sessions to legacy.

**Step 2: Run the coding golden suite**

Cover Python bug fix, React change, cross-stack feature, multi-file refactor, failed-test repair, refresh recovery, path isolation, approval resume, parent/child cancellation, and final diff/test evidence.

**Step 3: Run broad regression**

```powershell
python -m pytest server/tests/test_tool_platform_*.py server/tests/test_agent_* -q
Set-Location client
npm run typecheck
npx vitest run src/test/AgentWorkbenchRuntime.test.tsx src/test/AgentRunTimeline.test.tsx
npm run build
Set-Location ..
git diff --check
```

**Step 4: Document and commit**

```powershell
git commit -m "feat(agent): default build sessions to controlled orchestration"
```

## Deferred follow-up

Only after controlled Build is stable:

1. task-level Git worktrees and mutation rollback;
2. isolated Tool Runtime Worker for long-running execution;
3. Python and TypeScript/JavaScript LSP;
4. Web Search/Fetch with SSRF defenses;
5. background task scheduler;
6. OpenAI Tool Calling and MCP provider adapters;
7. explicit Train/Hybrid migration;
8. Workbench redesign and any SSE-to-WebSocket transport decision.

## Final acceptance

- DeepAgents is still the only production model/tool iteration loop.
- Platform owns the durable Goal Plan, phase, catalog projection, policy, work-unit graph, and execution-environment binding.
- Controlled Build cannot execute an unknown or unprojected tool.
- Approval occurs exactly once through the existing session/DeepAgents integration.
- Refresh/restart preserves plan, phase, work units, catalog binding, and evidence.
- A rollback switch affects only new sessions and does not reinterpret running sessions.
- Train/Hybrid continue to operate as before until separately migrated.
