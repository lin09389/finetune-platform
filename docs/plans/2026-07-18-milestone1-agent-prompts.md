# Milestone 1 External Agent Prompt Pack

These prompts are model-agnostic. Replace `<WORKTREE_PATH>`, `<BASE_BRANCH>`, and `<BASE_COMMIT>` with the actual isolated worktree, integration branch, and exact reviewed HEAD before sending each task.

## Shared preamble

Prepend this block to every implementation prompt:

```text
You are implementing one bounded task in Finetune Platform.

Repository/worktree: <WORKTREE_PATH>
Base branch: <BASE_BRANCH>
Base commit: <BASE_COMMIT>

Read and obey the repository AGENTS.md before acting. Then read completely:
- docs/adr/0012-platform-owned-orchestration-around-deepagents.md
- docs/plans/2026-07-18-controlled-tool-platform-design.md
- docs/plans/2026-07-18-milestone1-selective-tool-foundation.md

Use codex/tool-platform at commit 87cf803 only as a read-only source reference. Do not merge it. Never cherry-pick 8888bd3 or 96f0b93.

Strict boundaries:
- Modify only the files explicitly assigned below.
- Preserve unrelated changes.
- Use apply_patch for edits.
- Do not use git add .
- Do not install dependencies, access the network, or invoke a real model/CUDA.
- Do not change DeepAgents runtime behavior, approval semantics, Train/Hybrid behavior, frontend, Electron, lifespan, repository, configuration, or event transport.
- Follow TDD: add/run failing tests, implement the minimum, rerun focused tests.
- Commit only your owned files with the requested commit message.
- Do not merge another branch and do not merge your branch into the integration branch.

Final response must include:
1. concise implementation summary;
2. exact files changed;
3. exact commands and pass/fail counts;
4. commit hash(es);
5. git status result;
6. residual risks or blockers.
```

## Prompt A — integration audit

```text
Task: Milestone 1 Agent A — provenance and integration audit.

Read the shared preamble and execute only Section 3 of docs/plans/2026-07-18-milestone1-selective-tool-foundation.md.

Your only writable file is:
- docs/audits/2026-07-18-tool-platform-integration-baseline.md

Inspect actual Git objects and classify every file in master...codex/tool-platform as PORT_CORE, PORT_ADAPTED, REVIEW_LATER, or REJECT_STALE. Explicitly explain why commits 8888bd3 and 96f0b93 must not be merged or cherry-picked. Record the expected Milestone 1 file tree and test baseline.

Do not modify or test production code. Validate with git diff --check and commit:
docs(tools): record selective integration baseline
```

## Prompt B — taxonomy and canonical models

```text
Task: Milestone 1 Agent B — canonical taxonomy and models.

Read the shared preamble and execute only Section 4 of docs/plans/2026-07-18-milestone1-selective-tool-foundation.md.

Owned files:
- server/tool_platform/__init__.py
- server/tool_platform/taxonomy.py
- server/tool_platform/models.py
- server/tests/test_tool_platform_taxonomy.py
- server/tests/test_tool_platform_models.py

Port the final hardened state from 87cf803, not intermediate versions. Preserve separate data-mutation and execution-effect axes, strict/frozen JSON models, recursive redaction, stable event identity, UTC timestamps, and canonical tool_platform.* imports.

Do not create registry/catalog files and do not touch Agent Session files.

Required commit:
feat(tools): port canonical tool contracts
```

## Prompt C — definition, registry, and catalog

```text
Task: Milestone 1 Agent C — typed definition, registry, and catalog.

Your base commit must already contain Agent B's accepted canonical contracts. If it does not, stop and report the incorrect base.

Read the shared preamble and execute only Section 5 of docs/plans/2026-07-18-milestone1-selective-tool-foundation.md.

Owned files:
- server/tool_platform/definition.py
- server/tool_platform/registry.py
- server/tool_platform/catalog.py
- server/tests/test_tool_platform_registry.py

Port the final 87cf803 behavior. Catalog/project reads must never run availability probes. Missing agent/runtime/capability/facts fail closed. Catalog DTOs are deeply immutable, JSON-only, and contain no handler/probe/client objects. Definition freeze does not disable explicit async health refresh.

Do not modify taxonomy/models unless you find a blocking incompatibility. If blocked, report it instead of expanding scope.

Required commit:
feat(tools): port typed registry and catalog
```

## Prompt D — Manifest projection and architecture guard

```text
Task: Milestone 1 Agent D — Agent Manifest projection and architecture guard.

Your base commit must already contain Agents B and C. If tool_platform.registry cannot import and its focused tests are not green, stop and report the incorrect base.

Read the shared preamble and execute only Section 6 of docs/plans/2026-07-18-milestone1-selective-tool-foundation.md.

Owned files:
- server/agent_session/execution_context.py
- server/agent_session/agent_registry.py
- server/tests/test_agent_registry.py
- server/tests/test_tool_platform_architecture.py

Manually adapt only the selector/projection ideas from 910f2fb and 87cf803 to current master. Preserve allowed-field presence semantics: absent means unrestricted projection, explicit [] means deny-all, non-empty means authoritative. Keep enforcement_status exactly legacy_runtime.

The bridge is pure data compilation. It must not run probes, execute tools, modify session state, change runtime tool lists, or alter HITL.

Architecture tests must catch server.tool_platform imports, duplicate ToolKind enums, runtime integration in Milestone 1, and unexpected approval stores.

Required commit:
feat(agent): compile manifest tool projections
```

## Prompt E — independent read-only review

```text
Task: Milestone 1 independent final review. Read-only only.

Repository/worktree: <WORKTREE_PATH>
Review range: <MILESTONE_BASE>..<MILESTONE_HEAD>

Read AGENTS.md, ADR-0012, the controlled-tool-platform design, and the detailed Milestone 1 plan. Inspect the complete diff and relevant current runtime code.

Do not edit, stage, commit, format, or fix anything.

Review for:
- fail-closed taxonomy and projections;
- strict schemas, deep immutability, JSON-only snapshots, and recursive redaction;
- duplicate import/Enum identities;
- alias/version conflicts;
- availability probes accidentally running during reads;
- allowed absent vs explicit empty semantics;
- accidental DeepAgents/runtime enforcement before Milestone 2;
- approval, Train/Hybrid, or session behavior changes;
- tests that only validate their own fixtures rather than production behavior;
- files outside the approved Milestone 1 ownership.

Output findings first, ordered P0, P1, P2, P3. Every finding needs exact file:line, impact, evidence/reproduction, and recommended correction. If there are no P0/P1 findings, say so explicitly and list residual risks and missing coverage.
```

## Prompt F — post-fix verification

Use this only after review findings are fixed:

```text
Task: Verify Milestone 1 after review fixes. Do not modify code unless explicitly instructed.

Repository/worktree: <WORKTREE_PATH>
Expected head: <MILESTONE_HEAD>

Run the final validation commands from Section 8 of docs/plans/2026-07-18-milestone1-selective-tool-foundation.md. Confirm the worktree is clean, enumerate the exact Milestone 1 commits, and verify codex/tool-platform was not merged.

Return exact pass counts, Ruff/diff-check results, git status, unresolved warnings, and a final GO/NO-GO recommendation for Milestone 2.
```
