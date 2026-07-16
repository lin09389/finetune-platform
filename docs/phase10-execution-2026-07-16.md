# Phase 10 Execution Record — 2026-07-16

## Outcome

Phase 10 establishes the Windows x64 distributable-runtime foundation defined by ADR-0010. Electron can
discover a trusted local base runtime pack, validate one strict manifest, verify archive and unpacked
SHA-256 digests, extract into isolated staging, probe exact Python 3.11, atomically activate the healthy
version, preserve the previous activation on failure, and select the healthy managed Python on the next
application start.

The Workbench settings drawer exposes a protocol-v1 status projection and fixed prepare, repair, retry,
and reveal-log operations. Renderer input cannot choose manifests, archives, extraction paths, or shell
commands. Mutable user data remains below `userData/runtime`; managed runtime versions live in the
sibling `managed-runtimes` root.

## Integrated commits

- `c2a17f7e` — strict managed runtime manifest
- `36e2d9a0` — atomic runtime store
- `48a2354e` — prepare/verify/activate/repair coordinator
- `d8030262` — protocol-v1 runtime-management IPC
- `aed6a18d` — Workbench preparation and repair UI
- `e56d584d` — deterministic runtime pack pipeline
- `6da1014d` — desktop package and user-data policy
- Main-thread integration commit follows this record and aligns all three track contracts.

## Main-thread integration findings closed

- Unified `arch`, Python range, archive filename/size/digest, unpacked digest, and entrypoint fields.
- Unified coordinator snapshots with the renderer's `source` and bounded progress contract.
- Added no-argument trusted manifest actions expected by IPC.
- Added the local manifest/archive adapter and wired the coordinator into Electron main.
- Moved managed runtimes out of mutable product data and protected packaged resources.
- Fixed incorrect USTAR header offsets that previously extracted files below a false `0000000/` root.
- Split the low-frequency settings drawer/runtime card from the main Workbench bundle instead of raising
  the bundle budget.
- Fixed renderer `unknown` narrowing and status-action regressions that Track B could not test without
  its missing `node_modules`.

## Verification

- `npm run test:desktop`: 46 passed. Includes a synthetic end-to-end pack build, safe tar inspection,
  extraction, digest verification, activation, and active-runtime assertion.
- Frontend targeted regression: 78 passed across desktop runtime, settings drawer, and Workbench runtime.
- `npm run typecheck`: passed.
- `npm run build`: passed; Agent Workbench route 41.8/45 KiB gzip.
- Package/runtime policy tests are also included by the desktop suite.

The frontend Workbench runtime test logs a known jsdom connection refusal for the absent local API while
still passing its assertions; no backend service was started for this UI test.

## Release acceptance still open

The following checks are intentionally not marked complete:

- Build a real Python 3.11 base runtime with the frozen dependency profile.
- Run the same prepare/probe/activate path against that real runtime, not only a synthetic fixture.
- Produce and inspect an unsigned Windows unpacked application and NSIS installer.
- Execute first-launch, restart, corrupt-pack repair, failed-upgrade rollback, and user-data preservation
  on a clean Windows account or virtual machine.
- Configure production code signing and an update feed; these remain release-operations work.

Phase 10 implementation is integrated when the main-thread commit lands. Phase 10 release readiness
remains conditional on the real-artifact and clean-machine matrix above.
