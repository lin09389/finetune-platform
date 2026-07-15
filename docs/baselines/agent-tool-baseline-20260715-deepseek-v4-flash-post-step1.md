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
| C1 | ags_c61da533a31842929b90f96beff2e4c5 | completed | 1 | 57 | 1 | 0 | 1 | 1 | 1 | 6 | 0 | 1.31 | none | metrics:server; gate:已写 1 个路径；diff 可见；验证通过; completion_gate:yes |
| C2 | ags_1345210b31bd4a18af1a97dfbff4bf67 | completed | 1 | 36 | 0 | 0 | 1 | 1 | 1 | 4 | 0 | 0.73 | none | metrics:server; gate:已写 1 个路径；diff 可见；验证通过; completion_gate:yes |
| C3 | ags_ab255c67144043859bd8c1a70f3a8b2d | completed | 1 | 57 | 4 | 0 | 1 | 1 | 1 | 6 | 0 | 1.33 | none | metrics:server; gate:已写 2 个路径；diff 可见；验证通过; completion_gate:yes |
| C5 | ags_201d6d31f29145cbb816f53e35360832 | completed | 1 | 57 | 3 | 0 | 1 | 1 | 1 | 4 | 0 | 1.2 | none | metrics:server; gate:已写 1 个路径；diff 可见；验证通过; completion_gate:yes |

## §5.3 summary

| metric | value |
|--------|------|
| N | 4 |
| completion_rate | 1.0 |
| verify_attempt_rate_coding | 1.0 |
| verify_success_rate | 1.0 |
| diff_visible_rate | 1.0 |
| mean_tools_total | 51.75 |
| trajectory_block_scene_rate | 0.0 |
| mean_hitl | 5.0 |
| human_reprompt_rate | 0.0 |
| failure_kinds | {'none': 4} |

## §5.4 qualitative (auto)

1. Offline harness (fake model e2e + agent_eval) was green before this live run.
2. Live scores use deepseek-v4-flash via Agent Session API with confirm_all + auto HITL approve.
3. Metrics are event-heuristic; re-check Timeline in Workbench if a row looks wrong.
