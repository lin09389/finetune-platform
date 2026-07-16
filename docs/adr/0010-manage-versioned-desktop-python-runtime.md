# ADR-0010: Manage a versioned desktop Python runtime

## Status

Accepted

## Context

Phase 9 established Electron as the formal desktop boundary. The application already supervises local
services, isolates mutable data under Electron `userData/runtime`, and resolves Python 3.11 from an
explicit path, a project virtual environment, a managed-runtime slot, or the system. It does not yet
provision or repair that managed-runtime slot, so a non-technical Windows user must still install the
exact Python and dependencies manually.

The product is local-first and single-machine-first. It must preserve SQLite, local GPU access, user
workspaces, models, outputs, and secrets across application updates. At the same time, shipping every
CUDA, training, inference, and experimental dependency in the base installer would make releases very
large, slow, and fragile for an independent developer to operate.

## Decision

The desktop application will manage versioned, immutable Python runtime profiles outside packaged
resources and outside user data:

- `base` is the required control-plane and Agent profile.
- `training-gpu` and other heavyweight profiles are optional installable packs.
- Every pack has a versioned manifest containing platform, architecture, Python compatibility,
  profile name, archive digest, unpacked digest/version marker, and entrypoint.
- Installation uses download/copy to a staging directory, checksum verification, extraction, a
  health probe, and an atomic activation pointer. Failed staging never replaces the active runtime.
- The previous healthy runtime remains available until the new runtime passes its health probe.
- User data remains under `userData/runtime`; runtime packs live under a sibling managed runtime root.
- The renderer receives a narrow, versioned IPC projection. It never receives arbitrary filesystem
  or process execution primitives.
- Application updates and runtime-profile updates are distinct operations. Automatic application
  update integration may consume the same status model, but Phase 10 does not require a public update
  service or code signing credentials.

## Consequences

### Positive

- A clean Windows machine can run the base product without a separately installed Python.
- Corrupt or interrupted runtime installs can be diagnosed and repaired safely.
- Optional GPU packs keep the base installer and release workload manageable.
- Runtime rollback does not overwrite SQLite databases, models, outputs, workspaces, or secrets.
- The manifest and activation model can later support macOS without changing renderer contracts.

### Negative

- Release engineering must build and publish runtime packs in addition to the Electron installer.
- Disk usage temporarily includes both the active and previous runtime during an upgrade.
- Native Python dependencies must be validated per OS and architecture.
- The first launch may require a runtime preparation step.

### Neutral

- System Python remains a development fallback but is not the packaged-product contract.
- Training and inference profiles remain independently versioned from the application.

## Alternatives Considered

### Bundle every Python and GPU dependency inside the Electron installer

Rejected for Phase 10 because it creates a very large installer, couples all optional capabilities to
every release, and increases signing, download, and repair cost.

### Continue requiring system Python 3.11

Rejected because it prevents the product from behaving like a normal desktop application and creates
uncontrolled dependency drift.

### Install dependencies into one mutable virtual environment

Rejected because partial upgrades are difficult to recover and rollback cannot be made atomic.

## References

- `docs/phase9-execution-2026-07-15.md`
- `docs/adr/0004-split-runtime-dependency-profiles-and-images.md`
- `docs/plans/2026-07-16-phase10-distributable-desktop-design.md`
