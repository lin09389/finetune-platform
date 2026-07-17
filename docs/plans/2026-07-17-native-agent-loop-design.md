# Native Agent Loop and Workbench v2 Design

**Status:** Accepted design

**Date:** 2026-07-17

**Primary reference:** `C:\Users\JHJ\Desktop\grok-build`

**Supporting analysis:** `docs/audits/2026-07-17-grok-build-architecture-fact-report.md`

## 1. Objective

Replace the current DeepAgents-based Build runtime with a self-owned Native Agent Loop and replace the current
Agent Workbench protocol/UI with a v2 desktop experience. The migration must preserve the product's local-first
identity, Workspace safety, approval discipline, evidence-backed coding, Electron host, model independence, and
future Training Copilot direction.

This is not a Rust port and not a prompt-copying exercise. Grok Build is used to learn stable responsibility
boundaries, concurrency semantics, recovery behavior, and test strategy. The implementation remains Python,
FastAPI, React, TypeScript, Electron, SQLite, and the existing model/provider infrastructure.

## 2. Confirmed Product Decisions

| Area | Decision |
|---|---|
| Initial runtime scope | Build only |
| Train/Hybrid during migration | Temporarily disabled |
| Runtime selection | Internal configuration; no user-facing runtime selector |
| Protocol | Direct replacement with bidirectional WebSocket v2 |
| Old sessions | Clear only old Agent Session data |
| Message semantics | FIFO follow-up queue + safe-boundary steering |
| Execution security | Introduce provider contract first; trusted sandbox before default cutover |
| Rewind | Restore conversation and Agent-owned files |
| Rewind content | Text files under a size cap; other content requires manual resolution |
| Goal workflow | Enabled for every Build session |
| Goal roles | Planner, Implementer, Verifier, Strategist use the selected Build model |
| Subagents | Not in first Native production release |
| Persistence | Append-only events + periodic snapshots |
| Wire encoding | Versioned JSON envelope; bounded batching/compression |
| Trace collection | Local structural recording; manual selection before training |
| Frontend | Rewrite Workbench information architecture and components |
| Visual direction | Warm editorial desktop tool; preserve terra-cotta identity |

## 3. Target Architecture

```text
Electron / Native Workbench v2
          │
          │ WebSocket JSON Envelope v2
          ▼
Agent WebSocket Gateway
          │ commands / replay / subscriptions
          ▼
Native Session Host (one actor/mailbox per active session)
  ├─ Follow-up FIFO Queue
  ├─ Steering and cancellation controller
  ├─ Goal Workflow coordinator
  ├─ Pending Interaction / Approval
  ├─ Snapshot and recovery coordinator
  └─ Event append boundary
          │
          ▼
Native Sampling Loop
  ├─ Prompt assembler
  ├─ Model provider adapter
  ├─ Structured assistant/tool-call decoder
  ├─ Token/usage accounting
  └─ Bounded retry and compaction trigger
          │ ToolRequest
          ▼
Hook Pipeline → Permission Policy → Approval → Tool Runtime
                                             │
                                             ▼
                              ExecutionEnvironmentProvider
                         local / WSL now; trusted sandbox gate later
                                             │
                                             ▼
                               Files / Process / Git / Validation

Append-only Event Store ──► Snapshot Projector ──► UI / Diagnostics / Eval
           │
           └──────────────► Redacted Trace Collector ──► Manual Curation
```

### 3.1 Ownership rule

Only the Session Host may accept session commands or append authoritative session lifecycle facts. Only the
Sampling Loop decides whether to request a model tool. Only Permission Policy and Execution Environment may
authorize and enforce execution. UI, diagnostics, evaluation, and trace collection are projections/subscribers.

## 4. Runtime Layers

### 4.1 WebSocket Gateway

The gateway authenticates once, resolves the user/session binding, validates envelopes, applies size/rate
limits, and forwards typed commands to the Session Host. It does not own queues or current state.

HTTP remains only for application health, authentication bootstrap, session listing/creation where appropriate,
and large artifact download. Agent prompts, follow-ups, steering, cancellation, approvals, rewind, replay, model
deltas, tool activity, goal state, and completion use WebSocket v2.

### 4.2 Native Session Host

