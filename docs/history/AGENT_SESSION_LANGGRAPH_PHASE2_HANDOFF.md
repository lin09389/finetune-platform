# Agent Session LangGraph Phase 2 Handoff

## 1. Summary

This phase moves `agent_session` from a process-local LangGraph prototype to a SQLite-backed async runtime that can resume after rebuilding the service instance.

The current state is:

- non-streaming `agent_session` now prefers LangGraph when `AGENT_SESSION_LANGGRAPH_ENABLED=true`
- checkpointing uses SQLite instead of `InMemorySaver`
- action and permission resume paths no longer use `asyncio.run()` inside sync service methods
- API routes for `agent-permissions` and `agent-actions` now await async service methods directly
- streaming model output still stays on the legacy `AgentSessionProcessor`

## 2. What Changed

### 2.1 New async runner

Added:

- `server/agent_session/langgraph/runner.py`

`AgentSessionGraphRunner` is now the single LangGraph entrypoint for:

- lazy graph initialization
- SQLite checkpointer setup
- `run_prompt(initial_state)`
- `resume(session_id, decision)`
- `execute_action_and_resume(part_id, decision)`

It uses thread ids in this format:

- `agent_session:{session_id}`

This avoids mixing `agent_session` checkpoints with workflow runtime checkpoints.

### 2.2 Graph builder no longer owns checkpoint lifecycle

Updated:

- `server/agent_session/langgraph/graph_builder.py`

The graph builder now accepts an injected checkpointer instead of using a module-level `InMemorySaver`.

This is important because checkpoint lifecycle is now managed by the async runner rather than hidden inside graph construction.

### 2.3 Service async boundary is fixed

Updated:

- `server/agent_session/service.py`

Key changes:

- `prompt()` uses the async runner for the LangGraph path
- new async methods:
  - `approve_permission_async()`
  - `approve_action_async()`
  - `execute_action_async()`
- legacy sync methods are still kept for the old processor path
- LangGraph fallback metadata is recorded in session metadata
- resume decisions are stored in metadata for easier debugging

Current diagnostic metadata worth checking:

- `runtime`
- `checkpoint`
- `fallback_reason`
- `last_graph_error`
- `last_resume_decision`

### 2.4 API routes no longer wrap LangGraph resume in `run_sync()`

Updated:

- `server/api/agent_sessions.py`

For LangGraph-backed sessions:

- permission approve/reject now await async service methods
- action approve/reject/execute now await async service methods

This removes the old threadpool boundary that was conflicting with async checkpoint lifecycle.

## 3. Current Behavior

### 3.1 What now runs on LangGraph

When `AGENT_SESSION_LANGGRAPH_ENABLED=true` and no streaming model call is available:

- `POST /agent-sessions/{id}/prompt`
- permission resume
- action approve/reject/execute follow-up flow

all go through the LangGraph runtime.

### 3.2 What still stays on legacy processor

These are intentionally not migrated in this phase:

- `stream_model_call`
- `model_stream_started`
- `part_delta`
- `model_stream_completed`

If a streaming provider path is available, `prompt()` continues to use the legacy `AgentSessionProcessor`.

### 3.3 Action semantics remain unchanged

The user-facing approval model is still:

- `approve` marks `diff/command` part as `approved`
- `execute` performs the patch or command
- after execution, LangGraph resumes and continues the loop

`approve` does not auto-execute.

## 4. Tests Added or Extended

Added:

- `server/tests/test_agent_session_langgraph_prompt.py`
- `server/tests/test_agent_session_langgraph_actions.py`
- `server/tests/test_agent_session_langgraph_permissions.py`
- `server/tests/test_agent_session_langgraph_stream_fallback.py`
- `server/tests/test_agent_session_langgraph_fallback.py`
- `server/tests/test_agent_session_langgraph_api_async.py`

These cover:

- non-streaming prompt loop
- service rebuild + checkpoint resume
- permission resume after service rebuild
- action approve/execute after service rebuild
- streaming fallback stays on legacy processor
- API route uses async LangGraph service path instead of sync wrapper

## 5. Known Boundaries

### 5.1 Streaming is not migrated

This is the biggest intentional boundary left in place.

Do not assume that `agent_session` is fully LangGraph-native yet. Only the non-streaming execution path is.

### 5.2 Checkpoint lifecycle is per runner instance

The runner owns the async SQLite saver lifecycle.

Do not move checkpoint initialization back into:

- sync service methods
- threadpool wrappers
- module-level global async saver reuse across unrelated event loops

That was the main source of earlier resume instability.

### 5.3 Fallback is still important

If LangGraph init or execution fails, service code still falls back to the legacy processor path.

This is expected in the current phase and should not be removed yet.

## 6. Suggested Next Step

The next sensible phase is not more orchestration features. It is to stabilize the migration boundary:

- review and split commits by backend migration topic
- keep frontend changes separate from LangGraph backend changes
- then decide whether Phase 3 should target streaming migration or broader `ChatNew` end-to-end smoke coverage
