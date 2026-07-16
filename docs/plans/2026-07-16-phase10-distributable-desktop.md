# Phase 10 Distributable Desktop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship a recoverable Windows desktop runtime that can prepare and repair a versioned base Python environment without requiring system Python and without risking user data.

**Architecture:** Electron main owns an immutable, manifest-driven runtime store and atomic activation state. A narrow protocol-v1 IPC snapshot projects installer state into the existing Workbench settings UI, while build scripts create and inspect deterministic runtime/package artifacts. Heavy GPU profiles remain optional packs.

**Tech Stack:** Electron 28, Node.js built-in test runner, React 18, TypeScript, Vitest, electron-builder, Python 3.11 runtime profiles managed by `uv`.

---

### Task 1: Freeze the runtime manifest and state contracts

**Files:**
- Create: `electron/managed-runtime-manifest.js`
- Create: `electron/test/managed-runtime-manifest.test.js`
- Reference: `docs/adr/0010-manage-versioned-desktop-python-runtime.md`

**Step 1: Write failing manifest tests**

Cover a valid base manifest and rejection of unknown schema versions, path traversal entrypoints,
unsupported platform/architecture, incompatible Python range, malformed SHA-256, and unknown fields.

**Step 2: Run the focused test and confirm failure**

Run: `node --test electron/test/managed-runtime-manifest.test.js`

Expected: FAIL because the validator module does not exist.

**Step 3: Implement the strict validator**

Export `MANAGED_RUNTIME_MANIFEST_VERSION` and `validateManagedRuntimeManifest(input, target)`. Return a
normalized frozen object; throw typed errors with stable codes. Do not perform I/O in this module.

**Step 4: Run the focused test**

Expected: PASS.

**Step 5: Commit**

Commit: `feat(desktop): define managed runtime manifest contract`

### Task 2: Implement interruption-safe runtime storage

**Files:**
- Create: `electron/managed-runtime-store.js`
- Create: `electron/test/managed-runtime-store.test.js`

**Step 1: Write failing storage tests**

Use temporary directories to cover layout creation, atomic activation records, completed markers, stale
staging detection, preservation of the previous activation, and refusal to resolve paths outside the
managed root.

**Step 2: Run the focused test and confirm failure**

Run: `node --test electron/test/managed-runtime-store.test.js`

**Step 3: Implement the store**

The store owns `staging/`, `versions/<profile>/<version>/`, `active.json`, and quarantine metadata. All
activation writes use temporary files plus rename. Keep filesystem APIs internal.

**Step 4: Run focused and existing runtime-path tests**

Run: `node --test electron/test/managed-runtime-store.test.js electron/test/python-resolver.test.js`

Expected: PASS.

**Step 5: Commit**

Commit: `feat(desktop): add atomic managed runtime store`

### Task 3: Implement prepare, verify, activate, and repair coordination

**Files:**
- Create: `electron/managed-runtime-coordinator.js`
- Create: `electron/test/managed-runtime-coordinator.test.js`
- Modify: `electron/python-resolver.js`
- Modify: `electron/test/python-resolver.test.js`

**Step 1: Write failing state-machine tests**

Cover successful local-pack activation, checksum mismatch, failed health probe, concurrent request
deduplication, interrupted staging cleanup, repair, cancellation-safe shutdown, and previous-runtime
rollback.

**Step 2: Confirm the focused tests fail**

Run: `node --test electron/test/managed-runtime-coordinator.test.js`

**Step 3: Implement using injected artifact and probe adapters**

Keep network/download policy outside the coordinator. Publish immutable snapshots matching the design
state model. Never activate before verification and health probe success.

**Step 4: Make Python resolution consume only healthy active records**

Preserve explicit/project development overrides. In packaged mode, prefer a verified managed runtime
over system Python.

**Step 5: Run desktop tests**

Run: `npm run test:desktop`

Expected: PASS.

**Step 6: Commit**

Commit: `feat(desktop): coordinate managed runtime lifecycle`

### Task 4: Expose narrow runtime-management IPC

**Files:**
- Modify: `electron/runtime-contract.js`
- Modify: `electron/desktop-ipc.js`
- Modify: `electron/preload.js`
- Modify: `electron/main.js`
- Modify: `electron/test/runtime-contract.test.js`
- Modify: `electron/test/renderer-protocol.test.js`
- Modify: `client/src/runtime/desktopRuntime.ts`
- Modify: `client/src/test/desktopRuntime.test.ts`

**Step 1: Add failing protocol tests**

Define protocol-v1 status projection and allowlisted `prepareBaseRuntime`, `repairBaseRuntime`,
`retryRuntimeOperation`, and `revealRuntimeLogs` calls. Reject malformed snapshots and unknown states.

**Step 2: Run targeted Node and Vitest tests and confirm failure**

Run: `node --test electron/test/runtime-contract.test.js electron/test/renderer-protocol.test.js`

Run: `cd client; npx vitest run src/test/desktopRuntime.test.ts`

**Step 3: Implement main/preload/client contracts**

