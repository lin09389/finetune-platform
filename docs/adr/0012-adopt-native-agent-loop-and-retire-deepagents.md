# ADR-0012: Adopt a Native Agent Loop and Retire DeepAgents

## Status

Accepted

## Context

Phase 0-10 established a working Agent product around `AgentSessionService`, DeepAgents, persisted parts/events,
SSE, approval recovery, coding diffs, training tools, and the Electron Workbench. The product is not yet
released, so it does not carry a public session or wire-protocol compatibility obligation.

A source-level study of `C:\Users\JHJ\Desktop\grok-build` showed that its reliability comes primarily from
explicit runtime boundaries rather than a large prompt or a single monolithic loop. Its relevant structure is:

- a session actor that owns commands, queueing, cancellation, pending interactions, and recovery;
- a separate model/tool sampling loop;
- a serialized conversation/token state owner;
- a tool runtime with policy, hooks, execution context, and structured results;
- append-only lifecycle facts, replay, compaction, and file-aware rewind;
- deterministic goal roles above the sampling loop rather than a second implicit ReAct loop.

The current integration concentrates graph construction, prompt assembly, tools, event translation, approvals,
trajectory correction, and completion behavior around `deepagents_runtime.py` and its compatibility modules.
Continuing to wrap this integration would keep DeepAgents semantics as the product's permanent constraint.

## Decision

The project will progressively replace DeepAgents with a self-owned `NativeAgentLoop`. DeepAgents remains only
as a temporary implementation dependency until the Native Build runtime passes the cutover gates; it will then
be removed completely.

The migration follows these rules:

1. The first Native production scope is **Build only**. Train and Hybrid are temporarily disabled; no
   DeepAgents-to-v2 protocol adapter is built.
2. A session binds to exactly one runtime. Native and DeepAgents are never nested and never execute one turn
   together.
3. The frontend and backend switch directly to a versioned bidirectional WebSocket v2 protocol. The old
   SSE/parts wire protocol is not preserved.
4. Existing Agent sessions are deliberately cleared by a scoped migration. Workspace, model, dataset,
   training, inference, and other product data are not deleted.
5. The authoritative session record is an append-only event log with monotonic per-session sequence numbers.
   Periodic snapshots are disposable recovery accelerators, not a second source of truth.
6. Ordinary messages enter a FIFO follow-up queue. Steering is injected only at a safe boundary after the
   active tool finishes. Send-now cancels the current turn before starting the new message; no command mutates
   a tool invocation in flight.
7. Native Build uses a default Goal Workflow with Planner, Implementer, Verifier, and Strategist roles. All
   roles use the selected Build model with separate contexts, prompts, structured outputs, and usage accounting.
   This Goal Graph replaces the old Build `execution_plan` fact model.
8. The first release is single-session and does not expose subagents. Subagents return only after isolated
   worktree execution is available.
9. The model may request a tool but cannot authorize it. Session Host, hooks, permission policy, pending
   approval, and execution environment form the enforcement path.
10. `ExecutionEnvironmentProvider` is introduced before the Native loop is connected to tools. Existing local
    and WSL execution may implement the initial provider, but a fail-closed trusted sandbox is required before
    Native becomes the default Build runtime.
11. Rewind restores both conversation state and Agent-owned file changes. Automatic file restoration is limited
    to text files under a configured size cap. Binary, large, symlinked, or externally modified files require
    explicit manual resolution.
12. Trace collection records local, redacted structural events by default. Source bodies and full prompts are
    excluded unless the user explicitly selects them; training data requires manual review.
13. The Agent Workbench is rewritten against v2. It retains the warm editorial/terra-cotta identity but replaces
    the current information architecture and component hierarchy.

## Consequences

### Positive

- The product owns queueing, steering, cancellation, approvals, compaction, recovery, and protocol evolution.
- Electron, future CLI/RPC, evaluation, UI, and Trace-to-Train consume one stable event model.
- Append-only history and file snapshots make rewind and incident diagnosis explicit.
- Direct protocol replacement avoids a long-lived compatibility layer before public release.
- Disabling Train/Hybrid avoids maintaining two frontend protocols during the migration.

### Negative

- DeepAgents' mature interrupt, graph checkpoint, subagent, and tool behavior must be deliberately reimplemented
  and independently verified.
- Build availability cannot cut over until the sandbox, approval, replay, rewind, and real-model gates pass.
- Existing Agent sessions will be removed and cannot be opened after the v2 migration.
- Train/Hybrid temporarily regress from available workflows to disabled product surfaces.
- Rewriting the Workbench increases the size of the migration and requires a frozen protocol plus visual gates.

## Alternatives Considered

### Keep DeepAgents permanently and only thin the host

Rejected. This was ADR-0011. It lowers short-term risk but leaves the product coupled to DeepAgents' graph,
interrupt, parts, and checkpoint semantics.

### Nest Pi or a Native runtime around DeepAgents

Rejected. Two loops would compete for context, tool selection, cancellation, completion, and approvals.

### Big-bang replacement

Rejected. The Native runtime is built behind an internal runtime binding and must pass shadow/deterministic
evaluation before Build cutover.

### Keep Train/Hybrid on DeepAgents behind a v2 adapter

Rejected for the migration period. It preserves features but creates an adapter whose only purpose is to prolong
the old runtime. Train/Hybrid will return through native tools after Build stabilizes.

### Preserve the old SSE/parts protocol

Rejected. The product is unpublished, and the old protocol encodes DeepAgents-specific facts that would distort
the Native design.

## Guardrails

- No production path may instantiate both Native and DeepAgents for one session.
- WebSocket connections are transports, never the session source of truth.
- Every persisted event includes schema version, session sequence, turn id, command id, causation id, timestamp,
  kind, and a bounded safe payload.
- Unknown events advance replay position but cannot mutate known projections.
- Tool authorization and sandbox enforcement remain outside model-generated content.
- Snapshot corruption must fall back to replay; it must not corrupt the event log.
- Rewind appends new branch/restore events and never deletes historical facts or invokes `git reset`.
- External file changes produce conflicts and are never silently overwritten.
- Trace collection failure cannot fail the user's Build turn.
- Native does not become the Build default until the cutover gates in the migration plan pass.

## References

- `docs/audits/2026-07-17-grok-build-architecture-fact-report.md`
- `docs/plans/2026-07-17-native-agent-loop-design.md`
- `docs/plans/2026-07-17-native-agent-loop-migration.md`
- `docs/adr/0011-keep-deepagents-as-the-only-agent-loop.md`
- `server/agent_session/service.py`
- `server/agent_session/deepagents_runtime.py`
- `client/src/agent/`
