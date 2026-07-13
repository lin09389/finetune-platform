# Workspace Portability and Task Continuity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Export and import a safe, versioned Workspace package that restores resource references and resumable task context without carrying source, large files, secrets or executable authority.

**Architecture:** Add a storage-independent `workspace.portability` domain with strict Pydantic contracts, a bounded archive codec and provider Protocols. Expose a two-phase inspect/commit API under the existing beta Workspace capability. Persist imported continuation contexts separately from runnable Agent Sessions; the frontend provides a polished import/rebind flow and creates a new session when the user continues work.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLite/local files, React 18, TypeScript, Ant Design, Vitest.

---

## Ownership and parallel tracks

### Track A — Portable contract and archive safety

Own only:

- Create `server/workspace/portability/__init__.py`
- Create `server/workspace/portability/schemas.py`
- Create `server/workspace/portability/archive.py`
- Create `server/workspace/portability/service.py`
- Create `server/tests/test_workspace_portability_contract.py`
- Create `server/tests/test_workspace_portability_archive.py`

Do not modify API routers, Agent Session repository, frontend or existing Workspace metadata code.

### Track B — Backend integration and continuation sessions

Own only:

- Create `server/workspace/portability/providers.py`
- Create `server/workspace/portability/repository.py`
- Create `server/api/workspace_portability.py`
- Modify `server/apps/routers.py`
- Modify `server/agent_session/repository.py`
- Modify `server/agent_session/services/session_lifecycle.py` only for the new-session continuation entrypoint
- Create `server/tests/test_workspace_portability_api.py`
- Create `server/tests/test_workspace_continuation.py`

Consume Track A contracts; do not redefine manifest schemas or archive parsing.

### Track C — Workspace Manager experience

Own only:

- Modify `client/src/services/api.ts`
- Modify `client/src/pages/WorkspaceManager.tsx`
- Modify `client/src/pages/WorkspaceManager.module.css`
- Modify `client/src/test/WorkspaceManager.test.tsx`
- Create `client/src/test/WorkspacePortability.test.tsx`

Do not modify Agent runtime components. Preserve the existing design language and shared loading/empty/error states.

### Main thread — integration and acceptance

Own docs/ADR, cross-track fixes, acceptance tests, merge order, full regression and browser visual QA. Main thread does not duplicate track implementation.

## Task 1: Freeze Manifest v1 contracts

**Files:** Track A schema and contract test files.

1. Write failing tests for strict schema parsing, version 1, stable portable ID, typed resource refs, bounded safe task contexts and rejection of extra fields.
2. Run `python -m pytest server/tests/test_workspace_portability_contract.py -q`; expect failures because modules do not exist.
3. Implement `WorkspaceManifestV1`, `PortableTaskContext`, `PortableResourceReference`, `PortableProjectReference`, integrity and producer DTOs with `extra="forbid"` and explicit length/count limits.
4. Add serializers that exclude `session_tool_trust`, approval payloads, raw prompts, terminal output and Diff content by construction.
5. Re-run the test; expect all pass.
6. Commit: `feat(workspace): define portable manifest contract`.

## Task 2: Build bounded archive codec

**Files:** Track A archive/service and archive test files.

1. Write failing tests for deterministic archive round trip, allowlisted entries, SHA-256 validation, ZIP slip, symlink, duplicate entry, compression ratio, entry count and uncompressed-size limits.
2. Implement `SafeWorkspaceArchiveCodec` using `zipfile` without extracting untrusted entries to the filesystem.
3. Build archives in memory or a controlled temp file; write final exports atomically.
4. Parse every entry as bytes, validate limits before JSON decoding, and reject checksum mismatch before schema construction.
5. Add `WorkspaceManifestService.export_package` and `inspect_package` over injected providers.
6. Run both Track A test files; expect all pass.
7. Commit: `feat(workspace): add safe portability archive`.

## Task 3: Project safe task and resource context

**Files:** Track B providers/repository and tests.

1. Write failing provider tests for filtering sessions by authorized Workspace ID and emitting only safe task fields.
2. Add `AgentSessionRepository.list_sessions_for_workspace(workspace_id, owner_id, limit)` without exposing SQL or rows to the manifest domain.
3. Project title, mode, terminal status, repaired execution plan, bounded summary, changed-file metadata, verification outcome and safe artifact/training references.
4. Ensure absolute paths, raw tool arguments/results, full diffs, provider credentials, approvals and tool trust never enter DTOs.
5. Build typed resource references from existing Workspace/model/dataset/training metadata; missing optional services must degrade to unresolved refs, not abort export.
6. Run provider and existing Agent repository tests.
7. Commit: `feat(workspace): project portable task context`.

## Task 4: Persist imported continuation contexts