Return serializable snapshots only. Do not expose paths, shell commands, arbitrary URLs, or raw process
output. Wire coordinator shutdown into the existing Electron shutdown path.

**Step 4: Run targeted tests**

Expected: PASS.

**Step 5: Commit**

Commit: `feat(desktop): expose managed runtime lifecycle over IPC`

### Task 5: Add polished preparation and repair UI

**Files:**
- Modify: `client/src/agent/components/DesktopRuntimeSection.tsx`
- Modify: `client/src/agent/components/DesktopRuntimeSection.module.css`
- Modify: `client/src/test/DesktopRuntimeSection.test.tsx`

**Step 1: Add failing UI tests**

Cover ready, preparing progress, verifying, repair-required, recoverable failure, disabled concurrent
actions, retry, repair, and reveal-log actions.

**Step 2: Confirm failure**

Run: `cd client; npx vitest run src/test/DesktopRuntimeSection.test.tsx`

**Step 3: Implement the UI using existing tokens and hierarchy**

Keep the settings drawer compact. Preserve current visual language, keyboard access, focus visibility,
reduced-motion behavior, and concise Chinese copy. Do not add a second settings system.

**Step 4: Verify UI tests, typecheck, and build**

Run: `cd client; npx vitest run src/test/DesktopRuntimeSection.test.tsx src/test/desktopRuntime.test.ts`

Run: `cd client; npm run typecheck`

Run: `cd client; npm run build`

Expected: PASS.

**Step 5: Visually inspect all runtime states**

Capture or inspect ready, progress, repair, and failure states at the existing desktop width. Fix visual
regressions before committing.

**Step 6: Commit**

Commit: `feat(desktop): add runtime preparation and repair experience`

### Task 6: Build deterministic local runtime artifacts

**Files:**
- Create: `scripts/desktop/build-runtime-pack.mjs`
- Create: `scripts/desktop/runtime-pack-policy.mjs`
- Create: `electron/test/runtime-pack-policy.test.js`
- Modify: `package.json`
- Modify: `.gitignore`

**Step 1: Write failing policy tests**

Cover deterministic manifest fields, SHA-256 generation, allowed profile files, forbidden secrets/user
data, unsupported Python versions, and reproducible ordering.

**Step 2: Confirm failure**

Run: `node --test electron/test/runtime-pack-policy.test.js`

**Step 3: Implement a local artifact builder**

Accept an explicit prepared runtime directory and output directory. Do not download dependencies inside
unit tests. Produce the archive plus manifest in a gitignored artifacts directory.

**Step 4: Add package scripts**

Add focused scripts for runtime-pack tests/build without changing existing `start`, `build`, or
`build:electron` behavior.

**Step 5: Run policy and desktop tests**

Run: `node --test electron/test/runtime-pack-policy.test.js`

Run: `npm run test:desktop`

Expected: PASS.

**Step 6: Commit**

Commit: `build(desktop): add versioned runtime pack pipeline`

### Task 7: Enforce desktop packaging and user-data preservation

**Files:**
- Create: `scripts/desktop/inspect-package.mjs`
- Create: `electron/test/package-policy.test.js`
- Modify: `package.json`
- Modify: `docs/desktop-packaging.md`

**Step 1: Write failing package-policy tests**

Assert inclusion of Electron/client/server/runtime metadata and exclusion of databases, secrets, models,
datasets, outputs, workspaces, caches, logs, tests, and developer environments.

**Step 2: Implement package inspection**

The inspector must work on a supplied file list or unpacked directory so CI can verify policy without
signing credentials.

**Step 3: Document unsigned local and signed release paths separately**

Include artifact prerequisites, Windows unpacked smoke, installer smoke, expected data roots, failure
diagnosis, and the currently external signing/update-feed boundary.

**Step 4: Run packaging checks**

Run: `node --test electron/test/package-policy.test.js`

Run: `npm run build`

Run the unsigned Windows unpacked build when local dependencies are available, then inspect it.

**Step 5: Commit**

Commit: `build(desktop): enforce distributable package policy`

### Task 8: Integrate and run Phase 10 acceptance

**Files:**
- Create: `docs/phase10-execution-2026-07-16.md`
- Modify: `AGENTS.md`
- Modify: `README.md`

**Step 1: Review each track against ADR-0010**

Resolve shared-contract differences in the main integration branch. Do not merge overlapping generated
or lockfile changes without inspecting them.

**Step 2: Run automated acceptance**

Run: `npm run test:desktop`

Run targeted runtime Vitest tests, `npm run typecheck`, and `npm run build` from `client`.

Run package-policy tests and the relevant backend profile/desktop-path regression tests.

**Step 3: Execute the Windows clean-machine matrix**

Verify first launch, restart, local-pack preparation, corruption repair, failed update rollback, and
preservation of SQLite, workspaces, models, outputs, and secrets. Record any environment-limited checks
as blocked rather than passing them implicitly.

**Step 4: Update project documentation**

Document the runtime commands, ownership boundaries, current platform support, and Phase 11 handoff.

**Step 5: Commit**

Commit: `docs(desktop): record phase 10 acceptance and operations`
