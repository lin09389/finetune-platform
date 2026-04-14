# Unified Agent Chat Architecture Design

> For this design pass, I used the brainstorming workflow to align the plan with the current codebase and current mainstream agent patterns.

**Goal:** Converge the current split Chat and Agent experiences into a single, mainstream agent-chat architecture with one user-facing entrypoint, server-side orchestration, streaming event updates, and explicit approval interrupts.

**Architecture:** Keep the existing backend intent routing, agent loop, timeline, resume, and patch-confirmation capabilities, but reorganize them behind one unified conversation API. The frontend becomes a single chat surface that renders messages plus execution events, while the backend owns routing, orchestration, approvals, and persistence.

**Tech Stack:** FastAPI, React 18, TypeScript, Ant Design, SSE, existing `server/agent/*` orchestration, existing `client/src/hooks/chat/useChatStream.ts`, local model backends, optional future MCP-style tool adapters.

---

## Why Change

The current project already has substantial agent capability:

- Backend intent detection and policy routing in `server/api/agent.py` and `server/agent/intent/*`
- Multi-step task execution in `POST /agent/run-loop`
- Resume flows in `POST /agent/resume` and `POST /agent/resume-from-event`
- Rich execution timeline and confirmation handling in `client/src/hooks/chat/useChatStream.ts`
- A large Chat page that can act as both playground and task runner in `client/src/pages/Chat/index.tsx`

The real problem is not missing capability. The real problem is product shape:

- Users still have to understand and toggle `Agent Mode`
- The frontend still thinks in "chat vs agent" instead of "conversation with optional tools"
- The backend exposes multiple task-oriented endpoints with different mental models
- Skills, agent operations, and generation still look like adjacent systems instead of one tool-enabled conversation flow

The target design should follow the mainstream pattern used by current agent platforms:

- One chat entrypoint
- Server-side orchestration
- Streaming event protocol
- Approval interrupts for risky actions
- Tool registry behind a single planner/orchestrator
- Conversation state persisted as messages plus execution events

## Recommended Approach

### Option A: Full Rewrite

Replace the current chat page, hook structure, and agent APIs in one sweep with a new unified stack.

Pros:

- Cleanest end state
- Less temporary compatibility code

Cons:

- Highest delivery risk
- Breaks existing timeline, resume, and patch-confirmation flows
- Hard to verify incrementally

### Option B: Thin Unified Layer on Top of Existing Agent Stack

Keep the current executor, run loop, resume logic, timeline state, and most of `useChatStream`, but add one new unified API and slowly move the UI to consume it.

Pros:

- Lowest risk
- Reuses the strongest parts of the current system
- Supports gradual rollout
- Matches current repo state best

Cons:

- Requires temporary adapter code
- Old endpoints remain for a while

### Option C: Frontend-First Unification

Keep backend APIs mostly unchanged and hide the split by merging frontend hooks and UI first.

Pros:

- Fast visual improvement
- Lower backend churn

Cons:

- Does not solve long-term API fragmentation
- Leaves orchestration semantics split across endpoints

### Recommendation

Choose **Option B**.

This is the best fit for the repository because the backend already contains the hard parts: intent routing, loop execution, resume, summary generation, confirmation pauses, and timeline semantics. The architecture work should unify entrypoints and contracts, not replace the existing engine.

## Target Architecture

### User-Facing Flow

```text
User Message
  -> Unified Chat Input
  -> POST /agent/unified-execute
  -> Intent Router
  -> Orchestrator
     -> Direct generation
     -> Tool loop
     -> Tool loop + generation
  -> SSE event stream
  -> Unified message + timeline renderer
  -> Conversation persistence
```

### Backend Responsibilities

The backend should become the single owner of:

- intent detection
- route selection
- execution policy
- approval interrupts
- tool invocation
- optional model generation after tools
- session state and resumability
- event emission

This means the frontend should stop inferring execution semantics from several independent endpoints. It should consume one response stream and render what the server says happened.

### Frontend Responsibilities

The frontend should become the single owner of:

- composing user input
- lightweight intent preview while typing
- rendering conversation messages
- rendering execution events
- sending approval / rejection / resume actions
- preserving a clean conversation UX

The frontend should not decide whether something is "chat mode" or "agent mode". It should render one conversation that sometimes contains tool activity.

## Canonical Event Model

Define one event schema for streaming and persistence. Start with these event types:

- `intent_detected`
- `intent_preview`
- `route_selected`
- `approval_required`
- `step_started`
- `step_completed`
- `step_failed`
- `tool_result`
- `generation_started`
- `delta`
- `message_completed`
- `task_summary`
- `run_completed`

Design rules:

- Every streamed event must be storable as a session event
- Every persisted event must be renderable in the chat UI
- Event payloads should be additive and typed, not freeform blobs
- Event names should describe what happened, not which endpoint produced them

Map current timeline events into this canonical model first, then gradually retire old names.

## API Design

### New Primary Endpoint

Create:

- `POST /agent/unified-execute`

This endpoint should:

1. Accept the message, session id, attachments, workspace context, and execution preferences.
2. Decide whether the task needs direct generation, tool execution, or a mixed run.
3. Stream SSE events in canonical order.
4. Persist important state transitions to the session timeline.

### Keep Existing Endpoints Temporarily

Do not remove these immediately:

- `/agent/chat-execute`
- `/agent/run-loop`
- `/agent/resume`
- `/agent/resume-from-event`

Instead:

- implement `/agent/unified-execute` as an orchestration facade over them or over the same internal functions
- move frontend traffic gradually
- deprecate old endpoints only after the new flow is stable

This avoids a rewrite and protects current functionality.

## Tool Architecture

The tool layer should converge toward one registry contract:

```text
Orchestrator
  -> Tool Registry
     -> Agent file operations
     -> Agent CUA operations
     -> System operations
     -> Skills adapters
     -> Future MCP adapters
```

Important constraint: `server/skills/executor.py` is not currently a drop-in action handler registry. It should not be injected directly into `UnifiedExecutor` without an adapter layer.

Recommended next shape:

- keep `UnifiedExecutor` as the execution core
- create a `SkillActionAdapter` that exposes selected skills as typed tool actions
- register only explicitly approved skill-backed actions
- keep the action namespace consistent with `ActionType` or a close sibling enum

This preserves auditability and prevents skills from becoming an untyped side channel.

## Conversation and Persistence Model

Persist both of these in the session model:

- human / assistant messages
- execution events

The UI should reconstruct a session from both streams. A completed task may therefore include:

- the original user request
- several execution events
- a final assistant summary

This is more durable than the current implicit split where some execution meaning lives only in transient UI state.

## Human-in-the-Loop Model

Risky actions should pause the run from the server side, not from a frontend mode toggle.

Rules:

- safe read-only actions can auto-run if policy allows
- risky actions emit `approval_required`
- approval resumes the same run or session
- rejection emits a cancellation event and optional recovery guidance

This keeps user trust high and aligns with current mainstream agent design.

## Rollout Plan

### Phase 1: Canonical Contract

Files:

- Create: `server/api/agent_unified.py`
- Modify: `server/api/agent.py`
- Modify: `client/src/services/agentRunApi.ts`
- Modify: `client/src/types` files that hold agent timeline event types

Deliverables:

- canonical SSE event schema
- `POST /agent/unified-execute`
- compatibility mapping from existing run-loop results to canonical events
- no UI redesign yet

Success criteria:

- one endpoint can represent conversation, tool loop, and mixed runs
- no regressions in confirmation or resume semantics

### Phase 2: Frontend Hook Unification

Files:

- Create: `client/src/hooks/chat/useUnifiedChat.ts`
- Modify: `client/src/hooks/chat/useChatStream.ts`
- Modify: `client/src/pages/Chat/index.tsx`
- Modify: `client/src/pages/Chat/components/ChatMessageList.tsx`
- Modify: `client/src/pages/Chat/components/ChatInput.tsx`

Deliverables:

- one `sendMessage` path for all chat submissions
- event-driven rendering
- lightweight intent preview before submit
- `Agent Mode` still exists internally if needed, but is hidden or downgraded behind compatibility logic

Success criteria:

- the user can type naturally without deciding mode
- the same UI can show pure chat and tool-backed runs

### Phase 3: Product-Level Unification

Files:

- Modify: `client/src/pages/Chat/index.tsx`
- Modify: `client/src/store/chatStore.ts`
- Modify: session metadata persistence code

Deliverables:

- remove visible `Agent Mode` toggle
- move advanced controls into a settings drawer
- render one unified conversation panel
- keep execution timeline as contextual detail, not a separate product mode

Success criteria:

- no visible split between playground and agent task runner
- advanced controls remain accessible but no longer define the primary UX

### Phase 4: Tool Registry Convergence

Files:

- Modify: `server/agent/core/executor.py`
- Create: `server/agent/tools/skill_adapter.py`
- Modify: `server/skills/*` as needed for explicit adapters

Deliverables:

- skill-backed tools exposed through a typed adapter layer
- unified tool metadata for audit, approval, and UI display

Success criteria:

- tools and skills can be presented uniformly
- no direct unsafe injection of arbitrary skill execution into the executor

### Phase 5: Deprecation and Cleanup

Files:

- Modify: legacy API docs and tests
- Remove or deprecate frontend-only mode branching paths after migration

Deliverables:

- deprecation notices for old endpoints
- simplified frontend state
- reduced duplicate agent logic

Success criteria:

- one primary conversation path remains
- old flows are retained only where still needed for compatibility

## Non-Goals

This design intentionally does not include:

- replacing SSE with WebSocket for standard chat execution
- rewriting the executor core from scratch
- removing resume support
- exposing every skill as a first-class tool immediately
- redesigning Gateway and heartbeat in the same project phase

These would expand scope without helping the core user experience problem.

## Testing Strategy

### Backend

- add API contract tests for `/agent/unified-execute`
- verify event ordering for conversation-only, tools-only, and mixed runs
- verify approval interrupts and resume behavior
- verify persistence of streamed events into session state

### Frontend

- test unified hook state transitions
- test rendering of canonical event types
- test intent preview behavior and fallback
- test approval and rejection flows

### End-to-End

Required scenarios:

1. `"你好"` -> direct generation only
2. `"帮我读取 README.md"` -> intent preview -> tool execution -> optional generation summary
3. `"修复这个 failing test"` -> loop -> test output -> generation -> patch confirmation -> patch apply -> rerun
4. risky write/delete action -> approval interrupt -> resume or reject

## Final Recommendation

Do not execute the old `优化.txt` plan as written.

Use it as source material, but replace it with this architecture direction:

- unify the conversation entrypoint first
- preserve the current backend loop and timeline strengths
- make the server the orchestrator
- make the frontend an event renderer
- remove visible mode switching only after the unified path is proven

That path is much closer to the current mainstream architecture and much safer for this repository.