**Files:** Track B repository and continuation tests.

1. Write failing tests for atomic import creation, idempotent token commit, owner isolation and rollback.
2. Persist import sessions and continuation contexts under the application data directory or SQLite through a repository interface; do not insert them as runnable old Agent Sessions.
3. Store source portable ID, package digest, local Workspace ID, resource resolution state and bounded task DTOs.
4. Add expiry cleanup for inspect tokens and temporary archives.
5. Add a continuation service that creates a new Agent Session with current policy and explicit safe context.
6. Assert new sessions contain no `session_tool_trust`, pending permission, old checkpoint/thread ID or old approval IDs.
7. Commit: `feat(workspace): restore safe task continuations`.

## Task 5: Add two-phase portability API

**Files:** Track B API/router and API tests.

1. Write failing tests for preview/export, inspect/commit, continuation list/create, auth ownership and idempotency.
2. Register `api.workspace_portability` under `/workspace` in the Agent router group.
3. Add `GET /workspaces/{id}/portability/preview` and `POST /workspaces/{id}/exports`.
4. Add multipart `POST /imports/inspect`; stream to a bounded temp file instead of reading unbounded request bodies.
5. Add `POST /imports/{token}/commit` with explicit project/resource binding DTOs.
6. Add continuation list and create-session endpoints.
7. Map unsupported version, tamper, unsafe archive, secret finding, missing binding and expired token to stable machine-readable error codes.
8. Run Track B tests plus `test_workspace.py`, path-policy and Agent Session auth tests.
9. Commit: `feat(workspace): expose portability workflow`.

## Task 6: Build frontend API contract

**Files:** Track C `api.ts` and frontend tests.

1. Add TypeScript discriminated types matching manifest preview, resource status, inspect result, binding request, commit result and continuation context.
2. Add API methods for all Phase 8 endpoints using the existing Axios client; no scattered `fetch`.
3. Write tests for multipart inspect, binary export, stable error decoding and continuation create.
4. Run `npx vitest run src/test/WorkspacePortability.test.tsx` and `npm run typecheck`.
5. Commit: `feat(workspace): add portability client contract`.

## Task 7: Implement polished import/export UX

**Files:** Track C Workspace Manager page, CSS and tests.

1. Add failing UI tests for export preview, import selection, unsafe/unsupported file, resource rebind, missing resources, commit retry and continue-task action.
2. Add “导入 Workspace” to the page header and “导出/迁移检查” to each eligible Workspace action menu.
3. Implement a three-step responsive Drawer: select, inspect/rebind, completion.
4. Reuse shared loading/empty/error states, current spacing/tokens and button hierarchy.
5. Show exclusions before export and integrity/schema facts after inspect.
6. Treat missing resources as repairable grouped states; disable only actions that depend on them.
7. Ensure mobile full-screen behavior, 44px controls, keyboard focus return and non-color-only status labels.
8. Run Workspace tests, beta smoke, typecheck and build.
9. Commit: `feat(workspace): add portable workspace experience`.

## Task 8: Cross-track security and acceptance gate

**Files:** Main thread creates `server/tests/test_workspace_portability_acceptance.py` and updates Phase 8 docs only.

1. Add a golden round trip: export Build/Train/Hybrid contexts, inspect on a clean target, bind a new project path, commit and create a continuation session.
2. Assert no archive entry contains known source snippets, absolute paths, secret fixtures, raw terminal text, full diff text, approvals or tool trust.
3. Add malicious archives: traversal, symlink, duplicate manifest, checksum tamper, archive bomb, unsupported version and cross-user token.
4. Verify continuation session uses a new ID/thread, current autonomy defaults and current model tool-capability preflight.
5. Run focused backend suites, frontend Vitest, typecheck and build.
6. Start the app and visually inspect Workspace Manager at 1280×720 and 390×844 in light and dark themes.
7. Fix integration gaps only in the main thread, then commit: `test(workspace): enforce portability acceptance`.

## Final verification

```powershell
.venv\Scripts\python.exe -m pytest `
  server/tests/test_workspace_portability_contract.py `
  server/tests/test_workspace_portability_archive.py `
  server/tests/test_workspace_portability_api.py `
  server/tests/test_workspace_continuation.py `
  server/tests/test_workspace_portability_acceptance.py `
  server/tests/test_workspace.py `
  server/tests/test_workspace_path_policy.py `
  server/tests/test_agent_session_deepagents_runtime.py -q

Set-Location client
npx vitest run src/test/WorkspaceManager.test.tsx src/test/WorkspacePortability.test.tsx
npm run typecheck
npm run build
```

Exit only when the worktree is clean, archive/security acceptance passes, continuation creates a new policy-safe session, and desktop/mobile visual QA preserves the existing Phase 7.5 design quality.