The host is an actor-style serialized command processor. One active session has one mailbox and at most one
running turn. A database lease prevents two API processes from owning the same session concurrently. A host can
be destroyed and rebuilt from the event log plus the latest valid snapshot.

The host owns:

- prompt/follow-up queueing;
- safe-boundary steering;
- turn cancellation and send-now semantics;
- runtime binding and shutdown;
- pending approvals;
- goal workflow transitions;
- snapshot cadence and replay;
- terminal session state and event append ordering.

It does not own model-provider internals, concrete tools, UI state, training jobs, or trace dataset curation.

### 4.3 Native Sampling Loop

The sampling loop is deliberately small:

```text
assemble context
→ request model output
→ persist assistant delta/final response
→ decode zero or more tool requests
→ request policy-authorized tool execution
→ persist structured results
→ repeat, compact, pause, fail, or complete
```

It accepts a cancellation token and yields safe boundaries after model completion and each tool completion. It
never writes directly to WebSocket clients or database tables. It emits typed facts through a Session Host port.

### 4.4 Conversation State

Conversation/context state is rebuilt from events and snapshots. The model context is a projection containing
messages, selected tool results, goal state, compaction records, Workspace context references, and policy-safe
memory. It is not identical to the UI transcript.

Context assembly must be deterministic for a given event cursor and runtime binding. Token accounting is owned
by a separate usage projection so role calls and retries remain visible.

## 5. Commands and Queue Semantics

### 5.1 Command types

- `session.prompt`: start the first or next turn when idle.
- `session.follow_up`: append to the FIFO queue without affecting the current turn.
- `session.steer`: replace the next model-facing instruction at the next safe boundary.
- `session.send_now`: request cancellation of the current turn, then enqueue a high-priority new turn.
- `session.cancel_turn`: cancel the active turn without adding a message.
- `approval.resolve`: approve or reject a pending tool request exactly once.
- `rewind.request`: create a new branch and restore eligible Agent-owned files.
- `session.subscribe`: replay from a cursor and continue live delivery.

Every mutating command carries a client-generated `command_id`; duplicate commands return/replay the existing
result instead of repeating side effects.

### 5.2 Steering boundary

Steering never interrupts a tool in flight. If a tool is running, the command becomes pending and is applied
after the tool result is durably appended. If the model is sampling, cancellation is requested and the steering
instruction is applied to the next sampling call. The event log records requested, deferred, applied, or rejected.

## 6. WebSocket v2 Protocol

### 6.1 Envelope

```json
{
  "version": 2,
  "type": "command|event|ack|error|snapshot|ping|pong",
  "id": "uuid",
  "session_id": "uuid",
  "sequence": 42,
  "turn_id": "uuid-or-null",
  "command_id": "uuid-or-null",
  "causation_id": "uuid-or-null",
  "timestamp": "RFC3339",
  "payload": {}
}
```

Client commands omit server `sequence`. Server events always include the committed sequence. Schema validators
reject unknown command kinds; clients ignore unknown event kinds while still advancing their cursor.

### 6.2 Replay and resync

The client subscribes with `after_sequence`. The server replays committed events and then joins the live stream
without a gap. If the requested cursor is outside retention or the client projection version is incompatible,
the server sends a versioned snapshot followed by later events. WebSocket reconnection never guesses state.

### 6.3 Backpressure

Model token deltas may be batched within a short bounded window. Lifecycle, approvals, tool results, goal
transitions, rewinds, and terminal events are never dropped. Slow clients disconnect with a resumable cursor.
Large diffs, command logs, context files, and artifacts are stored separately and referenced by safe IDs.

## 7. Persistence and Recovery

### 7.1 Authoritative tables

The v2 schema introduces separate repositories for:

- session identity and immutable runtime binding metadata;
- append-only session events keyed by `(session_id, sequence)`;
- idempotent client commands keyed by `(session_id, command_id)`;
- periodic versioned snapshots keyed by `(session_id, sequence)`;
- pending interactions/approvals;
- file mutation snapshots and restore outcomes;
- local redacted trace candidates.

Current mutable status, timeline rows, goal cards, usage summaries, and UI attention items are rebuildable
projections.

### 7.2 Snapshot cadence

