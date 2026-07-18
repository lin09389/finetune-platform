# Tool Platform Selective Integration Baseline

**Audit date:** 2026-07-18
**Compared range:** `master...codex/tool-platform`
**Reference tip:** `87cf8032` (`fix(tools): harden registry projections`)
**Merge base:** `64ff8cd05ae467dc86b996713445e4ffa1975c65`

## Immutable Git facts

The actual oldest-to-newest commits in `master..codex/tool-platform` are:

```text
8888bd3 feat(agent): establish tool platform baseline
96f0b93 test(agent): make runtime fixtures work in clean worktrees
acdd7d2 feat(tools): define canonical tool taxonomy
d517fea feat(tools): define canonical tool models
b697e87 fix(tools): harden canonical tool contracts
6e4b390 feat(tools): add typed tool registry
910f2fb feat(agent): extend manifest tool selectors
87cf803 fix(tools): harden registry projections
```

`git diff --name-status master...codex/tool-platform` reports 29 files: 13 added and 16 modified. The old branch adds 3,573 lines and removes 19 lines in this merge-base diff. Its first commit alone changes 17 files with 1,755 insertions and 17 deletions; it is therefore not a narrowly scoped prerequisite for the later tool contracts.

The relevant commit statistics recorded from Git are:

| Commit | Actual scope |
| --- | --- |
| `8888bd3` | 17 files, 1,755 insertions, 17 deletions; mixes Git runtime tools with event batching, repository/query changes, retries, recovery, lifespan, configuration, and tests. |
| `96f0b93` | 1 runtime-fixture test file; 5 insertions and 5 deletions. |
| `acdd7d2` | 3 files, 253 insertions; canonical taxonomy and its tests. |
| `d517fea` | 2 files, 265 insertions; canonical models and their tests. |
| `b697e87` | 5 files, 258 insertions, 41 deletions; hardens the taxonomy/models final state. |
| `6e4b390` | 4 files, 561 insertions; typed registry, definitions, catalog, and tests. |
| `910f2fb` | 3 files, 227 insertions, 6 deletions; manifest selector/projection ideas. |
| `87cf803` | 10 files, 370 insertions, 80 deletions; final hardening for registry projections and related tests. |

## File disposition

`PORT_CORE` means port the final `87cf803` content selectively. `PORT_ADAPTED` means manually rebase only the projection semantics onto current `master`; it is not safe to copy the old file wholesale. `REVIEW_LATER` is useful material outside Milestone 1. `REJECT_STALE` is an old Agent Session/runtime baseline change that must not enter this integration.

| Status | File | Basis for disposition |
| --- | --- | --- |
| REVIEW_LATER | `docs/plans/2026-07-16-complete-tool-platform.md` | Historic broad M1--M4 plan; useful context, but superseded for this selective Milestone 1 and not an implementation input. |
| PORT_ADAPTED | `server/agent_session/agent_registry.py` | Contains the pure `tool_projection_context()` bridge and selector validation, but must be manually rebased to the current registry. |
| REJECT_STALE | `server/agent_session/agents/build.agent.yaml` | Adds live Git tools to the Build manifest; that changes the runtime tool surface before the approved enforcement migration. |
| REJECT_STALE | `server/agent_session/deepagents_events.py` | Token batching and direct broadcast behavior are unrelated event-transport/runtime changes. |
| REJECT_STALE | `server/agent_session/deepagents_runtime.py` | Injects live Git tools, changes event mapper construction, and changes permission lookup behavior. |
| PORT_ADAPTED | `server/agent_session/execution_context.py` | Adds manifest selector fields and explicit-`allowed` presence semantics required for projection; adapt only these data-model semantics. |
| REJECT_STALE | `server/agent_session/repository.py` | Changes session persistence/query behavior for the old resilience baseline, not tool description/projection. |
| REJECT_STALE | `server/agent_session/service.py` | Wires the old baseline's broadcast/runtime behavior. |
| REJECT_STALE | `server/agent_session/services/background_task_manager.py` | Adds automatic retry and timeout behavior; outside Milestone 1 and changes session execution semantics. |
| REJECT_STALE | `server/agent_session/services/event_broadcast.py` | Adds direct, non-persisted SSE broadcast support; event transport is explicitly out of scope. |
| REJECT_STALE | `server/agent_session/services/recovery_service.py` | Adds approval expiry/recovery transitions, which would alter the authoritative approval flow. |
| REJECT_STALE | `server/agent_session/session_state_machine.py` | Persists approval timing to support the rejected expiry mechanism. |
| REVIEW_LATER | `server/agent_session/tools/__init__.py` | Empty package marker for the old runtime Git-tool suite; retain only as a later native-tool migration consideration. |
| REVIEW_LATER | `server/agent_session/tools/git_tools.py` | Structured Git read tools are useful in the later Git migration step, but Milestone 1 must not add executable runtime tools. |
| REJECT_STALE | `server/apps/lifespan.py` | Starts an approval-sweep background task; lifespan changes are explicitly excluded. |
| REJECT_STALE | `server/core/config.py` | Adds retry and approval-timeout configuration for the rejected baseline. |
| PORT_ADAPTED | `server/tests/test_agent_registry.py` | Supplies selector presence, canonical kind/risk, and legacy-runtime tests; preserve only tests adapted to current registry behavior. |
| REJECT_STALE | `server/tests/test_agent_session_deepagents_events.py` | Validates the old event batching/transport behavior. |
| REJECT_STALE | `server/tests/test_agent_session_deepagents_runtime.py` | Covers baseline runtime Git/broadcast behavior; `96f0b93` further changes its fixtures. |
| REVIEW_LATER | `server/tests/test_agent_session_git_tools.py` | Test coverage for executable Git tools, deferred with the Git-tool migration. |
| PORT_CORE | `server/tests/test_tool_platform_models.py` | Final strict, immutable, redacting canonical-model contract tests from `d517fea` through `87cf803`. |
| PORT_CORE | `server/tests/test_tool_platform_registry.py` | Final typed registry/catalog projection tests from `6e4b390` through `87cf803`. |
| PORT_CORE | `server/tests/test_tool_platform_taxonomy.py` | Final fail-closed taxonomy tests from `acdd7d2` through `87cf803`. |
| PORT_CORE | `server/tool_platform/__init__.py` | Canonical package boundary. |
| PORT_CORE | `server/tool_platform/catalog.py` | JSON-only, immutable catalog snapshot/projection DTOs; port final hardened version. |
| PORT_CORE | `server/tool_platform/definition.py` | Typed definitions and projection constraints; port final hardened version. |
| PORT_CORE | `server/tool_platform/models.py` | Strict canonical invocation/result/event models, recursive redaction, and frozen JSON handling. |
| PORT_CORE | `server/tool_platform/registry.py` | Fail-closed resolution, availability refresh, and catalog projection behavior. |
| PORT_CORE | `server/tool_platform/taxonomy.py` | Canonical tool kind/risk/effect taxonomy with explicit fail-closed defaults. |

