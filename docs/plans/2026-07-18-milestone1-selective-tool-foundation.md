# Milestone 1 Selective Tool Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task.

**Goal:** Selectively port the canonical taxonomy, models, typed registry, catalog, and Agent Manifest projection from `codex/tool-platform` onto current `master` without importing its mixed legacy baseline or changing runtime behavior.

**Architecture:** `tool_platform` is a strict, JSON-safe semantic control plane. Milestone 1 only describes and projects tools; DeepAgents remains the active runtime and existing permissions remain authoritative. The implementation is split into one audit task, three dependency-ordered code tasks, and a final read-only review.

**Tech Stack:** Python 3.11, Pydantic v2, pytest, Ruff, Git worktrees.

---

## 1. Execution topology

Use one integration branch and separate worktrees for each external Agent. Agents must not merge their own branches.

```text
codex/tool-platform-integration-plan @ acb0d00
        |
        +-- Agent A: audit/provenance
        |       merge after review
        +-- Agent B: taxonomy/models
        |       merge after tests/review
        +-- Agent C: definition/registry/catalog
        |       merge after tests/review
        +-- Agent D: Manifest projection/architecture guard
        |       merge after tests/review
        +-- Agent E: read-only final review
```

Agent C must start from the integration head containing Agent B. Agent D must start from the integration head containing Agent C. Agent E starts only after A-D are integrated.

Recommended branch names:

- `codex/m1-audit`
- `codex/m1-tool-contracts`
- `codex/m1-tool-registry`
- `codex/m1-manifest-projection`

## 2. Shared constraints

- Source reference: `codex/tool-platform` at `87cf803`.
- Planning base: `codex/tool-platform-integration-plan` at `acb0d00`.
- Never cherry-pick or merge `8888bd3` or `96f0b93`.
- Do not modify `deepagents_runtime.py`, `deepagents_events.py`, repository, lifecycle, lifespan, configuration, frontend, Electron, training tools, or approval behavior.
- Do not add runtime registration, handler execution, availability probing at read time, policy enforcement, or Tool Gateway behavior.
- Production and tests use canonical `tool_platform.*` imports, not `server.tool_platform.*`.
- Preserve unrelated user changes. Do not use `git add .`, destructive checkout, reset, or force operations.
- Use `apply_patch` for edits.
- Tests must not require network access, a real model, DeepAgents installation, CUDA, or package installation.
- Every implementation Agent returns one or more focused commits, an exact test report, and a clean worktree.

## 3. Agent A — provenance and integration audit

### Files

- Create: `docs/audits/2026-07-18-tool-platform-integration-baseline.md`

### Step 1: Record immutable Git facts

Run:

```powershell
git merge-base master codex/tool-platform
git log --format="%h %s" --reverse master..codex/tool-platform
git diff --name-status master...codex/tool-platform
git show --stat --oneline 8888bd3 96f0b93 acdd7d2 d517fea b697e87 6e4b390 910f2fb 87cf803
```

Record actual output, not remembered summaries.

### Step 2: Classify every old-branch file

Use these categories:

- `PORT_CORE`: final semantic tool implementation/tests;
- `PORT_ADAPTED`: Agent Manifest/projection logic that must be rebased manually;
- `REVIEW_LATER`: useful but outside Milestone 1;
- `REJECT_STALE`: older session/runtime baseline that must not enter the integration.

At minimum, classify all 29 files in `git diff --name-status master...codex/tool-platform`.

### Step 3: Define expected Milestone 1 tree

Expected production files after A-D:

```text
server/tool_platform/__init__.py
server/tool_platform/taxonomy.py
server/tool_platform/models.py
server/tool_platform/definition.py
server/tool_platform/registry.py
server/tool_platform/catalog.py
```

Only these existing Agent files may change:

```text
server/agent_session/execution_context.py
server/agent_session/agent_registry.py
server/tests/test_agent_registry.py
```

### Step 4: Validate and commit

```powershell
git diff --check
git add docs/audits/2026-07-18-tool-platform-integration-baseline.md
git commit -m "docs(tools): record selective integration baseline"
git status --short
```

Expected: one documentation commit; clean worktree.

## 4. Agent B — canonical taxonomy and models

### Files

- Create: `server/tool_platform/__init__.py`
- Create: `server/tool_platform/taxonomy.py`
- Create: `server/tool_platform/models.py`
- Create: `server/tests/test_tool_platform_taxonomy.py`
- Create: `server/tests/test_tool_platform_models.py`

### Step 1: Port tests before production code

Use the final files from `87cf803` as references:

