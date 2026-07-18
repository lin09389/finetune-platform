# ADR-0012: Platform-Owned Orchestration Around DeepAgents

## Status

Accepted

## Context

ADR-0011 correctly keeps DeepAgents as the only production model/tool iteration loop. However, the current runtime also lets DeepAgents see a broad tool surface and decide global planning and subagent creation. Product evaluation found that tool selection, plan quality, and subagent decisions need stronger deterministic boundaries.

An existing `codex/tool-platform` branch proves a canonical taxonomy and typed registry approach, but it is not integrated into the current `master` and its first commit mixes unrelated Agent Session work with the tool contracts.

The product is maintained by an independent developer and remains local-first. The solution must reuse existing session, approval, recovery, SQLite, Electron, and DeepAgents behavior without introducing a second autonomous loop or a mandatory distributed service.

## Decision

DeepAgents remains the only production model/tool iteration loop, but it becomes a bounded worker runtime rather than the owner of product-wide orchestration.

The platform owns:

- a bounded, schema-constrained Goal Planner that uses the current Build model once per planning/replanning request;
- a deterministic phase controller backed by the existing execution-plan fact source;
- phase-specific tool projection and policy;
- typed subagent work-unit creation, dependency, scope, budget, cancellation, and recovery;
- tool validation, approval integration, execution routing, evidence, and canonical events;
- execution-environment binding and future worktree/sandbox selection.

DeepAgents owns:

- model iteration and local reasoning inside a supplied work unit;
- choosing the next call only from the supplied phase catalog;
- executing through the platform Tool Gateway;
- the existing interrupt/resume mechanism while it remains the runtime adapter.

There is no second ReAct loop. The Goal Planner cannot call tools or autonomously advance phases. The phase controller cannot generate free-form model decisions. A single session is bound to one runtime and one orchestration mode at creation.

ADR-0011 remains valid for the single-loop decision. This ADR supersedes only its statements that DeepAgents must own product-wide planning, global tool visibility, and subagent creation.

## Consequences

### Positive

- Preserves mature DeepAgents tool-call, checkpoint, interrupt, and resume behavior.
- Makes tool authority, phase transitions, and subagent scope testable without prompt-only rules.
- Reuses the existing execution plan, session repository, approval flow, and async-subagent service.
- Allows future runtime replacement without changing product orchestration semantics.
- Keeps the first migration local and in-process.

### Negative

- The DeepAgents adapter becomes a maintained compatibility boundary.
- Built-in DeepAgents tools may require middleware/backend enforcement if they cannot be hidden individually.
- Plan, phase, work-unit, and catalog schema migrations require disciplined compatibility tests.
- During migration, legacy and controlled Build modes must coexist.

### Neutral

- Existing Train/Hybrid tasks remain supported but initially use their current runtime behavior.
- An independent Tool Runtime Worker is deferred until long-running tools require process isolation.
- The Workbench continues consuming persisted session events; transport replacement is a separate decision.

## Alternatives Considered

### Merge the existing tool branch wholesale

Rejected because its older baseline bundles tool contracts with unrelated event, recovery, lifespan, and Git-tool changes.

### Keep all planning and subagent decisions inside DeepAgents

Rejected because prompt and manifest hints do not provide a reliable authority, recovery, or phase boundary.

### Implement a native Agent loop

Rejected because it duplicates working DeepAgents behavior and substantially expands maintenance burden.

### Add a separate autonomous planner loop above DeepAgents

Rejected. The accepted planner is a bounded typed call; durable advancement remains deterministic.

## Guardrails

- Architecture tests prevent another production model/tool loop or approval state machine.
- Controlled mode cannot start if its catalog, phase, execution environment, or policy facts are incomplete.
- Unknown tools and missing capability facts fail closed.
- Catalog and event projections are JSON-only and deeply immutable.
- Planner output never stores hidden reasoning.
- Child work units cannot exceed the parent's Workspace, authority, or resource budget.
- New sessions may roll back to legacy mode; a running session never changes orchestration mode in place.

## References

- `docs/adr/0001-agent-session-as-primary-agent-runtime.md`
- `docs/adr/0011-keep-deepagents-as-the-only-agent-loop.md`
- `docs/plans/2026-07-18-controlled-tool-platform-design.md`
- `server/agent_session/runtime_contract.py`
- `server/agent_session/execution_plan.py`
- `server/agent_session/deepagents_runtime.py`
- branch `codex/tool-platform` at `87cf803`