Create a snapshot after a bounded event count, after a completed/paused turn, before compaction, and before a
rewind branch. Snapshot writes are temporary-file/transactional and include a checksum. Invalid snapshots are
discarded and replay falls back to the previous valid snapshot or event zero.

### 7.3 Scoped reset

The migration deletes only legacy Agent Session events, parts, DeepAgents checkpoints, approvals tied solely to
those sessions, async subagent state, and derived Agent diagnostics. It preserves Workspace registrations,
project files, chat data outside Agent Session, models, datasets, training jobs, inference state, settings, and
desktop user data.

## 8. Goal Workflow

Every Build session uses one versioned Goal Graph:

```text
Planner → Implementer → Verifier
              ▲            │
              └─ Strategist┘  (only on blocked/repeated failure)
```

- **Planner** produces a structured goal, constraints, ordered/dependent steps, expected files, and verification.
- **Implementer** executes the active step through the same Native Sampling Loop and tools.
- **Verifier** reads existing artifacts and decides pass, revise, blocked, or fail with evidence.
- **Strategist** changes the plan only after explicit failure thresholds or a blocking fact.

The selected Build model serves all roles, but each call has a separate prompt, context budget, role identifier,
and usage record. Role output is schema-validated. Workflow transitions are deterministic application logic;
roles do not create a second hidden tool loop.

The Goal Graph replaces legacy Build `execution_plan`; there is no dual write or compatibility projection.

## 9. Tools, Approval, and Execution Environment

### 9.1 Request path

```text
ToolRequest
→ normalize and schema validate
→ pre-tool hooks
→ permission decision: allow / deny / ask
→ pending approval when required
→ ExecutionEnvironmentProvider
→ structured ToolResult
→ post-tool hooks
→ durable events
```

Approval is a pending interaction owned by Session Host. The renderer sends an idempotent decision command;
only a still-pending request may transition. Reconnect/replay restores the same approval card and decision.

### 9.2 Execution environment contract

The provider contract exposes filesystem operations, process execution, cancellation, network capability,
environment injection, resource limits, and a capability report. Initial local/WSL providers preserve current
development behavior. Native cannot become Build default until a trusted provider fails closed and passes escape,
network, process-tree, timeout, and Workspace sentinel tests.

## 10. File Mutation Ledger and Rewind

Before each Agent write/edit/delete/rename, the runtime records path, base hash, operation, text encoding, bounded
pre-image, and causation. After success it records the new hash and diff reference.

Automatic rewind is allowed only when:

- the path is inside the registered Workspace;
- the mutation was made by this session/branch;
- the file is a regular text file below the configured byte limit;
- its current hash still matches the last Agent-produced hash;
- no later non-rewound Agent mutation depends on it.

Otherwise rewind produces a conflict/manual-resolution event. Binary, oversized, symlinked, externally modified,
or ambiguous rename/delete cases are never silently overwritten.

Rewind creates a new conversation branch, appends restore attempts/results, and preserves the original history.
It does not run `git reset`, change unrelated dirty files, or delete event records.

## 11. Compaction

Compaction is a structured record, not a free-form chat summary. It includes:

- user goal and active constraints;
- Goal Graph version and step states;
- decisions and rejected approaches;
- files read and changed, with mutation references;
- tool failures and what was learned;
- verification evidence and remaining checks;
- queued follow-ups, pending steering, approvals, and blockers;
- context references and explicit omissions.

The record is schema-validated and appended before older context is excluded from the next model window.

## 12. Trace-to-Train Boundary

Local trace collection is enabled for structural facts: role, event kind, tool name, duration, outcome, safe error
class, token/usage totals, verification state, and redacted path categories. It excludes secrets, environment
values, absolute paths, source bodies, full prompts, and raw large tool output by default.

Users manually select candidate sessions/branches. Selection starts a separate redaction and review workflow;
it never starts training automatically. Trace collector failures are isolated subscribers and cannot fail turns.

## 13. Workbench v2 Rewrite

### 13.1 Product structure

