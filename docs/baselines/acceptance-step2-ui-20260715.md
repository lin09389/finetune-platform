# Acceptance: Step 2 + UI (2026-07-15)

Model: deepseek / deepseek-v4-flash  
Commit context: post 2691985 (workbench progress UI + live SSE) + step2 harness  
Scenarios: C1, C3, C5 (fixtures reset)

## Results

| Scenario | Final status | completed_ok | tools (server) | verify | gate | summary sections |
|----------|--------------|--------------|----------------|--------|------|------------------|
| C1 | completed | true | 12 | 1/1 | true | 已完成项/变更文件/验证结果/平台完成核对 |
| C3 | completed* | true | 24 | 1/1 | true | same (*after multi-HITL unstick) |
| C5 | completed | true | 20 | 1/1 | true | same |

\* C3 initial runner stuck on multi-action HITL (Expected 5 decisions, got 1). Product resume after `/decide` with 5 approves completed successfully.  
  **Follow-up:** `server/scripts/run_agent_tool_baseline.py` now multi-decides via `/decide` (N approves in one request).

## Step 2 checks

| Check | Result |
|-------|--------|
| completion_gate on terminal | PASS (all 3) |
| tool_metrics present | PASS |
| working_state present | PASS |
| summary enrichment | PASS (all 3 after C3 complete) |
| exploration budget hard | N/A (tools 12–24 << 40/80 soft/hard) |
| blind execute latch fire | Not observed (no trajectory_guard_blocked for blind_execute_retry; C3 had 6 execute fails but likely varied commands / observations interleaved) |
| live metrics climb (C3 poll) | PASS tools 15→24 while running, verify 0→1, then gate=true |

## UI path

- REST `GET /agent-sessions/{id}` exposes tool_metrics / completion_gate / working_state for Environment rail.
- Event DB dump may omit `payload.session_progress` (enrichment is on bus notify); live UI relies on SSE merge + workspace refresh.

## Verdict

**Step 2 + UI acceptance: PASS with note**

- Product completion/metrics/summary path healthy on C1/C5 fully automated; C3 needs multi-decision HITL approve in automation.
- No regression vs post-step1 completed_ok on coding scenarios once HITL is handled.