## Why the first two commits must not be merged or cherry-picked

`8888bd3` is a mixed Agent Session resilience/runtime baseline rather than a tool-contract commit. In one commit it adds runtime-visible Git tools and Build-manifest entries, changes DeepAgents assembly and permission lookup, batches and broadcasts events, changes repository queries, adds retries and approval expiry/recovery behavior, creates a lifespan task, and adds configuration. Merging or cherry-picking it would violate the Milestone 1 boundaries on DeepAgents behavior, approvals, event transport, lifespan, configuration, and runtime tools. It also obscures provenance for the later canonical contracts.

`96f0b93` is coupled to that rejected baseline: it changes fixtures in `test_agent_session_deepagents_runtime.py` for the old runtime worktree behavior. It provides no canonical taxonomy, model, registry, catalog, or manifest-projection contract, and cherry-picking it would import test assumptions for behavior deliberately excluded from this milestone.

Neither commit is an ancestor requirement for selectively reading and porting the final `87cf803` contract files. The source branch remains a read-only reference; no old-branch commit is to be merged.

## Expected Milestone 1 tree

After Agents A--D, the only new production package files are:

```text
server/tool_platform/__init__.py
server/tool_platform/taxonomy.py
server/tool_platform/models.py
server/tool_platform/definition.py
server/tool_platform/registry.py
server/tool_platform/catalog.py
```

The only existing Agent-related files permitted to change are:

```text
server/agent_session/execution_context.py
server/agent_session/agent_registry.py
server/tests/test_agent_registry.py
```

The corresponding new tests are `server/tests/test_tool_platform_taxonomy.py`, `server/tests/test_tool_platform_models.py`, `server/tests/test_tool_platform_registry.py`, and `server/tests/test_tool_platform_architecture.py`. No `deepagents_runtime.py`, approval/recovery, event transport, Train/Hybrid, frontend, Electron, lifespan, repository, or configuration file is part of the expected Milestone 1 tree.

## Test baseline

This audit intentionally did not run production code or tests. The source-tip structural baseline, counted from the `87cf803` test definitions, is 6 taxonomy tests, 11 model tests, and 15 registry tests (32 focused tool-platform tests total). `test_agent_registry.py` contains 14 tests at that source tip, including the manifest-selector coverage that must be adapted rather than copied wholesale.

The planned cumulative validation after the selective ports is:

```powershell
python -m pytest server/tests/test_tool_platform_taxonomy.py server/tests/test_tool_platform_models.py server/tests/test_tool_platform_registry.py server/tests/test_tool_platform_architecture.py server/tests/test_agent_registry.py server/tests/test_agent_permission.py server/tests/test_agent_session_deepagents_runtime.py -q
python -m ruff check server/tool_platform server/agent_session/execution_context.py server/agent_session/agent_registry.py server/tests/test_tool_platform_*.py server/tests/test_agent_registry.py
git diff --check
```

The acceptance condition is a clean worktree with those checks passing and no runtime tool behavior change. Agent A's required validation is documentation-only: `git diff --check`.
