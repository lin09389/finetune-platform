# Agent Training Foundation

`server/agent_training/` is an application service intended for future
DeepAgents tool adapters. It deliberately imports training *services*, never
API routers.

## Stable tool contract

- `TrainingProposalRequest` wraps the existing `TrainingConfigInput`, plus
  `use_queue` and `priority`.
- `AgentTrainingService.create_proposal()` / `propose_training()` runs
  read-only model and dataset resolution, `TrainingValidator.validate_config`,
  and `estimate_preflight_required_vram`. It does not create an output
  directory or invoke a training task.
- `TrainingProposal` reports `ready`, `warning`, or `blocked`, with all
  blockers, warnings, suggestions, and the estimated VRAM requirement.
- `ApprovedTrainingAction` must carry `approved=True`.
  `submit_approved_training()` / `submit_training()` otherwise raises
  `AgentTrainingError(code="approval_required")`. Unknown, blocked, stale,
  and already-submitted proposals are also rejected with stable error codes.
- Submission resolves the model and dataset a second time before delegating to
  `services.training.orchestrator.start_training_task`; catalog IDs must name
  one child directory and cannot escape the configured model/dataset roots. It
  also repeats complete preflight in a worker thread before creating a task.
- Future tool adapters must pass the authenticated owner and Agent session to
  proposal creation and submission. The service rejects a proposal submitted
  from a different scope.
- `TrainingSubmission` exposes the resulting `proposal_id`, `task_id`, and
  task `status`.
- `get_run_summary()` / `get_training_run_summary()` maps the authoritative
  `services.training.records.find_training_record` result into the read-only
  `TrainingRunSummary` DTO.

## Proposal lifetime

Proposals live in a bounded store (100 entries by default). When application
settings provide `base_dir`, the store uses SQLite under `data/` so proposals
and submission claims survive restarts and are shared across API workers.
Tests and explicitly injected stores may use in-memory storage instead.

## Build Agent integration

The runtime exposes `propose_training`, `submit_training`, and
`get_training_summary` only to Build sessions whose persisted `task_mode` is
`train` or `hybrid`. Explore, Review, ordinary Build, and project-chat sessions
receive none of these tools.

Proposal and summary calls are read-only. `submit_training` is forced through
the existing DeepAgents HITL interrupt flow and can invoke the application
service only after the matching official approval creates a one-time,
proposal-specific grant. Rejection and repeated calls cannot create a task.

Agent events and Workbench timeline projections restrict training data to safe
identifiers and status fields; output, adapter, and checkpoint paths are never
rendered.

## Workbench golden path

The Workbench is the primary training journey. A `train` task creates a
read-only proposal first, pauses at the existing HITL approval request, submits
one task only after approval, and then shows the authoritative run summary in
the same timeline. The task mode is fixed for the lifetime of the session:
`hybrid` keeps normal Build activity alongside the training journey, while
`build` never receives training tools.

The cross-layer acceptance fixture is
`server/tests/fixtures/agent_training_golden_path.json`. It freezes six
deterministic CPU-only scenarios:

- Train approval: proposal, approved submission, and run summary retain their
  proposal/task identities.
- Train rejection: no task is created.
- Duplicate retry: the original task remains the only submission.
- Refresh recovery: persisted parts reconstruct the same ordered activity IDs.
- Hybrid coexistence: generic Build activity remains visible beside training.
- Build exclusion: no training-tool projection exists.

The intended persisted projection location is
`timeline_item.payload.training_activity`. Every recognized projection contains
`kind`, `source_tool`, a safe `summary`, its `status`, and a stable
`proposal_id` and/or `task_id`. Recognized kinds are `proposal`, `submission`,
and `run_summary`. The payload must never contain output, adapter, checkpoint,
local-path, secret, or raw configuration fields. Unknown, malformed, and failed
projections must stay visible as generic tool activity instead of breaking the
timeline.

### Failure meanings

- A proposal marked `blocked` cannot reach approval or create a task.
- A rejected or missing official approval means submission did not occur.
- A duplicate retry must preserve the original `task_id`; it must not enqueue a
  second training task.
- A stale proposal, worker outage, or missing run is an authoritative failure
  or degraded status, not a locally invented success state.