```text
┌─────────────────────────────────────────────────────────────────┐
│ Workspace / Branch | Goal | Model | Runtime | Usage | Attention│
├───────────────┬──────────────────────────────┬──────────────────┤
│ Sessions      │ Conversation + Execution     │ Context Dock     │
│ Goals         │ goal / tool / approval /     │ Files / Diff     │
│ Files         │ verification / rewind        │ Terminal         │
│ History       │                              │ Diagnostics      │
├───────────────┴──────────────────────────────┴──────────────────┤
│ Queue / Steering Composer                         Status / Stop │
└─────────────────────────────────────────────────────────────────┘
```

The center is an execution narrative, not a chat-bubble list. Goal transitions, model messages, tool calls,
approvals, verification, file mutations, and rewind are distinct but visually coherent activity types.

### 13.2 Interaction rules

- The composer explicitly switches between follow-up queueing and steering.
- Send-now explains that the active turn will be cancelled.
- Pending approval remains visible across reconnect and cannot be submitted twice.
- Goal Graph is always visible for Build and supports step evidence inspection.
- Diff, terminal, files, context, and diagnostics are dockable panels with stable keyboard shortcuts.
- Rewind previews conversation branch and file effects before confirmation.
- Disabled Train/Hybrid modes explain that they are migrating to Native rather than appearing broken.

### 13.3 Visual system

Retain the existing warm paper surfaces and terra-cotta brand accent, but rebuild typography, density, spacing,
icons, states, and layout as one desktop system. Avoid generic admin cards, neon AI styling, excessive gradients,
and decorative motion. Use purposeful transitions, visible focus, 44px minimum touch targets where relevant,
screen-reader semantics, reduced-motion final states, and light/dark contrast gates.

### 13.4 Frontend architecture

The v2 client is organized by contract and projection:

```text
client/src/native-agent/
  protocol/       JSON envelope, runtime validation, generated types
  transport/      WebSocket lifecycle, replay cursor, backpressure
  store/          normalized event-sourced projection
  commands/       idempotent command builders
  selectors/      goal, queue, attention, timeline, docks
  workbench/      shell and responsive layout
  components/     focused activity and review surfaces
  testing/        protocol fixtures and business journeys
```

It does not import legacy Agent parts, SSE decoders, or DeepAgents-specific tool activity types.

## 14. Failure Semantics

| Failure | Required behavior |
|---|---|
| WebSocket disconnect | Turn continues; client reconnects by cursor |
| API process crash | Lease expires; host rebuilds from snapshot + events |
| Invalid snapshot | Ignore it and replay older snapshot/events |
| Duplicate command | Return existing acknowledgement/result |
| Model timeout | Append classified failure; bounded retry or pause |
| Tool process ignores cancel | Provider kills the process tree; session remains cancelling until confirmed |
| Approval race | First pending decision wins; later decisions receive stable conflict |
| External file edit | Rewind enters conflict; never overwrite |
| Trace subscriber failure | Log/metric only; primary turn continues |
| Sandbox unavailable | Build blocked after default cutover; no silent local fallback |

## 15. Cutover Gates

Native becomes the default Build runtime only when all are true:

- deterministic runtime scenarios pass without DeepAgents;
- real-model Build benchmark meets the agreed Phase 9 baseline and safety thresholds;
- WebSocket reconnect/replay has no missing or duplicated committed events;
- queue, steering, send-now, cancellation, and approval race tests pass;
- crash recovery works from events with deleted/corrupt snapshots;
- text-file rewind preserves unrelated dirty changes and reports conflicts;
- trusted execution provider passes fail-closed security tests;
- Workbench v2 desktop/mobile, keyboard, screen-reader, reduced-motion, and bundle gates pass;
- Train/Hybrid are visibly disabled and cannot be invoked through hidden API/tool routes.

DeepAgents is removed only after a soak period confirms no Build rollback is required. Removal includes Python
dependency, graph checkpoints, compatibility/event adapters, prompts tied to DeepAgents virtual paths, legacy
SSE/parts frontend code, and obsolete tests/documentation.

## 16. Non-goals for the First Native Release

- Train or Hybrid execution;
- subagents, Agent teams, or parallel writers;
- public plugin marketplace;
- PostgreSQL/Redis/team deployment;
- automatic Trace-to-Train dataset creation or training;
- arbitrary binary/large-file rewind;
- macOS parity;
- compatibility with legacy Agent sessions or protocol clients.
