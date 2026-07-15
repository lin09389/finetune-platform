# Agent tool baseline run — 2026-07-15

## §1 conditions

| field | value |
|------|------|
| date | 2026-07-15 |
| operator | automated API runner |
| commit | d0e9715 |
| backend | uvicorn :8010 (this session) |
| provider/model | deepseek / deepseek-v4-flash |
| real model | yes |
| task_mode | per scenario |
| autonomy_mode | confirm_all (HITL auto-approved by runner) |
| notes | semi-auto; T2 not run |

## §5.2 scores

| baseline_id | session_id | status | completed_ok | tools_total | tools_failed | trajectory_blocks | verify_attempted | verify_ok | diff_visible | hitl_count | human_reprompt | duration_min | failure_kind | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C1 | ags_325cd6261b6e47dfb2c960331431bf11 | needs_manual_review | 0 | 36 | 0 | 1 | 1 | 0 | 1 | 6 | 0 | 0.8 | other | needs_manual_review; pattern:write_without_read |
| C2 | ags_c115f430d5294f5ebc2512d139f710fd | completed | 0 | 33 | 0 | 0 | 1 | 0 | 1 | 4 | 0 | 0.66 | none | verify_failed |
| C3 | ags_0c13c259a92b444a8aac887b1aa11696 | needs_manual_review | 0 | 51 | 0 | 0 | 1 | 0 | 1 | 4 | 0 | 0.77 | loop | loop_block; needs_manual_review |
| C5 | ags_a24426c69c8c4dacaaab1d2e9a1cc597 | completed | 0 | 120 | 0 | 2 | 1 | 0 | 1 | 6 | 0 | 2.87 | none | verify_failed; pattern:write_without_read |
| T1 | ags_e79c0c82c9904a14b5c61368fcfe9b78 | completed | 1 | 36 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0.45 | none | pattern:no_verify; train_propose_only |

## §5.3 summary

| metric | value |
|--------|------|
| N | 5 |
| completion_rate | 0.2 |
| verify_attempt_rate_coding | 1.0 |
| verify_success_rate | 0.0 |
| diff_visible_rate | 1.0 |
| mean_tools_total | 55.2 |
| trajectory_block_scene_rate | 0.4 |
| mean_hitl | 4.2 |
| human_reprompt_rate | 0.0 |
| failure_kinds | {'other': 1, 'none': 3, 'loop': 1} |

## §5.4 qualitative (auto)

1. Offline harness (fake model e2e + agent_eval) was green before this live run.
2. Live scores use deepseek-v4-flash via Agent Session API with confirm_all + auto HITL approve.
3. Metrics are event-heuristic; re-check Timeline in Workbench if a row looks wrong.

## Post-check (workspace files after run)

- C1 `app.py`: `return items[index]` (off-by-one fixed on disk)
- C2 `app.py`: null → `""` then strip/lower (looks correct)
- C3 `cli.py`: validation helpers added
- C5 `Counter.tsx`: functional `setCount((prev) => prev + 1)`
- Offline: `pytest` coding e2e + agent_eval = 28 passed
- Live gate: `ENABLE_REAL_MODEL_EVALUATION` still false (agent-eval live path unused; used Agent Session API instead)

## Interpretation vs Step 1 gate

Protocol §6 says Step 1 can start after C1–C3+C5+T1 filled. **This batch fills that gate.**
Strict completed_ok is low; product Step 1 (state card / completion UI / metrics) is still justified by verify_ok=0 and NMR/loop patterns.
