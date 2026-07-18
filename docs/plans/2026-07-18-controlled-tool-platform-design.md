# Controlled Tool Platform and Orchestration Design

**Status:** Accepted for planning
**Date:** 2026-07-18
**Scope:** Build Agent first; existing Train and Hybrid flows remain on their current runtime path until a later explicit migration.

## 1. Objective

Build a Grok Build-inspired tool and orchestration control plane without replacing DeepAgents or creating a second ReAct loop.

The platform will own durable task planning, phase transitions, tool visibility, policy, approvals, subtask scheduling, recovery, and evidence. DeepAgents will remain the only production model/tool iteration loop, but each run will receive a bounded work unit and a phase-specific tool set.

## 2. Current Facts

- `AgentSessionService` owns the durable session lifecycle.
- `AgentRuntimeContract` already carries model, agent, tools, permissions, middleware, skills, subagents, interrupts, backend mode, and runtime policy.
- `DeepAgentsSessionRunner` still assembles local async-subagent tools directly.
- `execution_plan.py` is the persisted execution-plan fact source.
- `orchestration_planner.py` currently derives UI next actions; it is not a strategic task planner.
- Permission and HITL behavior is already implemented around DeepAgents interrupts and must remain authoritative during migration.
- `codex/tool-platform` contains useful Task 1/2 work, but its first commit also bundles unrelated Git tools, event batching, recovery, lifespan, and configuration changes from an older base.

## 3. Requirements

### Functional

- Define one canonical taxonomy, invocation model, tool definition, registry, and JSON-only catalog.
- Compile Agent Manifest, runtime, provider/model facts, phase, and user policy into a fail-closed tool projection.
- Route every migrated tool call through validation, policy, approval, execution, output validation, redaction, and event emission.
- Create a bounded structured Goal Plan using the current Build model without introducing a second autonomous loop.
- Persist phase and work-unit state in the existing execution-plan/session facts.
- Let the platform decide when to create Explore, Implement, Verify, and Review work units.
- Preserve current Train/Hybrid behavior while Build migrates.

### Non-functional

- Single-node and SQLite-first; no Redis, Kafka, or new mandatory service in the first cutover.
- Unknown tools, missing required facts, invalid schemas, and unsupported execution locations fail closed.
- No duplicate approval state machine or second session transcript.
- No hidden chain-of-thought persistence; plans contain only user-visible goals, steps, dependencies, scopes, and acceptance criteria.
- The legacy Build path remains available as a rollback switch until controlled mode passes the golden suite.
- Tool catalog reads never execute availability probes or external processes.
- Events and snapshots contain no handlers, probes, secrets, absolute paths, or unbounded raw output.

## 4. Alternatives

### A. Merge `codex/tool-platform` wholesale

Rejected. The branch has 3,573 inserted lines across 29 files and mixes semantic tool work with an older Agent Session resilience baseline. A wholesale merge would obscure ownership and make regressions difficult to attribute.

### B. Keep Registry as documentation only

Rejected. It would improve schemas but leave DeepAgents with the same global tool surface and would not solve tool selection, policy, or subagent behavior.

### C. Replace DeepAgents with a native loop

Rejected. It would duplicate mature model iteration, interrupt/resume, checkpoint, and tool-call behavior that the product already depends on.

### D. Platform-owned orchestration around a bounded DeepAgents worker

Accepted. The platform controls durable strategy and authority; DeepAgents performs local model/tool iteration inside a work unit.

## 5. Target Architecture

```text
Electron / Workbench / API
          |
    AgentSession Host
 queue / steering / recovery / approval / events
          |
   Structured Goal Planner
 one bounded model call -> typed plan
          |
     Phase Controller
 inspect -> plan -> implement -> verify -> review -> deliver
          |
 Phase Tool Router + Policy
 Registry projection / risk / capability / trust
          |
 DeepAgents Runtime Adapter
 one work unit, one bounded catalog, one model/tool loop
          |
       Tool Gateway
 validate -> authorize -> execute -> redact -> emit
          |
 Execution Environment
 workspace now; worktree and sandbox later
```

## 6. Ownership Boundaries

