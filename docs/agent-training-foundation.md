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
  `services.training.orchestrator.start_training_task`.
- `TrainingSubmission` exposes the resulting `proposal_id`, `task_id`, and
  task `status`.
- `get_run_summary()` / `get_training_run_summary()` maps the authoritative
  `services.training.records.find_training_record` result into the read-only
  `TrainingRunSummary` DTO.

## Proposal lifetime

Proposals live only in a bounded, thread-safe in-process store (100 entries by
default). They are intentionally not written to disk or a database. An
application restart clears them, so an agent must request a fresh proposal
before attempting to submit training.

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
