# ADR-0001: Agent Session Is The Primary Agent Runtime

## Status
Accepted

## Context
Rapid iteration left several agent-adjacent surfaces in the codebase: Chat
Agent intent routing, Agent Session execution, Gateway integration, Heartbeat
scheduling, and Evaluation jobs. The main risk is allowing old workflow/run
concepts to become a second execution path for development-agent work.

The platform needs a single place to own agent lifecycle, transcript state,
HITL decisions, background task cancellation, recovery, and SSE updates.

## Decision
Use `server/agent_session/` and `AgentSessionService` as the only development
Agent runtime.

`server/chat_agent/` remains intent-only. It can classify a message as `chat`
or `agent` and suggest a directly-startable agent id, but it must not create
runs, persist workflow state, approve actions, or execute tools.

Gateway and Heartbeat remain experimental integration surfaces. Evaluation
remains a separate asynchronous evaluation-job system, not an Agent Session
state source.

## Consequences

### Positive
- One lifecycle owner for Agent runs.
- One transcript format through `AgentPart`.
- Permission resume, interrupt, and failure handling stay in one service.
- Frontend Chat can treat Agent Session as the execution source of truth.

### Negative
- Old workflow-backed documents and tests need periodic cleanup.
- Experimental Gateway and Heartbeat pages need explicit labeling until they
  become GA-backed product surfaces.

### Neutral
- Historical transcript compatibility can still exist, but only as display or
  migration code, not as a new execution path.

## Alternatives Considered

**Keep Chat Agent as a workflow-backed runtime**
- Rejected: recreates two agent lifecycle owners and increases state drift.

**Move Gateway or Heartbeat into the primary runtime**
- Rejected for now: both are experimental and have different product promises.

**Let Evaluation reuse Agent Session state**
- Rejected: evaluation runs have separate polling, scoring, artifacts, and
  deployment gates.

## References
- `docs/agent_session_migration.md`
- `server/agent_session/service.py`
- `server/chat_agent/service.py`
- `server/tests/test_chat_agent_intent.py`
