# Coding Agent Capability Audit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Establish evidence-backed, repeatable golden scenarios for normal project development and produce a prioritized Coding Agent gap report without changing runtime implementation.

**Architecture:** The audit adds deterministic backend trajectory/workspace scenarios and frontend Workbench projections in new files only. It evaluates existing production contracts for project understanding, multi-file editing, terminal verification, failure repair, diff review, refresh recovery, and Workspace isolation. Findings become the input to a later Coding-first implementation phase.

**Tech Stack:** Python 3.11, pytest, DeepAgents runtime contracts, React 18, TypeScript, Vitest.

---

## Scope and ownership

**Create only:**
- `server/tests/fixtures/coding_agent_golden_path.json`
- `server/tests/test_coding_agent_golden_path.py`
- `client/src/agent/testing/codingAgentScenarios.ts`
- `client/src/test/CodingAgentGoldenPath.test.tsx`
- `docs/coding-agent-capability-audit-2026-07-11.md`

Do not modify Agent Runtime, repositories, services, manifests, protocol, timeline, Workbench components/styles, existing tests, or Phase 6 files. A failing production capability must be reported as a gap; do not weaken the scenario or patch implementation.

## Task 1: Freeze representative engineering scenarios

1. Define at least six scenarios: Python bug fix, React change, cross-stack feature, multi-file refactor, verification failure/repair, and refresh/resume.
2. For every scenario specify initial files, required reads, allowed writes, commands, expected verification, expected changed files, and forbidden paths.
3. Add explicit Build-mode availability and Hybrid coding/training coexistence invariants.
4. Validate the fixture schema in a failing pytest, then add the fixture and make the schema test pass.
5. Commit.

## Task 2: Audit backend production contracts

1. Add CPU-only tests that exercise existing path policy, Build tool availability, trajectory scoring/guards, failure-reread requirement, verification classification, stable session identity, and changed-file/artifact projection where exposed.
2. Never call a live model, CUDA, network, package installer, or destructive Git command.
3. Classify unsupported end-to-end behavior as an explicit expected gap in the report rather than a fake passing assertion.
4. Run the new backend test plus existing trajectory/workspace focused tests.
5. Commit.

## Task 3: Audit Workbench coding continuity

1. Add deterministic TypeScript scenario projections for command, diff, permission, failure, repair, verification, summary, and refresh recovery.
2. Assert normal Coding activity remains ordered and visible in Build and Hybrid modes, including alongside training activity.
3. Assert refresh preserves session identity, changed files, terminal/diff activity, and pending approval semantics represented by existing contracts.
4. Run the new Vitest test and typecheck.
5. Commit.

## Task 4: Produce the capability report

1. Report each capability as `proven`, `partially proven`, or `missing` with exact test/code evidence.
2. Separate product gaps from test-environment limitations.
3. Prioritize the next Coding-first implementation phase by user impact and architectural risk.
4. Explicitly identify any regression caused by training-oriented changes.
5. Run `git diff --check`, verify only five owned files changed, and commit.

## Verification

```powershell
C:\Users\JHJ\Desktop\finetune-platform\.venv\Scripts\python.exe -m pytest server/tests/test_coding_agent_golden_path.py server/tests/test_agent_trajectory.py server/tests/test_workspace_path_policy.py -q
cd client
npx vitest run src/test/CodingAgentGoldenPath.test.tsx
npm run typecheck
git diff --check
```

The audit is complete only when the report distinguishes what the Coding Agent demonstrably does today from what still requires implementation.