```powershell
git show 87cf803:server/tests/test_tool_platform_taxonomy.py
git show 87cf803:server/tests/test_tool_platform_models.py
```

Create the tests with `apply_patch`. Keep the test asserting that `CanonicalToolMeta.kind` uses the exact same `ToolKind` class imported from `tool_platform.taxonomy`.

### Step 2: Confirm the tests fail

```powershell
python -m pytest server/tests/test_tool_platform_taxonomy.py server/tests/test_tool_platform_models.py -q
```

Expected: import/collection failure because production modules do not exist.

### Step 3: Port the final implementation

Use:

```powershell
git show 87cf803:server/tool_platform/taxonomy.py
git show 87cf803:server/tool_platform/models.py
```

Required properties:

- every `ToolKind` has an explicit fail-closed default;
- data mutation and execution effects are separate axes;
- process/network/credential effects are composable;
- canonical name, risk, location, schemas, invocation, result, error, availability, and event models are strict;
- nested JSON is defensively frozen;
- diagnostic serialization recursively redacts sensitive keys, Bearer values, URL query secrets, and JSON-encoded secret content;
- events include stable event ID, attempt, sequence, and timezone-aware UTC timestamp;
- model inputs reject extras and unintended coercion.

Do not simplify hardening just because the original commits were incremental; port the final `87cf803` state.

### Step 4: Run focused validation

```powershell
python -m pytest server/tests/test_tool_platform_taxonomy.py server/tests/test_tool_platform_models.py -q
python -m ruff check server/tool_platform server/tests/test_tool_platform_taxonomy.py server/tests/test_tool_platform_models.py
git diff --check
```

Expected: all focused tests pass; Ruff and whitespace checks pass.

### Step 5: Commit

```powershell
git add server/tool_platform/__init__.py server/tool_platform/taxonomy.py server/tool_platform/models.py server/tests/test_tool_platform_taxonomy.py server/tests/test_tool_platform_models.py
git commit -m "feat(tools): port canonical tool contracts"
git status --short
```

Expected: one focused commit; clean worktree.

## 5. Agent C — typed definition, registry, and catalog

### Dependency

Start from the integration head containing Agent B's accepted commit.

### Files

- Create: `server/tool_platform/definition.py`
- Create: `server/tool_platform/registry.py`
- Create: `server/tool_platform/catalog.py`
- Create: `server/tests/test_tool_platform_registry.py`

### Step 1: Port final tests first

```powershell
git show 87cf803:server/tests/test_tool_platform_registry.py
```

Tests must cover:

- strict Pydantic input/output models;
- async-only handler and availability probe contracts;
- alias and version resolution;
- duplicate canonical name/alias/version rejection;
- absent runtime, capability, agent, or fact failing closed;
- explicit empty allowed names meaning deny-all;
- explicit async availability refresh with timeout;
- catalog/project reads never executing probes;
- deep immutable, JSON-only catalog snapshots;
- handlers and probes never entering a snapshot;
- registry definition freeze not preventing explicit health refresh.

### Step 2: Confirm failure

```powershell
python -m pytest server/tests/test_tool_platform_registry.py -q
```

Expected: missing production modules.

### Step 3: Port final production code

Use the final versions from `87cf803`. Preserve:

```python
ToolDefinition
ToolProjectionContext
ToolRegistry
ToolCatalogEntry
ToolCatalogSnapshot
ToolProjectionConstraints
catalog_json
```

Facts must contain strict JSON only and be deeply immutable. `catalog()` returns DTOs, not raw executable dictionaries. `snapshot()` contains no callable or live client object.

### Step 4: Run focused and cumulative validation

```powershell
python -m pytest server/tests/test_tool_platform_taxonomy.py server/tests/test_tool_platform_models.py server/tests/test_tool_platform_registry.py -q
python -m ruff check server/tool_platform server/tests/test_tool_platform_taxonomy.py server/tests/test_tool_platform_models.py server/tests/test_tool_platform_registry.py
git diff --check
```

### Step 5: Commit

```powershell
git add server/tool_platform/definition.py server/tool_platform/registry.py server/tool_platform/catalog.py server/tests/test_tool_platform_registry.py
git commit -m "feat(tools): port typed registry and catalog"
git status --short
```

## 6. Agent D — Manifest projection and architecture guard

### Dependency

Start from the integration head containing Agents B and C.

### Files

- Modify: `server/agent_session/execution_context.py`
- Modify: `server/agent_session/agent_registry.py`
- Modify: `server/tests/test_agent_registry.py`
- Create: `server/tests/test_tool_platform_architecture.py`

