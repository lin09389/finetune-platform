"""Semi-automated baseline runner for agent-tool protocol (API + real model).

Simulates Workbench flow: create session → prompt → auto-approve HITL → score events.
Does not modify product code. Workspaces and results live under ``tmp/baseline/``.

Multi-action HITL: uses ``POST /agent-permissions/{id}/decide`` with N
``{type: approve}`` decisions (``/approve`` only ever sends one).

Usage (repo root)::

    uv run --extra all python server/scripts/run_agent_tool_baseline.py C1 C3 C5
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8010"
ROOT = Path(__file__).resolve().parents[2]
BASELINE_DIR = ROOT / "tmp" / "baseline"
RESULTS = BASELINE_DIR / "results"
PROVIDER = "deepseek"
MODEL = "deepseek-v4-flash"
AUTONOMY = "confirm_all"
POLL_S = 3.0
TIMEOUT_S = 20 * 60  # 20 min per scenario
TERMINAL = {
    "completed",
    "failed",
    "interrupted",
    "needs_manual_review",
}

# Priority gate first (protocol §6), then remaining of recommended 10.
SCENARIOS: list[dict[str, Any]] = [
    {
        "baseline_id": "C1",
        "dir": "C1-py-debug-off-by-one",
        "task_mode": "build",
        "prompt": "Correct the indexed selection boundary bug and cover the first and last valid positions.",
    },
    {
        "baseline_id": "C2",
        "dir": "C2-py-debug-null-config",
        "task_mode": "build",
        "prompt": "Diagnose and fix the null input failure without changing valid normalization behavior.",
    },
    {
        "baseline_id": "C3",
        "dir": "C3-py-feature-cli-validation",
        "task_mode": "build",
        "prompt": "Add deterministic CLI validation with actionable errors and a successful normal path.",
    },
    {
        "baseline_id": "C5",
        "dir": "C5-react-debug-stale-state",
        "task_mode": "build",
        "prompt": "Fix stale React state updates during rapid interaction and preserve accessible behavior.",
    },
    {
        "baseline_id": "T1",
        "dir": "T1-training-feature-dry-run",
        "task_mode": "train",
        "prompt": (
            "Only diagnose training configuration with propose_training / dry-run analysis. "
            "Do NOT submit real training. Summarize blockers or readiness."
        ),
    },
    {
        "baseline_id": "C4",
        "dir": "C4-py-refactor-service-boundary",
        "task_mode": "build",
        "prompt": "Extract normalization behavior behind a small service boundary while preserving public behavior.",
    },
    {
        "baseline_id": "C6",
        "dir": "C6-react-feature-error-state",
        "task_mode": "build",
        "prompt": "Add loading, recoverable error, retry, and success states without visual layout jumps.",
    },
    {
        "baseline_id": "C7",
        "dir": "C7-crossstack-debug-contract",
        "task_mode": "build",
        "prompt": "Align backend and frontend user field naming with an explicit compatibility boundary.",
    },
    {
        "baseline_id": "T3",
        "dir": "T3-hybrid-feature-train-evaluate",
        "task_mode": "hybrid",
        "prompt": (
            "Locate training-related issues in workflow/ui, then advise whether train is appropriate. "
            "Real training submit is optional; code understanding summary is required."
        ),
    },
    # T2 skipped unless models/datasets ready — filled as config later if needed
]


def http_json(method: str, path: str, body: dict | None = None, timeout: float = 60) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} -> {exc.code}: {detail[:800]}") from exc
    except URLError as exc:
        raise RuntimeError(f"{method} {path} connection failed: {exc}") from exc


def score_from_session(session: dict, events: list[dict], parts: list[dict] | None = None) -> dict[str, Any]:
    status = str(session.get("status") or "")
    tools_total = 0
    tools_failed = 0
    trajectory_blocks = 0
    verify_attempted = 0
    verify_ok = 0
    diff_visible = 0
    hitl_count = 0
    failure_kind = "none"
    notes: list[str] = []

    tool_names: list[str] = []

    for ev in events:
        et = str(ev.get("event_type") or "")
        payload = ev.get("payload") or {}
        msg = str(ev.get("message") or "")
        if et in {"tool_call", "tool_call_started", "tool_started"} or "tool_call" in et:
            tools_total += 1
            name = payload.get("tool") or payload.get("name") or payload.get("tool_name") or ""
            if name:
                tool_names.append(str(name))
        if et in {"tool_result", "tool_call_completed", "tool_completed"} or "tool_result" in et:
            ok = payload.get("ok")
            status_s = str(payload.get("status") or "").lower()
            if ok is False or status_s in {"failed", "error"} or "error" in msg.lower() and "failed" in msg.lower():
                tools_failed += 1
            # verify heuristics
            cmd = str(payload.get("command") or payload.get("input") or msg or "").lower()
            tool = str(payload.get("tool") or payload.get("name") or "").lower()
            if tool in {"execute", "bash", "shell"} or "pytest" in cmd or "typecheck" in cmd or "lint" in cmd or "npm test" in cmd:
                verify_attempted = 1
                if ok is True or status_s in {"ok", "success", "completed"} or "passed" in msg.lower():
                    verify_ok = 1
        if "trajectory_guard_blocked" in et or "trajectory" in et and "block" in et:
            trajectory_blocks += 1
        if "trajectory_guard_blocked" in json.dumps(payload, ensure_ascii=False):
            trajectory_blocks += 1
        if "permission" in et or et in {"waiting_permission", "permission_requested", "action_requested"}:
            hitl_count += 1
        if "diff" in et or payload.get("diff") or payload.get("hunks"):
            diff_visible = 1
        if et in {"session_failed", "failed"} or status == "failed":
            failure_kind = str(payload.get("failure_kind") or failure_kind or "other")
        if "loop" in et or "loop_blocked" in et:
            failure_kind = "loop"
            notes.append("loop_block")

    # also scan session metadata / parts
    meta = session.get("metadata") or {}
    ui = meta.get("ui_state") or {}
    timeline = ui.get("timeline") or []
    for item in timeline:
        t = str(item.get("type") or item.get("part_type") or "")
        if "diff" in t:
            diff_visible = 1
        if t in {"tool_call", "tool"}:
            tools_total = max(tools_total, tools_total)  # keep event count primary
        content = json.dumps(item, ensure_ascii=False).lower()
        if "trajectory_guard_blocked" in content:
            trajectory_blocks += 1
        if any(k in content for k in ("pytest", "typecheck", "npm test", "vitest", "eslint")):
            verify_attempted = 1
            if "passed" in content or '"exit_code": 0' in content or "exit_code\":0" in content:
                verify_ok = 1

    if parts:
        for p in parts:
            pt = str(p.get("type") or p.get("part_type") or "")
            if "diff" in pt:
                diff_visible = 1
            if pt in {"tool_call", "tool"}:
                tools_total += 1
            blob = json.dumps(p, ensure_ascii=False).lower()
            if "trajectory_guard" in blob and "block" in blob:
                trajectory_blocks += 1

    # heuristic fallback: count tool_call strings in events dump
    if tools_total == 0:
        blob = json.dumps(events, ensure_ascii=False)
        tools_total = len(re.findall(r'"tool_call"', blob))
        trajectory_blocks = max(trajectory_blocks, blob.count("trajectory_guard_blocked"))
        if "diff" in blob:
            diff_visible = 1
        if any(x in blob for x in ("pytest", "typecheck", "vitest", "npm test")):
            verify_attempted = 1

    # Prefer server Step-1 metadata when present (tool_metrics / completion_gate).
    meta = session.get("metadata") or {}
    server_metrics = meta.get("tool_metrics") if isinstance(meta.get("tool_metrics"), dict) else None
    gate = meta.get("completion_gate") if isinstance(meta.get("completion_gate"), dict) else None
    if server_metrics:
        tools_total = max(tools_total, int(server_metrics.get("tools_total") or 0))
        tools_failed = max(tools_failed, int(server_metrics.get("tools_failed") or 0))
        trajectory_blocks = max(trajectory_blocks, int(server_metrics.get("trajectory_blocks") or 0))
        if int(server_metrics.get("verify_attempted") or 0):
            verify_attempted = 1
        if int(server_metrics.get("verify_ok") or 0):
            verify_ok = 1
        hitl_count = max(hitl_count, int(server_metrics.get("hitl_count") or 0))
        notes.append("metrics:server")

    # completion definition
    completed_ok = 0
    if gate is not None and "completed_ok" in gate:
        completed_ok = 1 if gate.get("completed_ok") else 0
        if gate.get("diff_visible"):
            diff_visible = 1
        if int(gate.get("verify_attempted") or 0):
            verify_attempted = 1
        if int(gate.get("verify_ok") or 0):
            verify_ok = 1
        gaps = gate.get("gaps") or []
        if gaps:
            notes.append("gaps:" + ",".join(str(g) for g in gaps[:6]))
        if gate.get("summary"):
            notes.append("gate:" + str(gate.get("summary"))[:120])
        notes.append("completion_gate:yes")
    elif status == "completed":
        write_scene = True  # coding write expected for C*; T1 may be analysis-only
        if write_scene and (diff_visible or tools_total > 0):
            if diff_visible and verify_ok:
                completed_ok = 1
            elif not diff_visible and verify_ok:
                completed_ok = 0
                notes.append("pattern:no_diff_or_incomplete_completion")
            else:
                notes.append("pattern:no_verify" if not verify_attempted else "verify_failed")
        else:
            completed_ok = 1

    if status == "needs_manual_review":
        failure_kind = failure_kind if failure_kind != "none" else "other"
        notes.append("needs_manual_review")
    if status == "failed" and failure_kind == "none":
        failure_kind = "model"
    if trajectory_blocks > 0:
        notes.append("pattern:write_without_read")

    notes = [n for n in notes if n]
    return {
        "status": status,
        "completed_ok": completed_ok,
        "tools_total": tools_total,
        "tools_failed": tools_failed,
        "trajectory_blocks": trajectory_blocks,
        "verify_attempted": verify_attempted,
        "verify_ok": verify_ok,
        "diff_visible": diff_visible,
        "hitl_count": hitl_count,
        "human_reprompt": 0,
        "failure_kind": failure_kind,
        "notes": "; ".join(notes)[:400],
        "tool_names_sample": tool_names[:20],
        "tool_metrics": server_metrics,
        "completion_gate": gate,
        "working_state": meta.get("working_state") if isinstance(meta.get("working_state"), dict) else None,
    }


def _action_count_for_permission(session: dict, part_id: str, pending: dict | None = None) -> int:
    """How many HITL decisions the platform expects for this permission part."""
    if pending and str(pending.get("part_id") or pending.get("id") or "") == part_id:
        actions = pending.get("actions")
        if isinstance(actions, list) and actions:
            return len(actions)
        for key in ("action_count", "count"):
            if pending.get(key):
                try:
                    return max(1, int(pending[key]))
                except (TypeError, ValueError):
                    pass
    for part in session.get("parts") or []:
        if not isinstance(part, dict) or str(part.get("id") or "") != part_id:
            continue
        payload = part.get("payload") if isinstance(part.get("payload"), dict) else {}
        actions = payload.get("action_requests") or payload.get("actions")
        if isinstance(actions, list) and actions:
            return len(actions)
        for key in ("action_count", "count"):
            if payload.get(key):
                try:
                    return max(1, int(payload[key]))
                except (TypeError, ValueError):
                    pass
    return 1


def approve_permission_part(session: dict, part_id: str, *, action_count: int | None = None) -> bool:
    """Approve a pending permission, sending N decisions when multi-action HITL is required."""
    meta = session.get("metadata") or {}
    ui = meta.get("ui_state") or {}
    pending = ui.get("pending_permission") if isinstance(ui.get("pending_permission"), dict) else None
    n = action_count if action_count is not None else _action_count_for_permission(session, part_id, pending)
    n = max(1, int(n))
    decisions = [{"type": "approve"} for _ in range(n)]
    body = {"decisions": decisions}
    try:
        # Prefer /decide — supports multi-action batches (approve alone always sends 1).
        http_json("POST", f"/agent-permissions/{part_id}/decide", body)
        print(f"  decided approve x{n} for permission {part_id}", flush=True)
        return True
    except Exception as exc_decide:
        if n == 1:
            try:
                http_json("POST", f"/agent-permissions/{part_id}/approve", {})
                print(f"  approved pending permission {part_id}", flush=True)
                return True
            except Exception as exc_approve:
                print(f"  approve failed {part_id}: {exc_approve}", flush=True)
                return False
        print(f"  multi-decide failed {part_id} (n={n}): {exc_decide}", flush=True)
        return False


def approve_pending(session: dict) -> int:
    """Approve only currently pending permission parts (avoid agp_ false positives)."""
    approved = 0
    meta = session.get("metadata") or {}
    ui = meta.get("ui_state") or {}
    pending = ui.get("pending_permission") if isinstance(ui.get("pending_permission"), dict) else None
    candidates: list[tuple[str, int | None]] = []
    if pending:
        pid = pending.get("part_id") or pending.get("id") or pending.get("permission_id")
        if pid:
            candidates.append((str(pid), _action_count_for_permission(session, str(pid), pending)))
    for part in session.get("parts") or []:
        if not isinstance(part, dict):
            continue
        if str(part.get("type") or "") == "permission" and str(part.get("status") or "") == "pending":
            pid = str(part.get("id") or "")
            if pid:
                candidates.append((pid, _action_count_for_permission(session, pid, pending)))

    seen: set[str] = set()
    for pid, n in candidates:
        if not pid or pid in seen:
            continue
        seen.add(pid)
        if approve_permission_part(session, pid, action_count=n):
            approved += 1
    return approved


def run_one(sc: dict[str, Any]) -> dict[str, Any]:
    baseline_id = sc["baseline_id"]
    project = (BASELINE_DIR / sc["dir"]).resolve()
    if not project.is_dir():
        return {
            "baseline_id": baseline_id,
            "session_id": "",
            "status": "skipped",
            "completed_ok": 0,
            "failure_kind": "config",
            "notes": f"missing workspace {project}",
            "duration_min": 0,
        }

    print(f"\n=== {baseline_id} workspace={project.name} mode={sc['task_mode']} ===", flush=True)
    create_body = {
        "agent_id": "build",
        "title": f"baseline-{baseline_id}-{MODEL}",
        "project_path": str(project),
        "task_mode": sc["task_mode"],
        "provider": PROVIDER,
        "model": MODEL,
        "autonomy_mode": AUTONOMY,
    }
    session = http_json("POST", "/agent-sessions", create_body)
    sid = session["id"]
    print(f"  session={sid}", flush=True)

    t0 = time.time()
    http_json(
        "POST",
        f"/agent-sessions/{sid}/prompt",
        {"content": sc["prompt"], "provider": PROVIDER, "model": MODEL},
        timeout=120,
    )

    last_status = "running"
    hitl_total = 0
    stagnant = 0
    last_event_count = 0

    while True:
        elapsed = time.time() - t0
        if elapsed > TIMEOUT_S:
            try:
                http_json("POST", f"/agent-sessions/{sid}/interrupt", {})
            except Exception:
                pass
            session = http_json("GET", f"/agent-sessions/{sid}")
            events = http_json("GET", f"/agent-sessions/{sid}/events") or []
            scored = score_from_session(session, events, session.get("parts"))
            scored.update(
                {
                    "baseline_id": baseline_id,
                    "session_id": sid,
                    "duration_min": round(elapsed / 60, 2),
                    "failure_kind": "timeout",
                    "notes": (scored.get("notes") or "") + "; timeout",
                }
            )
            print(f"  TIMEOUT after {elapsed:.0f}s status={session.get('status')}", flush=True)
            return scored

        session = http_json("GET", f"/agent-sessions/{sid}")
        last_status = str(session.get("status") or "")
        approved = approve_pending(session)
        if approved:
            hitl_total += approved
            print(f"  approved {approved} HITL (total={hitl_total}) status={last_status}", flush=True)

        # also scan events for permission ids
        events = http_json("GET", f"/agent-sessions/{sid}/events") or []
        if len(events) == last_event_count and last_status in {"waiting_permission", "waiting_approval", "running"}:
            stagnant += 1
        else:
            stagnant = 0
            last_event_count = len(events)

        # Only approve part_id from recent permission_asked while waiting.
        if last_status in {"waiting_permission", "waiting_approval"}:
            for ev in events[-8:]:
                if str(ev.get("event_type") or "") != "permission_asked":
                    continue
                payload = ev.get("payload") or {}
                pid = payload.get("part_id")
                if not pid:
                    continue
                n = None
                actions = payload.get("action_requests") or payload.get("actions")
                if isinstance(actions, list) and actions:
                    n = len(actions)
                elif payload.get("action_count"):
                    try:
                        n = int(payload["action_count"])
                    except (TypeError, ValueError):
                        n = None
                if approve_permission_part(session, str(pid), action_count=n):
                    hitl_total += 1

        if last_status in TERMINAL:
            break
        if last_status in {"waiting_permission", "waiting_approval"} and stagnant > 8:
            # stuck HITL
            print(f"  stuck in {last_status}, treating as terminal for scoring", flush=True)
            break

        print(f"  ... {last_status} events={len(events)} t={elapsed:.0f}s", flush=True)
        time.sleep(POLL_S)

    elapsed = time.time() - t0
    session = http_json("GET", f"/agent-sessions/{sid}")
    events = http_json("GET", f"/agent-sessions/{sid}/events") or []
    scored = score_from_session(session, events, session.get("parts"))
    scored["hitl_count"] = max(scored.get("hitl_count") or 0, hitl_total)
    scored.update(
        {
            "baseline_id": baseline_id,
            "session_id": sid,
            "duration_min": round(elapsed / 60, 2),
        }
    )
    # T1 special: analysis ok without verify if completed
    if baseline_id == "T1" and scored["status"] == "completed":
        scored["completed_ok"] = 1
        scored["notes"] = (scored.get("notes") or "") + "; train_propose_only"
    print(
        f"  DONE status={scored['status']} completed_ok={scored['completed_ok']} "
        f"tools={scored['tools_total']} verify={scored['verify_attempted']}/{scored['verify_ok']} "
        f"diff={scored['diff_visible']} hitl={scored['hitl_count']} min={scored['duration_min']}",
        flush=True,
    )
    # persist raw events for audit
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{baseline_id}-{sid}.events.json").write_text(
        json.dumps({"session": session, "events": events}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return scored


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    coding = [r for r in rows if r.get("baseline_id", "").startswith("C")]
    write_rows = coding  # all C* expect writes
    return {
        "N": n,
        "completion_rate": round(sum(r.get("completed_ok") or 0 for r in rows) / n, 3) if n else 0,
        "verify_attempt_rate_coding": round(
            sum(r.get("verify_attempted") or 0 for r in coding) / len(coding), 3
        )
        if coding
        else None,
        "verify_success_rate": round(
            sum(r.get("verify_ok") or 0 for r in rows)
            / max(1, sum(r.get("verify_attempted") or 0 for r in rows)),
            3,
        ),
        "diff_visible_rate": round(
            sum(r.get("diff_visible") or 0 for r in write_rows) / len(write_rows), 3
        )
        if write_rows
        else None,
        "mean_tools_total": round(sum(r.get("tools_total") or 0 for r in rows) / n, 2) if n else 0,
        "trajectory_block_scene_rate": round(
            sum(1 for r in rows if (r.get("trajectory_blocks") or 0) > 0) / n, 3
        )
        if n
        else 0,
        "mean_hitl": round(sum(r.get("hitl_count") or 0 for r in rows) / n, 2) if n else 0,
        "human_reprompt_rate": round(
            sum(1 for r in rows if (r.get("human_reprompt") or 0) > 0) / n, 3
        )
        if n
        else 0,
        "failure_kinds": {},
    }


def to_markdown(meta: dict, rows: list[dict], summary: dict) -> str:
    lines = [
        f"# Agent tool baseline run — {meta['date']}",
        "",
        "## §1 conditions",
        "",
        f"| field | value |",
        f"|------|------|",
        f"| date | {meta['date']} |",
        f"| operator | automated API runner |",
        f"| commit | {meta['commit']} |",
        f"| backend | uvicorn :8010 (this session) |",
        f"| provider/model | {meta['provider']} / {meta['model']} |",
        f"| real model | yes |",
        f"| task_mode | per scenario |",
        f"| autonomy_mode | {meta['autonomy']} (HITL auto-approved by runner) |",
        f"| notes | semi-auto; T2 not run |",
        "",
        "## §5.2 scores",
        "",
        "| baseline_id | session_id | status | completed_ok | tools_total | tools_failed | trajectory_blocks | verify_attempted | verify_ok | diff_visible | hitl_count | human_reprompt | duration_min | failure_kind | notes |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            "| {baseline_id} | {session_id} | {status} | {completed_ok} | {tools_total} | {tools_failed} | {trajectory_blocks} | {verify_attempted} | {verify_ok} | {diff_visible} | {hitl_count} | {human_reprompt} | {duration_min} | {failure_kind} | {notes} |".format(
                baseline_id=r.get("baseline_id", ""),
                session_id=r.get("session_id", ""),
                status=r.get("status", ""),
                completed_ok=r.get("completed_ok", ""),
                tools_total=r.get("tools_total", ""),
                tools_failed=r.get("tools_failed", ""),
                trajectory_blocks=r.get("trajectory_blocks", ""),
                verify_attempted=r.get("verify_attempted", ""),
                verify_ok=r.get("verify_ok", ""),
                diff_visible=r.get("diff_visible", ""),
                hitl_count=r.get("hitl_count", ""),
                human_reprompt=r.get("human_reprompt", 0),
                duration_min=r.get("duration_min", ""),
                failure_kind=r.get("failure_kind", ""),
                notes=str(r.get("notes") or "").replace("|", "/"),
            )
        )
    lines += [
        "",
        "## §5.3 summary",
        "",
        "| metric | value |",
        "|--------|------|",
    ]
    for k, v in summary.items():
        lines.append(f"| {k} | {v} |")
    lines += [
        "",
        "## §5.4 qualitative (auto)",
        "",
        "1. Offline harness (fake model e2e + agent_eval) was green before this live run.",
        "2. Live scores use deepseek-v4-flash via Agent Session API with confirm_all + auto HITL approve.",
        "3. Metrics are event-heuristic; re-check Timeline in Workbench if a row looks wrong.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    only = set(argv[1:]) if len(argv) > 1 else set()
    # default: priority 5 then rest; allow subset like C1 C2
    selected = SCENARIOS
    if only:
        selected = [s for s in SCENARIOS if s["baseline_id"] in only]
        if not selected:
            print(f"No scenarios match {only}", file=sys.stderr)
            return 2

    health = http_json("GET", "/health")
    print("health:", health.get("status"), flush=True)

    # commit
    commit = "unknown"
    try:
        import subprocess

        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        pass

    meta = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "commit": commit,
        "provider": PROVIDER,
        "model": MODEL,
        "autonomy": AUTONOMY,
    }

    rows: list[dict[str, Any]] = []
    for sc in selected:
        try:
            row = run_one(sc)
        except Exception as exc:
            print(f"  ERROR {sc['baseline_id']}: {exc}", flush=True)
            row = {
                "baseline_id": sc["baseline_id"],
                "session_id": "",
                "status": "error",
                "completed_ok": 0,
                "tools_total": 0,
                "tools_failed": 0,
                "trajectory_blocks": 0,
                "verify_attempted": 0,
                "verify_ok": 0,
                "diff_visible": 0,
                "hitl_count": 0,
                "human_reprompt": 0,
                "duration_min": 0,
                "failure_kind": "config",
                "notes": str(exc)[:300],
            }
        rows.append(row)
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "partial.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = summarize(rows)
    # failure kind dist
    fk: dict[str, int] = {}
    for r in rows:
        k = str(r.get("failure_kind") or "none")
        fk[k] = fk.get(k, 0) + 1
    summary["failure_kinds"] = fk

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_json = RESULTS / f"baseline-{stamp}-{MODEL.replace(':', '_')}.json"
    out_md = RESULTS / f"baseline-{stamp}-{MODEL.replace(':', '_')}.md"
    payload = {"meta": meta, "rows": rows, "summary": summary}
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(to_markdown(meta, rows, summary), encoding="utf-8")
    print("\nWrote", out_json)
    print("Wrote", out_md)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

