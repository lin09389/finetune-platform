# ADR-0011: Keep DeepAgents as the Only Agent Loop

## Status

Accepted

## Context

The product needs a stronger cross-turn AgentSession host, runtime rebinding, structured lifecycle events,
steering, follow-up messages, compaction records, extension hooks, and Trace-to-Train collection. Pi Agent
demonstrates a useful design: keep the model/tool loop thin and place product behavior around a strong session
host and event-driven extensions.

The repository already uses DeepAgents as its production model/tool execution harness. DeepAgents owns model
iteration, planning, tool selection, subagents, interrupts, and resume. Adding Pi or a new ReAct loop below or
above DeepAgents would create competing lifecycle, planning, tool, and approval semantics.

## Decision

DeepAgents remains the only production Agent execution loop. Pi is an architectural reference, not an
additional runtime dependency.

`AgentSessionService` remains the only development-Agent lifecycle owner and evolves as a thin product host:

- bind a session to its Workspace, model, tool catalog, execution environment, and context sources;
- own cross-turn persistence, cancellation, steering, follow-up, runtime replacement, and diagnostics;
- publish versioned structured lifecycle events from the existing persisted Agent-part facts;
- expose safe subscription points for UI projection, evaluation, automation, and Trace-to-Train;
- keep training jobs, desktop lifecycle, storage details, and extension code outside the DeepAgents loop.

The platform task workflow is a deterministic application state machine. It may coordinate approvals,
recovery, artifacts, training jobs, and idempotency, but it must not become a second LLM planner or decide the
next tool call.

If another Agent harness is evaluated later, it must implement an explicit `AgentRuntimeProvider` contract and
replace DeepAgents for a selected experimental session. Two harnesses must never be nested for one session.

## Consequences

### Positive

- Preserves the working DeepAgents integration and all Phase 0–10 recovery and approval behavior.
- Gives Electron, API, CLI/RPC, evaluation, and training-data collection one stable session/event boundary.
- Allows Pi-inspired steering, compaction, runtime rebinding, and extensions without a risky runtime rewrite.
- Keeps Trace-to-Train asynchronous and isolated from user-facing Agent success.

### Negative

- Some current `AgentSessionService` responsibilities must be separated behind smaller host/runtime services.
- DeepAgents upgrades remain a compatibility concern and need adapter-level contract tests.
- Public extensions cannot be enabled until event, permission, timeout, and failure-isolation contracts stabilize.

### Neutral

- `execution_plan` remains the planning fact source exposed by the platform; this ADR does not remove
  DeepAgents planning behavior.
- Existing Agent parts and repositories remain authoritative. A versioned event envelope is a projection and
  integration contract, not a second transcript database.

## Alternatives Considered

### Run Pi beneath DeepAgents

Rejected. Both systems would own model/tool iteration and context, creating nested loops and ambiguous abort,
approval, token, and completion semantics.

### Replace DeepAgents with Pi now

Rejected. It would discard mature interrupt/resume, subagent, persistence, and test coverage without evidence
that the replacement improves product outcomes.

### Put a second AI workflow planner above DeepAgents

Rejected. The platform workflow must remain deterministic. Complex tool decisions stay in the selected Agent
harness; durable application state stays in platform services.

## Guardrails

- Architecture tests must prevent any new production Agent loop or approval state machine.
- Event subscribers must be timeout-bounded and unable to corrupt the authoritative session transaction.
- Trace collection must be optional, privacy-scoped, and unable to fail the primary Agent turn.
- Runtime replacement must close the old binding before constructing the new Workspace-bound services.
- Persisted event schemas require explicit versions and backward-compatible readers or migrations.

## References

- `docs/adr/0001-agent-session-as-primary-agent-runtime.md`
- `docs/plans/2026-07-10-personal-ai-engineer-agent-product-design.md`
- `docs/plans/2026-07-13-trusted-local-ai-engineer-roadmap.md`
- `server/agent_session/service.py`
- `server/agent_session/runtime_factory.py`
- `server/agent_session/execution_plan.py`