### Step 1: Characterize current manifest behavior

Read current versions before editing:

```powershell
Get-Content server/agent_session/execution_context.py -Raw
Get-Content server/agent_session/agent_registry.py -Raw
python -m pytest server/tests/test_agent_registry.py -q
```

Record the baseline result in the completion report.

### Step 2: Add failing selector tests

Add tests for:

- `allowed` absent -> `allowed_names is None`;
- `allowed: []` -> `allowed_names == frozenset()`;
- non-empty allowed -> exact canonical/alias selector set;
- kinds -> `ToolKind` values;
- denied names, risk ceiling, runtime, capability, provider/model/platform facts;
- invalid kinds and risk values produce actionable manifest errors;
- `enforcement_status == "legacy_runtime"`.

### Step 3: Port only projection-related logic

Use `910f2fb` and `87cf803` as references, but manually adapt to current `master`. Do not overwrite current classes wholesale.

Implement a pure bridge equivalent to:

```python
AgentRegistry.tool_projection_context(
    agent_id,
    runtime_kind=None,
    enabled_capabilities=None,
    provider_facts=None,
    model_facts=None,
    platform_facts=None,
) -> ToolProjectionContext
```

The bridge may only compile data. It must not mutate a session, run probes, execute handlers, change DeepAgents tool lists, or alter HITL permissions.

### Step 4: Add architecture guards

`test_tool_platform_architecture.py` must assert:

- production/tests import `tool_platform.*`, never `server.tool_platform.*`;
- Milestone 1 does not import Tool Registry or Gateway from `deepagents_runtime.py` or `runtime_factory.py`;
- no second ToolKind enum exists in production;
- no new approval repository/state machine exists;
- only the expected production and Agent files were introduced/modified for Milestone 1.

### Step 5: Run cumulative regression

```powershell
python -m pytest server/tests/test_tool_platform_taxonomy.py server/tests/test_tool_platform_models.py server/tests/test_tool_platform_registry.py server/tests/test_tool_platform_architecture.py server/tests/test_agent_registry.py server/tests/test_agent_permission.py server/tests/test_agent_session_deepagents_runtime.py -q
python -m ruff check server/tool_platform server/agent_session/execution_context.py server/agent_session/agent_registry.py server/tests/test_tool_platform_*.py server/tests/test_agent_registry.py
git diff --check
```

Expected: all tests pass; no DeepAgents runtime behavior changed.

### Step 6: Commit

```powershell
git add server/agent_session/execution_context.py server/agent_session/agent_registry.py server/tests/test_agent_registry.py server/tests/test_tool_platform_architecture.py
git commit -m "feat(agent): compile manifest tool projections"
git status --short
```

## 7. Agent E — read-only final review

Agent E must not edit, stage, commit, reformat, or fix files. Review the integrated Milestone 1 range against this plan and ADR-0012.

Required review dimensions:

- semantic correctness and fail-closed behavior;
- JSON immutability and secret redaction;
- duplicate module/Enum identity;
- manifest presence semantics;
- accidental runtime enforcement;
- imports and dependency direction;
- test self-confirmation or missing negative cases;
- unintended changes outside Milestone 1 ownership.

Output findings first, ordered P0-P3, with exact `file:line`, impact, reproduction/reasoning, and recommended correction. If no blocking findings exist, explicitly state that and list residual risks.

## 8. Main-thread integration checklist

After every Agent:

1. verify its branch/worktree is clean;
2. inspect `git show --stat` and full diff;
3. reject out-of-scope files;
4. run that Agent's focused tests in the integration worktree;
5. integrate by cherry-picking only reviewed commits;
6. notify the next Agent of the new exact integration HEAD.

Final Milestone 1 checks:

```powershell
python -m pytest server/tests/test_tool_platform_taxonomy.py server/tests/test_tool_platform_models.py server/tests/test_tool_platform_registry.py server/tests/test_tool_platform_architecture.py server/tests/test_agent_registry.py server/tests/test_agent_permission.py server/tests/test_agent_session_deepagents_runtime.py server/tests/test_application_profiles.py -q
python -m ruff check server/tool_platform server/agent_session/execution_context.py server/agent_session/agent_registry.py server/tests/test_tool_platform_*.py server/tests/test_agent_registry.py
git diff --check
git status --short
```

Milestone 1 is complete only when:

- the integrated worktree is clean;
- Agent E reports no unresolved P0/P1;
- all cumulative tests pass;
- no runtime tool behavior changed;
- the old `codex/tool-platform` branch remains unmerged and available only as reference.
