# ADR-0013: Use Typed WorkUnits for Controlled Build Orchestration

## Status

Accepted

## Context

ADR-0012 made the platform responsible for global planning, phase control,
tool projection, and typed subagent work units while retaining DeepAgents as
the only production model/tool loop.

Tasks 10 and 11 introduced a bounded Goal Plan and a deterministic phase
controller. The existing `AsyncSubagentService` still exposes model-facing
tools that let DeepAgents decide when to create, restart, list, or cancel
subagents. In addition, one monolithic DeepAgents `run_prompt()` cannot rebind
the phase-specific catalog during execution.

The product needs deterministic, recoverable subagent orchestration without a
second autonomous loop, a new distributed service, or write conflicts in the
shared local workspace.

## Decision

Controlled Build sessions use strict `agent.work_unit.v1` contracts compiled
deterministically from the attached Goal Plan.

The platform owns WorkUnit identity, role assignment, dependencies, scope,
budget, attempts, retries, cancellation, Review gating, recovery, and phase
boundaries.

DeepAgents remains the only model/tool loop inside a supplied WorkUnit.
Parent-owned WorkUnits invoke DeepAgents in scoped turns so the runtime
contract can be rebuilt between phases.

Until task-level worktrees exist:

- the parent Build Agent is the only writer;
- Explore and Review children are read-only;
- child authority is the intersection of parent authority, role policy,
  WorkUnit scope, phase projection, and workspace policy;
- child side-effect requests are denied without user approval or authority
  escalation.

The fixed role mapping is:

- Inspect and Plan → Explore child;
- Implement, Verify, and Deliver → parent Build;
- Review → Review child;
- unknown phases → parent Build.

All WorkUnit failures retry up to the Goal Plan `max_phase_retries` budget.
Retries use a new attempt but never widen authority. Exhausted child work
degrades to a parent fallback; exhausted Review correction moves the parent
session to `needs_manual_review`.

WorkUnit state reuses `agent_subtasks` and `agent_subtask_events`; SQLite is the
fact source. Stable IDs and attempt revisions make compilation, scheduling,
restart recovery, and late result handling idempotent.

Controlled mode removes model-visible async-subagent management tools while
the WorkUnit orchestrator is active. Legacy, Shadow, Train, and Hybrid behavior
is unchanged.

The platform writes `phase_boundary_driver=typed_work_unit.v1` only after a
valid graph is durably persisted and the orchestrator is active.

## Consequences

### Positive

- Subagent creation and phase advancement become deterministic and testable.
- Child authority cannot exceed parent authority.
- Shared-workspace write conflicts are avoided before worktrees exist.
- Phase-specific tool catalogs can be enforced between scoped DeepAgents runs.
- Existing child-session execution, HITL, checkpointing, SQLite, SSE, and
  Workbench projections are reused.
- Orchestration facts are independent of the future Agent runtime provider.

### Negative

- Parent execution changes from one monolithic DeepAgents run to several
  scoped runs in Controlled Build mode.
- The runtime adapter must distinguish WorkUnit completion from whole-session
  completion.
- Retrying every failure class may spend model calls on deterministic failures,
  although the budget remains bounded and authority remains fixed.
- The existing `agent_subtasks` envelope becomes responsible for both legacy
  async tasks and typed WorkUnits, requiring strict discriminators and
  compatibility tests.

### Neutral

- Dedicated WorkUnit UI is deferred.
- Worktrees, sandbox providers, and remote workers remain future work.
- Parent-only fallback keeps Controlled Build usable when planning or
  orchestration facts are incomplete.

## Alternatives considered

### Keep model-facing async-subagent tools

Rejected because the model would continue to own global delegation decisions,
dependencies, retries, and cancellation.

### Add an autonomous planner/orchestrator model loop

Rejected because it would create a second Agent loop and weaken deterministic
recovery and authority.

### Use one monolithic DeepAgents run and observe phases

Rejected because phase-specific tool projection cannot be rebound reliably
inside the already running graph.

### Permit one serial write-capable Implement child

Rejected for Task 12 because the parent and child would share a writable local
workspace without task-level worktree isolation.

### Add a new WorkUnit database

Rejected because the existing SQLite subtask tables already provide durable
task, child-session, event, and recovery plumbing.

## Guardrails

- Task 12 is Build-only and Controlled-only.
- At most 12 WorkUnits and two concurrent read-only children.
- Child tools, paths, capabilities, model, and environment can only be
  intersected with parent facts.
- Unknown or ambiguous phases remain parent-owned.
- Missing facts do not enable the typed boundary driver.
- Terminal WorkUnit states are monotonic.
- WorkUnit events are versioned, JSON-only, and recursively redacted.
- No hidden reasoning is persisted.
- No new approval state machine is introduced.
- Architecture tests preserve DeepAgents as the only model/tool loop.

## References

- `docs/adr/0012-platform-owned-orchestration-around-deepagents.md`
- `docs/plans/2026-07-18-controlled-tool-platform-integration.md`
- `docs/plans/2026-07-29-task12-typed-work-unit-orchestration-design.md`
- `server/agent_session/goal_plan.py`
- `server/agent_session/phase_controller.py`
- `server/agent_session/phase_tool_router.py`
- `server/agent_session/async_subagents.py`
- `server/agent_session/deepagents_runtime.py`
