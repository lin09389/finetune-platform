# Acceptance: post-B4 Phase B close-out (2026-07-15)

## Goal

Close Phase B (B0–B4 shipped, B5 suspended) with offline regression + live C1/C3/C5 cross-checks.

## §1 conditions

| field | value |
|------|------|
| date | 2026-07-15 |
| operator | automated goal harness |
| product commits | B0 `43a45d3` … B4 `9fdf302` (+ B1 label fix if committed with this note) |
| offline suite | pytest Phase B contracts (see scratch logs) |
| live API | `127.0.0.1:8010` health=200 |
| provider/model | deepseek / deepseek-v4-flash |
| autonomy | confirm_all (runner multi-decide HITL) |
| B5 | **suspended** (not implemented) |

Scratch evidence dir: goal implementer scratch (`phase-b-offline-pytest*.log`, `baseline-c1-c3-c5.log`, crosscheck JSON).

## §2 Offline regression (gating)

### Clean HEAD proof (authoritative)

Run with a clean worktree (WIP stashed) after shipping the missing module:

| suite | result |
|------|--------|
| `test_task_scope.py` | pass |
| `test_workspace_inventory.py` | pass |
| `test_session_progress_step2.py` | pass |
| `test_trajectory_step2.py` | pass |
| `test_multi_file.py` | pass |
| `test_session_progress.py` | pass |
| `test_knowledge_binding.py` | pass (covers shipped `context.knowledge_binding`) |
| **Total** | **43 passed** (`phase-b-offline-clean-head-final.log`, exit 0) |

### Ship-tree fix (skeptic gap)

- **Symptom on clean HEAD:** 3 failures with `ModuleNotFoundError: context.knowledge_binding`.
- **Root cause:** `server/context/deepagents.py` (committed with B1-era pack) imports `resolve_agent_knowledge_collection`, but `server/context/knowledge_binding.py` was never tracked.
- **Fix:** add and commit `server/context/knowledge_binding.py` + unit tests driving the real resolver.
- **Proof:** clean-tree suite log above (43 passed). Earlier “44 passed” claim was measured on a dirty WIP tree that already had the untracked module — superseded by this clean-HEAD evidence.

### Non-authoritative WIP note

While WIP was present, an extra session_progress test failure appeared when the card label was temporarily `**上下文**` without `（B1）`. Clean HEAD already labels `上下文（B1）`.

## §3 Live C1 / C3 / C5 (gating)

First live batch (API already up; process may predate full B1 metadata persistence):

| baseline_id | session_id | status | completed_ok | tools_total (runner) | verify | diff | hitl | duration_min |
|-------------|------------|--------|--------------|----------------------|--------|------|------|--------------|
| C1 | `ags_cb6a0b2c5e534970ab2273827ba590c5` | completed | 1 | 36 | 1/1 | 1 | 4 | 0.69 |
| C3 | `ags_fc89f338bb474734aeec2c5d14defc39` | completed | 1 | 45 | 1/1 | 1 | 6 | 1.18 |
| C5 | `ags_a68a003edd714cb3b959952e597a2ad4` | completed | 1 | 42 | 1/1 | 1 | 4 | 1.28 |

Summary: `N=3`, `completion_rate=1.0`, `verify_success_rate=1.0`, `diff_visible_rate=1.0`, `failure_kinds={none:3}`.

Runner artifacts: `tmp/baseline/results/baseline-20260715-230657-deepseek-v4-flash.{json,md}` and scratch `baseline-c1-c3-c5.log`.

**Note:** Runner logged occasional `approve failed … Permission part is not pending` after successful `/decide`; sessions still progressed to `completed` (non-blocking race / double-path approve).

### Post-restart C1 (B1 live proof)

API restarted with current tree; C1 re-run:

| field | value |
|------|------|
| session_id | `ags_fcecdd63b7574dfb9232bc5dbb5ccfec` |
| status | completed |
| completed_ok | 1 |
| verify | 1/1 |
| tools_total (runner) | 30 |
| artifact | `tmp/baseline/results/baseline-20260715-231038-deepseek-v4-flash.*` + `baseline-c1-post-restart.log` |

## §4 Cross-check B1 / B3 / B4