- A malformed `training_activity` is a compatibility case: use generic tool
  rendering and preserve the rest of the timeline.

### Manual smoke procedure

1. Create a Workbench task with a registered Workspace and `train` mode.
2. Ask for a small catalog-backed training proposal and confirm its model,
   dataset, status, and proposal ID contain no local paths.
3. Reject the approval once; verify no task ID or worker task is created.
4. Request or reuse a ready proposal, approve exactly once, and verify a single
   task ID appears. Repeat submission or refresh the page; the same ID must
   remain and no second task may be created.
5. Wait for or query the run summary, then refresh the Workbench; proposal,
   submission, and summary cards must retain their order and IDs.
6. Repeat in `hybrid` mode while doing a normal Build action, then confirm a
   `build`-mode task exposes no training tools.

The fixture is an acceptance guard owned independently of the projection
implementation. Track A must persist the documented `training_activity`
contract with successful training tool outcomes, and Track B must decode only
recognized shapes and render all other payloads generically. Until those tracks
are integrated, the fixture and scenario tests freeze the required behavior but
do not claim the production timeline has adopted the projection.

## Live-sync recovery contract (Phase 6)

`server/tests/fixtures/agent_training_live_sync.json` freezes the Phase 6
control-plane contract independently of the reconciler implementation. It
covers ordered progress, duplicate replay, API restart cursor recovery,
browser refresh recovery, Worker outage/recovery, missing-job grace,
cross-user rejection, terminal completion, and the artifact handoff.

For a given authenticated owner, session, proposal, and task, exactly one
persisted Agent part is created. Its `part_id` never changes during a replay,
restart, refresh, outage, or terminal update. Training event sequences are
strictly increasing at the persisted cursor: an event at or below the cursor is
acknowledged without creating a new card or moving visible progress backward.

The reconciler may display a safe `degraded` bridge state after bounded Worker
read failures, while retaining the last authoritative progress. Once the
Worker can be read again, the same card returns to the authoritative state.
A job absent during its grace window remains pending; only after that bounded
window may the card enter the safe `missing` state for manual review. A task
link must be rejected when its owner and session binding do not match; no card
may be attached to another user or session.

The only artifact handoff is the label **Available in Models/Training** with
the logical target `models_training`. Output, adapter, checkpoint, local-path,
Worker identifier, raw event payload, prompt, token, and secret values are not
part of this projection.

The cursor is strictly monotonic. Unknown event kinds advance the cursor but
leave the existing training card unchanged, preventing both unsafe rendering
and an infinite replay loop. An event at or below a terminal card’s cursor
cannot regress the terminal projection. A process crash after updating the
part but before committing its cursor is safe to replay: the task still has one
stable card, and the retry commits the same event cursor.

The service owns at most one reconciler and processes a bounded link batch per
wake-up. If the event source cannot be constructed, the Agent-only profile
still starts; training sync is safely degraded instead of preventing coding
workbench use. A task link’s owner, session, proposal, and task identity are
immutable after creation.

`build` sessions create no training links. In `hybrid` sessions, command,
diff, and text parts coexist with the one stable training card. Training
terminal state never changes the overall Agent session state, execution-plan
state, or coding parts; refresh recovery retains that coding timeline.

### Live-sync failure meanings

- `degraded` means the bridge temporarily cannot read the authoritative Worker
  state; it is not a training failure or completion.
- `missing` means the authoritative job remained absent after the configured
  grace window and needs manual review.
- A duplicate/replayed sequence is harmless and must leave both the persisted
  cursor and stable card identity intact.
- An ownership mismatch is a security rejection: the task must never appear in
  the requester’s timeline.

### Local Phase 6 smoke procedure

1. Start a `train` or `hybrid` Agent session and approve one proposal.
2. Confirm that submission creates one training card, then watch queued,
   loading, and running updates without asking the model for a summary.
3. Refresh the Workbench and restart the API while the Worker continues; the
   task and card IDs must stay unchanged and progress must resume from the
   persisted cursor.
4. Temporarily make the Worker record unavailable. Verify the existing card is
   marked degraded, never completed or failed locally, then returns to running
   when the Worker is available.
5. Complete the task and verify the card exposes only **Available in
   Models/Training**, never a filesystem path. Repeat as another user and
   verify the task cannot be linked or displayed.
