# Phase 10 Distributable Desktop Design

## Product outcome

Phase 10 turns the Phase 9 Electron runtime from a developer-oriented desktop shell into a recoverable
Windows desktop product. A user installs the application, opens it, and sees either a ready workbench or
a clear runtime preparation/repair flow. The product must not require the user to understand Python,
virtual environments, FastAPI, or package profiles.

This phase preserves the established product story: one Codex-like task and conversation workbench for
coding projects and model-training assistance, optimized for one person and one machine. It does not
replace SQLite, local GPU execution, the Agent Session runtime, or the training/inference process split.

## Requirements and non-functional constraints

- Windows x64 is the release acceptance platform; macOS compatibility is architectural only.
- Python must remain `>=3.11,<3.12` for this phase.
- The required base runtime must be installable and repairable without system Python.
- Runtime installation must be interruption-safe and must verify content before activation.
- Updates must never write into packaged resources or overwrite user databases, models, datasets,
  outputs, logs, workspaces, caches, or secrets.
- Runtime state must be observable from the existing Workbench settings surface.
- Renderer privileges remain narrow: status, prepare, repair, reveal logs, and retry are explicit IPC
  operations; arbitrary path or command execution is forbidden.
- A failed runtime update must leave either the previous healthy runtime active or a deterministic
  repair state. Target recovery time is under five minutes after a valid local runtime pack is available.
- The base installer and base runtime must not include CUDA/PyTorch training stacks by default.
- Tests must not require paid model calls, signing credentials, or a public release server.

## Architecture

The managed runtime is a small Electron-main-domain subsystem with four boundaries:

1. A pure manifest validator accepts only the supported schema, platform, architecture, Python range,
   profile, digests, and entrypoint.
2. A runtime store owns staging, version directories, an activation record, health metadata, and safe
   cleanup. It exposes no renderer-facing filesystem primitives.
3. A coordinator runs the prepare/verify/activate/repair state machine and publishes a serializable
   snapshot through the existing desktop runtime contract.
4. The renderer projects the snapshot into the existing desktop runtime settings section and presents
   explicit recovery actions.

Runtime packs are immutable after activation. The activation record is the only mutable pointer and is
written atomically. The active Python path is passed to the existing process supervisor; mutable product
data continues to use the Phase 9 runtime paths.

## Runtime state model

The public state is versioned and intentionally smaller than internal installer state:

- `unavailable`: no compatible active runtime and no operation running.
- `checking`: reading and validating installed state.
- `preparing`: staging or extracting a pack, with bounded progress fields.
- `verifying`: checking digest, entrypoint, and health probe.
- `ready`: a compatible active runtime is healthy.
- `repair_required`: installed data is corrupt or incomplete and a repair action is available.
- `failed`: the latest operation failed; the prior healthy activation may still be usable.

Snapshots include protocol version, operation id, profile, runtime version, Python version, source,
progress, recoverability, last error code, and timestamps. Error messages are mapped to stable error
codes before reaching the renderer; raw command output is written to desktop logs.

## Failure handling

- Invalid manifests fail before filesystem mutation.
- Digest mismatch deletes/quarantines staging and never changes activation.
- Interrupted extraction is detected by the absence of a completed marker.
- Failed health probes retain the previous activation.
- Concurrent prepare/repair requests are deduplicated by one operation lock and operation id.
- Application shutdown cancels cancellable work and leaves staging detectable for the next cleanup.
- Disk-space, permission, antivirus-lock, and archive-corruption failures become actionable status codes.
- Tests simulate interruption, checksum mismatch, stale staging, activation failure, and rollback.

## Release and packaging boundary

Phase 10 produces deterministic local runtime artifacts and a Windows unpacked/installer smoke path. It
does not require publishing artifacts to a public CDN. The artifact source is injectable so tests and
local releases can use a filesystem pack while future releases can use HTTPS with the same manifest.

The package allowlist continues to exclude mutable data. A packaging assertion inspects the built file
list and fails if databases, secrets, workspaces, models, outputs, or caches are included. Code signing
and a production update feed remain release-operations follow-ups, not hidden prerequisites for local
acceptance.

## User experience

The existing Workbench settings drawer remains the primary surface. It shows one compact status card:

- ready: runtime version and healthy services;
- preparing/verifying: stage and progress without blocking the rest of the shell;
- repair required/failed: concise cause, recommended action, retry/repair, and reveal-log affordance.

Visual work must reuse the existing design tokens, spacing, card hierarchy, and motion behavior. Phase 10
does not introduce a separate rough bootstrap application unless Electron cannot render the existing
client bundle before services start.

## Parallel ownership

- Track A owns manifest validation, runtime store/coordinator, and Node tests.
- Track B owns the versioned IPC projection, preload/client types, settings UI, and Vitest coverage.
- Track C owns artifact/build scripts, `package.json`/builder configuration, packaging assertions, and
  release-runbook documentation.
- The main thread owns this design, ADR, shared protocol decisions, integration, cross-track review, and
  final acceptance.

Track B builds against the protocol in this document and may use a fake Electron bridge. Track C consumes
Track A's artifact contract but does not edit Track A modules. Only Track C edits `package.json`.

## Acceptance criteria

- A synthetic valid base pack installs, verifies, activates, and is selected before system Python.
- Checksum mismatch, interrupted staging, and failed probe do not replace a healthy activation.
- Runtime status and repair actions are exposed through versioned, allowlisted IPC.
- The Workbench settings UI represents ready, progress, repair-required, failure, and retry states.
- Node desktop tests, targeted Vitest tests, frontend typecheck/build, and packaging-policy tests pass.
- A Windows clean-machine runbook verifies first launch, restart, repair, upgrade, rollback, and user-data
  preservation without paid model calls.

## Explicit non-goals

- PostgreSQL/Redis or team collaboration.
- Independent per-task Agent worktrees; that remains Phase 11.
- macOS signing/notarization and universal binaries.
- A hosted update service or paid code-signing setup.
- Bundling all CUDA/training/inference profiles in the base installer.
- Replacing DeepAgents or redesigning the Coding Agent loop.
