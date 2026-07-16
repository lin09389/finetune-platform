# Desktop packaging and runtime artifacts

Phase 10 ships a small Windows x64 Electron application and a separately prepared, versioned Python
runtime pack. The base application never downloads Python packages, CUDA, PyTorch, models, datasets, or
user data while it is being built. `base` contains only the control-plane and Agent dependencies;
`training-gpu` remains a separately prepared optional profile.

## Build a local runtime pack

Prepare the runtime directory outside this repository with Python `3.11.x` and all required base
dependencies already installed. The builder only reads that directory. It does not invoke `uv`, `pip`,
or the network.

```powershell
npm run build:runtime-pack -- `
  --runtime-dir C:\prepared\python-3.11-base `
  --output-dir artifacts\runtime-packs `
  --profile base `
  --version 2026.07.16 `
  --platform win32 `
  --architecture x64 `
  --python-version 3.11.9
```

The output directory receives a deterministic `.tar.gz` archive and adjacent JSON manifest. The manifest
contains the schema version, target platform/architecture, `>=3.11,<3.12` compatibility, profile,
entrypoint, archive digest, unpacked digest, and completed-marker name. `artifacts/runtime-packs/` is
ignored by Git deliberately: packs are release artifacts, never source inputs.

The builder rejects unprepared or unsafe inputs, including symlinks, databases, secrets, mutable user
data, models, datasets, outputs, workspaces, caches, logs, developer environments, and GPU/training
dependencies in a `base` pack. Run its policy test without creating a runtime archive:

```powershell
npm run test:runtime-pack
```

## Unsigned local Windows validation

Unsigned builds are the supported local-development acceptance path. They are not a release channel.

```powershell
npm run build
npm run build:electron:unpacked
```

Before handing the unpacked build to a tester, inspect the package file list. The inspector accepts a
JSON array so CI can obtain the list from its archive/unpacked-file collection step without signing:

```powershell
npm run inspect:package -- --file-list release\package-files.json
npm run test:package-policy
```

The policy requires Electron main/preload code, the built client, the server entrypoint, and package
metadata. It rejects databases, secrets, models, datasets, outputs, workspaces, caches, logs, tests,
and development environments. `server/datasets/__init__.py` is the one permitted empty package marker;
it is not user dataset content.

Smoke the unpacked executable on a clean Windows test account with a prepared local base pack available.
Verify first launch, close/restart, intentional corrupt-pack repair, failed-pack rollback, and that no
write occurs below the installation directory. Then build the NSIS installer with `npm run build:electron`
and repeat the same smoke test from the installed application.

Mutable state belongs below Electron's `userData/runtime` root (normally under the Windows per-user app
data location). SQLite, secrets, models, datasets, outputs, logs, workspaces, and caches stay there.
Managed runtime profiles are versioned outside the package and outside that mutable runtime-data root,
under the sibling managed-runtime location selected by Electron main. Application updates must preserve
both locations.

## Signed releases and update service

Code signing and an update feed are intentionally separate release-operations work. A signed release
requires a Windows code-signing certificate, protected CI credentials, verified installer metadata, and
an update-feed publication/rollback process. Do not treat a passing unsigned smoke test as a signed
release, and do not add signing credentials, certificate files, runtime packs, or user data to this
repository. The current package inspection and unsigned smoke path remain useful prerequisites for that
future release workflow.

## Failure diagnosis

- `RUNTIME_PACK_PYTHON_VERSION`: prepare an exact Python `3.11.x` runtime.
- `RUNTIME_PACK_FORBIDDEN_FILE`: remove user/developer data or GPU dependencies from a base pack.
- `RUNTIME_PACK_ENTRYPOINT_MISSING`: provide `python.exe` for a Windows pack.
- `PACKAGE_POLICY_FORBIDDEN_FILE`: correct the builder include/filter rule; never waive mutable data
  into the application package.
- `PACKAGE_POLICY_REQUIRED_FILE_MISSING`: rebuild the client/server desktop input before packaging.