| Component | Owns | Must not own |
|---|---|---|
| Agent Session Host | lifecycle, queue, steering, recovery, approvals, event publication | next model tool call |
| Goal Planner | typed user-visible plan, phases, dependencies, acceptance criteria | iterative tool execution |
| Phase Controller | deterministic transitions and retry/return rules | free-form model reasoning |
| Tool Registry | definitions, schemas, availability facts, catalog projection | execution side effects |
| Tool Policy | allow/deny/ask decision from explicit facts | approval persistence |
| Tool Gateway | validation, authorization, dispatch, output validation, redaction, canonical events | task planning |
| Subagent Orchestrator | work-unit graph, role, scope, budget, dependencies | model iteration inside a work unit |
| DeepAgents | model calls, local reasoning, next tool call inside the supplied catalog, interrupt/resume integration | global plan, global tool catalog, worktree ownership |
| Execution Environment | filesystem/process boundary and mutation evidence | Agent/session state |

## 7. Planning and Phase Semantics

The planner is a bounded structured call using the current Build model. It returns a versioned plan with:

- goal and constraints;
- ordered phases;
- candidate work units and dependencies;
- allowed file scope where known;
- verification commands or evidence requirements;
- user-visible risks and approval needs.

It is not a loop. It cannot execute tools, approve actions, or mark work complete. The deterministic phase controller persists and advances the plan.

Default Build phases:

| Phase | Default tool kinds | Exit condition |
|---|---|---|
| Inspect | read, list, search, LSP, Git read | relevant files and constraints identified |
| Plan | read, search, plan/todo | typed plan accepted by controller |
| Implement | read, write, edit, Git read | planned changes recorded |
| Verify | execute, test, read, Git diff | required checks recorded with result |
| Review | read, Git diff, diagnostics | risks resolved or surfaced |
| Deliver | read-only evidence projection | final summary references persisted evidence |

Verification failure returns to Implement with a bounded retry count. Missing evidence blocks Deliver. Steering messages are queued and applied at a phase or tool boundary; they do not mutate a running tool invocation.

## 8. Subagent Semantics

The platform creates typed `WorkUnit` records for Explore, Implement, Verify, and Review. Each work unit binds:

- parent session and execution-plan node;
- agent role and model;
- workspace/execution environment;
- allowed tool projection and file scope;
- token/time/iteration budget;
- dependencies and expected artifacts;
- retry, cancellation, and completion rules.

DeepAgents executes a work unit. It does not decide whether a new child should exist. During migration, the existing `start_async_task` tools remain available only in legacy mode. Controlled Build mode removes them from the model catalog and lets the orchestrator create child sessions through `AsyncSubagentService` directly.

Write work units run serially until task-level worktrees exist. Read-only Explore and Review work units may run concurrently.

## 9. Tool Migration

The canonical registry initially describes both platform tools and DeepAgents built-ins. Before enforcement, a compatibility spike must confirm which built-ins can be hidden or intercepted by the installed DeepAgents version. If individual visibility cannot be controlled, the execution backend/middleware must enforce policy even when a schema remains model-visible.

Migration order:

1. read/list/search;
2. Git status/diff/log;
3. write/edit;
4. execute/test;
5. training tools after Build stabilizes;
6. LSP, Web, background runtime, Scheduler after the execution boundary exists.

## 10. Failure Modes

| Failure | Required behavior |
|---|---|
| Registry cannot resolve a name/version | reject; do not fall back to an arbitrary handler |
| Required runtime/capability/fact absent | exclude tool from projection |
| Policy or schema evaluation fails | reject and emit a safe diagnostic event |
| Approval requested | use the existing DeepAgents/session approval flow exactly once |
| Tool times out or crashes | record terminal canonical event; do not infer success |
| Planner emits invalid plan | retain current session, show actionable error, allow one bounded replan |
| Verification fails | return to Implement within retry budget |
| Subtask crashes | mark its work unit failed without corrupting the parent session |
| Controlled mode regression | switch new sessions to legacy; existing sessions remain bound to their creation mode |

## 11. Migration Gates

- Gate 0: selective Task 1/2 port; no runtime behavior change.
- Gate 1: shadow catalog matches legacy Build tools and approval facts.
- Gate 2: Tool Gateway enforces migrated platform tools while DeepAgents remains the loop.
- Gate 3: typed plan and phase routing pass deterministic recovery tests.
- Gate 4: platform-created subagents pass scope, cancellation, and parent-recovery tests.
- Gate 5: controlled Build becomes the default after coding golden scenarios, typecheck/build, and rollback tests pass.
- Train/Hybrid migration requires a separate accepted gate and is not implied by Build cutover.
