# Coding Agent Capability Audit — 2026-07-11

## Scope and method

This is an additive audit. It creates only the five owned audit files and does
not modify the Agent Runtime, repository, services, manifests, protocol,
timeline, Workbench, existing tests, or Phase 6 work. The tests are CPU-only
and use an injected repository, temporary directories, and deterministic
fixtures; they do not invoke a model, CUDA, network, package installer, or a
destructive Git operation.

The frozen scenarios are in
`server/tests/fixtures/coding_agent_golden_path.json`: Python bug fix, React
change, cross-stack feature, multi-file refactor, failed-verification repair,
and refresh/resume. They specify read/write bounds, commands, expected files,
forbidden paths, Build availability, and Build/Hybrid coexistence invariants.

## Evidence and classification

| Capability | Status | Evidence | Boundary of the claim |
| --- | --- | --- | --- |
| Build coding-tool contract and trajectory policy | proven | `test_build_contract_has_coding_tools_and_guarded_trajectory_policy` passes; `agent_session/agents/build.agent.yaml` and `agent_session/trajectory.py` expose read/edit/write/execute plus the required guards. | Proves configured availability and policy, not a live model choosing the tools correctly. |
| Workspace path isolation | proven | `test_workspace_policy_accepts_only_explicitly_allowed_project_roots` passes; `workspace/path_policy.py::validate_agent_project_path` resolves an allowed temporary project and rejects an adjacent directory. Existing `test_workspace_path_policy.py` also passes. | This is path-policy evidence; it is not a hostile-process sandbox escape test. |
| Read-before-write and failed-verification reread | proven | `test_trajectory_requires_reread_after_failed_verification_and_recognizes_real_checks` passes; `agent_session/trajectory.py::score_trajectory` records `write_without_reread_after_failure`. Existing `test_agent_trajectory.py` validates the middleware gate. | It proves the guard when tool events are observed, not model-level recovery quality. |
| Verification-command recognition | proven | The same new test accepts pytest, Vitest, and typecheck while rejecting `echo`; `agent_session/trajectory.py::is_verification_command` implements the classifier. | It classifies commands only; it does not prove that a real command is run or that its output is accurately parsed. |
| Stable session identity | proven | `test_session_identity_and_changed_file_projection_are_stable` passes for repository reload and `deepagents_thread_id`; `agent_session/deepagents_runtime.py::deepagents_thread_id` is deterministic. | It proves identity persistence, not complete resume after process/browser failure. |
| Changed-file / artifact projection | partially proven | The same test exercises `state.record_diff` and `artifact_extractor.AgentArtifactExtractor`; `workspace_view.py` passes extracted changed files to its response. | The audit found no production producer that turns every edit into a diff artifact, so an end-to-end edit-to-diff guarantee is not established. |
| Project understanding and multi-file editing | partially proven | The fixture requires target and related reads, and existing trajectory tests enforce individual file/context gates. | There is no scenario runner that proves the runtime reads all callers, types, and tests before a coordinated multi-file change; there is no atomic refactor contract. |
| Terminal command and verification presentation | partially proven | `artifact_extractor.py` can project command and test artifacts; `AgentRunTimeline.tsx` renders tool/command information; the new fixture maintains command and verification ordering. | The current audit has no real runtime command event flowing through to the Workbench, so terminal fidelity and exit-code UX are not end-to-end proven. |
| Diff review | missing | `AgentRunTimeline.tsx` has a diff rendering path and the extractor can consume diff artifacts. | No runtime contract requires a post-edit diff, produces it for every edit, or gates completion on a review; no end-to-end test proves it. |
| Workbench visibility in Build and Hybrid | partially proven | `CodingAgentGoldenPath.test.tsx` passes for ordered coding activity in Build and alongside a training item in Hybrid. `workbenchSelectors.ts::selectTimeline` merges workspace timeline and session parts, and `AgentWorkbenchPage.tsx` renders it through `AgentRunTimeline`. | The new test intentionally exercises deterministic projections rather than modifying/duplicating Workbench tests; it does not render a real backend stream in both modes. |
| Pending approval continuity | partially proven | The frontend scenario preserves `coding-permission-001`; `AgentWorkbenchPage.tsx` passes `workspace.pending_permission` into the timeline, while `deepagents_events.py` persists permission parts. | A refresh followed by approval and resumed execution is not covered as one integrated flow. |
| Refresh / resume | partially proven | The frontend scenario preserves session ID, changed files, terminal/diff activities, and approval ID. `sessionPersistence.ts` retains the recent session index and active session ID. | It does not persist the full workspace payload locally; successful server rehydration after a browser refresh/process restart remains unproven. |
| Build/Hybrid coding and training coexistence | partially proven | `CodingAgentGoldenPath.test.tsx` verifies deterministic coexistence. `training_tools.py::training_tools_enabled_for_session` restricts actual training tools to `agent_id == build` with `task_mode` train or hybrid. | No integrated session verifies coding tools, training activity, approval, refresh, and final summary together. |
| End-to-end normal project development | missing | The six scenarios are frozen as a repeatable acceptance contract. | There is no deterministic runtime harness that drives reads, multi-file edits, commands, failures, rereads, diffs, approval, and resume through the existing production stack without a live model. |

