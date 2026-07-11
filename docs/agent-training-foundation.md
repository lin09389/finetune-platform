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
