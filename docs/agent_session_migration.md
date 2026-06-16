# Agent Session Architecture Boundary

## Current State

The development-agent path is centered on `AgentSessionService` and the
`server/agent_session/` package.

- Create a run: `POST /agent-sessions`
- Advance a run: `POST /agent-sessions/{session_id}/prompt`
- Stream run state: `GET /agent-sessions/{session_id}/events/stream`
- Approve HITL tool calls: `POST /agent-permissions/{id}/approve|reject`
- Runtime output: `AgentPart` transcript plus session `metadata.state`

`/chat-agent/intent` is intentionally narrow. It classifies a user message as
`chat` or `agent` and may suggest a directly-startable agent id. It does not
create runs, persist workflow state, approve actions, or execute tools.

## Ownership

- **Agent Session** owns agent lifecycle, background tasks, recovery, SSE events,
  transcript parts, HITL decisions, and runtime policy.
- **Chat Agent** owns intent routing only.
- **Chat UI** decides whether to send ordinary chat or create an Agent Session.
- **Gateway / Heartbeat** remain experimental integration surfaces, not alternate
  Agent Session runtimes.
- **Evaluation** owns asynchronous evaluation runs and polling/SSE progress,
  separate from Agent Session state.

## Removed Boundaries

These older concepts are no longer the safety or runtime boundary for the main
agent path:

- workflow-backed Chat Agent runs
- platform patch engine path checks
- platform command allowlist / command policy

Current boundaries are:

- DeepAgents workspace backend isolation
- DeepAgents HITL approval for write/edit/execute tool calls
- Agent runtime policy and permission metadata
- Agent Session repository and state machine

## Guardrails

- New Chat Agent code must not create workflow runs or agent-run records.
- New frontend agent execution UI should use Agent Session data, not workflow
  run data.
- Gateway and Heartbeat pages must keep their experimental framing unless they
  become GA-backed product surfaces.