## Product gaps vs. test-environment limitations

### Product gaps

1. There is no guaranteed edit-to-diff-to-review pipeline. A changed-file
   projection can be consumed, but the audit could not prove a runtime source
   for every edit or a required review before completion.
2. Normal coding work has no end-to-end golden-path harness. Current checks
   prove individual guards and UI/projection contracts, not the complete
   trajectory across backend and Workbench.
3. Resume retains an ID and recent-session index, but no contract proves full
   restoration of workspace state, pending approval, terminal output, and diff
   after refresh.
4. Multi-file understanding/refactoring has per-file controls but no
   coherent-change or completion contract across all affected files.

### Test-environment limitations

- The audit deliberately did not use a live model, CUDA, the network, package
  installation, or destructive Git. It therefore makes no claim about model
  reasoning quality, provider reliability, GPU behavior, or remote command
  execution.
- Vitest runs deterministic data projections rather than a real browser reload
  connected to a running backend. Browser storage and server rehydration are
  separately evidenced only by their local contracts.

## Training-oriented regression check

This audit changed no production code, so it introduced no regression. There
is, however, an existing configuration-pressure risk: the Build manifest lists
`propose_training`, `submit_training`, and `get_training_summary`, while
`training_tools_enabled_for_session` later restricts actual construction to
Train/Hybrid modes. The runtime gate prevents demonstrated Build-mode access,
but manifest-level exposure can still steer a normal coding session toward
training behavior. The existing training golden-path fixture separately
expects an empty training projection for Build. Treat this as a P1 contract
alignment risk, not a proven behavioral regression.

## Next Coding-first implementation priorities

1. **P0 — Build an offline end-to-end golden-path runner.** Use a deterministic
   fake tool-calling model and temporary workspace to execute the six frozen
   scenarios through session, trajectory, event, workspace, and Workbench
   projections. Assert reads, bounded writes, command result, reread/repair,
   final verification, and no forbidden path writes.
2. **P0 — Add a first-class edit/diff/review contract.** Emit changed files and
   a diff artifact for every successful edit, display the result, and make the
   final summary state whether review occurred. This closes the highest-risk
   gap between actual code changes and user-visible evidence.
3. **P1 — Make refresh/resume a server-backed continuity contract.** Reload by
   stable session ID and assert restored parts, changed files, terminal result,
   diff, and pending approval before any resumed action.
4. **P1 — Separate Coding and training capabilities at the manifest/runtime
   boundary.** Keep Hybrid coexistence explicit while preventing Build-only
   tool exposure from drifting toward training.
5. **P2 — Strengthen multi-file completion semantics.** Record the required
   context set and affected files, then require focused verification and a
   reviewed diff that covers that set.

## Verification record

```text
C:\Users\JHJ\Desktop\finetune-platform\.venv\Scripts\python.exe -m pytest \
  server/tests/test_coding_agent_golden_path.py \
  server/tests/test_agent_trajectory.py \
  server/tests/test_workspace_path_policy.py -q
34 passed, 1 warning

cd client
npx vitest run src/test/CodingAgentGoldenPath.test.tsx
1 file passed, 3 tests passed

npm run typecheck
passed
```

The final ownership and whitespace checks are run immediately before the
report commit.