### Live batch C1/C3/C5 (first process)

| signal | C1 | C3 | C5 | notes |
|--------|----|----|-----|------|
| B1 `workspace_inventory` in `deep_context.context_engineering` | **absent** | **absent** | **absent** | Only `task.md` / alias listed; likely long-lived API process without B1 pack metadata fields |
| B1 `project_retrieval` | **absent** | **absent** | **absent** | same |
| B3 `recovery_state` present | yes | yes | yes | schema present |
| B3 `require_observation_before_retry` at terminal | false | **true** | false | C3 still latched at end (`last_failed_execute` set); blocks=0 (no same/varied thrash block observed) |
| B3 `blind_retry_blocks` | 0 | 0 | 0 | No thrash block fired |
| B4 `multi_file` on completion_gate | **null** | **null** | **null** | Each scenario **1** source write path → multi-file gate N/A |
| B4 written path count | 1 | 1 | 1 | Single-file edits |

### Post-restart C1

| signal | observation |
|--------|-------------|
| B1 `workspace_inventory.status` | **`ok`** |
| B1 `recommended_reads` | `["app.py"]` |
| B1 VFS file | `/context/retrieval/workspace-inventory.md` present in `files` |
| B1 `project_retrieval.status` | `empty` (`no_project_sources` — expected for tiny unindexed fixture) |
| B3 recovery latch at terminal | cleared / not requiring observation |
| B4 `completion_gate.multi_file` | present; `is_multi_file=false`, `source_write_count=1`, `path_verify_ok=true` |

### Offline structural cross-check (always)

Unit tests assert real shipped helpers:

- B0: `test_task_scope.py`
- B1: `test_workspace_inventory.py` (inventory inject + card label)
- B3: `test_session_progress_step2.py` / `test_trajectory_step2.py` (any execute blocked until observe)
- B4: `test_multi_file.py` (path-level verify when ≥2 source writes)

Direct pack call on fixture (scratch `b1-direct-inventory-check.log`): inventory `ok`, injects `workspace-inventory.md`.

## §5 Product regressions / notes

| item | severity | note |
|------|----------|------|
| B1 card label drift in WIP tree | fixed | Restored `上下文（B1）` |
| First live batch missing inventory metadata | process | Restart API after B1; post-restart C1 proves inject |
| HITL double-approve 404 noise | low | Non-blocking; sessions completed |
| B4 multi-file hard gate | N/A on C1/C3/C5 | Single-file writes only; covered by unit tests |
| B5 | suspended | No work |

## §6 Verdict

**Phase B close-out: PASS**

1. Offline Phase B contract suite green on **clean HEAD: 43 passed** (authoritative: `phase-b-offline-clean-head-final.log` / `phase-b-offline-post-commit.log`). Dirty-WIP “44 passed” is superseded and not used as the pass bar.  
2. Live C1/C3/C5 all terminal `completed` with `completed_ok=1` and verify 1/1.  
3. B1 proven live after API restart on C1; B3 recovery_state observed; B4 multi-file fields present when gate runs (single-file path).  
4. B5 remains suspended. Unrelated training/gpu/permission WIP left unstaged.

## Artifacts index

| path | purpose |
|------|---------|
| `docs/baselines/acceptance-post-b4-20260715.md` | this record |
| `tmp/baseline/results/baseline-20260715-230657-deepseek-v4-flash.*` | live C1/C3/C5 |
| `tmp/baseline/results/baseline-20260715-231038-deepseek-v4-flash.*` | post-restart C1 |
| goal scratch `phase-b-offline-clean-head-final.log` | **authoritative** clean-HEAD offline (43 passed) |
| goal scratch `phase-b-offline-post-commit.log` | post `knowledge_binding` commit re-run (43 passed) |
| goal scratch `phase-b-offline-clean-head-after-kb-fix.log` | after shipping module (39 then +kb tests) |
| goal scratch `baseline-c1-c3-c5.log` | live triple |
| goal scratch `baseline-c1-post-restart.log` | B1 live |
| goal scratch `b1-b3-b4-crosscheck.json` | first-batch metadata |
| goal scratch `c1-post-restart-crosscheck.json` | post-restart metadata |
