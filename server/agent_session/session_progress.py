"""Session working-state card, tool metrics, and completion-gate helpers (Step 1).

Pure helpers plus small persistence hooks. Does not own the Agent loop.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

TOOL_METRICS_KEY = "tool_metrics"
COMPLETION_GATE_KEY = "completion_gate"
RECOVERY_STATE_KEY = "recovery_state"
WORKING_STATE_SECTION_TITLE = "## 当前工作状态（平台注入）"

# Step 2 exploration budget (per prompt run; reset with tool_metrics).
SOFT_TOOL_BUDGET = 40
HARD_TOOL_BUDGET = 80
SOFT_OBSERVE_BUDGET = 24
HARD_OBSERVE_BUDGET = 40
_OBSERVE_TOOLS = frozenset({"ls", "glob", "grep", "read_file"})

_MAX_PATHS = 10
_MAX_TOOL_NAME_BUCKETS = 24
_REQUIRED_SUMMARY_SECTIONS = ("已完成项", "变更文件", "验证结果")

_VERIFY_HINTS = (
    "pytest",
    "unittest",
    "typecheck",
    "tsc",
    "eslint",
    "lint",
    "vitest",
    "npm test",
    "npm run test",
    "npm run typecheck",
    "py_compile",
    "node --check",
    "ruff",
    "mypy",
)


def empty_tool_metrics() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "tools_total": 0,
        "tools_failed": 0,
        "trajectory_blocks": 0,
        "verify_attempted": 0,
        "verify_ok": 0,
        "hitl_count": 0,
        "observe_total": 0,
        "by_tool": {},
        "last_tool": None,
        "last_failure_tool": None,
        "budget_soft_warned": False,
        "budget_hard_blocked": False,
        "updated_at": None,
    }


def empty_recovery_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "require_observation_before_retry": False,
        "last_failed_execute": None,
        "blind_retry_blocks": 0,
        "updated_at": None,
    }


def normalize_command(command: str | None) -> str:
    raw = " ".join(str(command or "").strip().split())
    return raw


def reset_tool_metrics(metadata: dict[str, Any]) -> dict[str, Any]:
    next_metadata = dict(metadata)
    next_metadata[TOOL_METRICS_KEY] = empty_tool_metrics()
    next_metadata[RECOVERY_STATE_KEY] = empty_recovery_state()
    # Drop stale completion gate at the start of a new prompt run.
    next_metadata.pop(COMPLETION_GATE_KEY, None)
    return next_metadata


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _tool_name(event: dict[str, Any]) -> str:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    for key in ("tool", "name", "tool_name"):
        value = payload.get(key)
        if value:
            return str(value)
    part = payload.get("part") if isinstance(payload.get("part"), dict) else {}
    part_payload = part.get("payload") if isinstance(part.get("payload"), dict) else {}
    if part_payload.get("tool"):
        return str(part_payload["tool"])
    if part.get("title"):
        return str(part["title"])
    return ""


def _looks_like_verification(tool: str, event: dict[str, Any]) -> bool:
    tool_l = (tool or "").lower()
    if tool_l not in {"execute", "bash", "shell"}:
        return False
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    blob_parts = [
        str(payload.get("command") or ""),
        str(payload.get("summary") or ""),
        str(event.get("message") or ""),
    ]
    part = payload.get("part") if isinstance(payload.get("part"), dict) else {}
    if isinstance(part.get("payload"), dict):
        inp = part["payload"].get("input")
        if isinstance(inp, dict):
            blob_parts.append(str(inp.get("command") or ""))
        else:
            blob_parts.append(str(inp or ""))
        blob_parts.append(str(part.get("content") or ""))
    # trajectory step
    step = payload.get("step") if isinstance(payload.get("step"), dict) else {}
    if str(step.get("kind") or "") == "verification":
        return True
    blob_parts.append(str(step.get("command") or ""))
    blob = " ".join(blob_parts).lower()
    return any(hint in blob for hint in _VERIFY_HINTS)


def apply_tool_event(metrics: dict[str, Any], event: dict[str, Any]) -> dict[str, Any] | None:
    """Return updated metrics dict, or None if the event is irrelevant."""
    event_type = str(event.get("event_type") or "")
    if not event_type:
        return None

    current = dict(metrics or empty_tool_metrics())
    by_tool = dict(current.get("by_tool") or {})
    tool = _tool_name(event)
    changed = False

    if event_type == "tool_call_started":
        current["tools_total"] = int(current.get("tools_total") or 0) + 1
        if tool:
            bucket = dict(by_tool.get(tool) or {"calls": 0, "failed": 0})
            bucket["calls"] = int(bucket.get("calls") or 0) + 1
            by_tool[tool] = bucket
            current["last_tool"] = tool
            if tool in _OBSERVE_TOOLS:
                current["observe_total"] = int(current.get("observe_total") or 0) + 1
        changed = True
    elif event_type == "tool_call_failed":
        current["tools_failed"] = int(current.get("tools_failed") or 0) + 1
        if tool:
            bucket = dict(by_tool.get(tool) or {"calls": 0, "failed": 0})
            bucket["failed"] = int(bucket.get("failed") or 0) + 1
            # started may have been missed in some paths
            if int(bucket.get("calls") or 0) < int(bucket.get("failed") or 0):
                bucket["calls"] = int(bucket.get("failed") or 0)
            by_tool[tool] = bucket
            current["last_failure_tool"] = tool
            current["last_tool"] = tool
        if _looks_like_verification(tool, event):
            current["verify_attempted"] = 1
        changed = True
    elif event_type == "tool_call_completed":
        if tool:
            current["last_tool"] = tool
        if _looks_like_verification(tool, event):
            current["verify_attempted"] = 1
            current["verify_ok"] = 1
        changed = True
    elif event_type == "trajectory_guard_blocked":
        current["trajectory_blocks"] = int(current.get("trajectory_blocks") or 0) + 1
        changed = True
    elif event_type == "trajectory_step_recorded":
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        step = payload.get("step") if isinstance(payload.get("step"), dict) else {}
        if str(step.get("kind") or "") == "verification":
            current["verify_attempted"] = 1
            if step.get("success"):
                current["verify_ok"] = 1
            changed = True
    elif event_type in {
        "permission_asked",
        "permission_requested",
        "deepagents_interrupt",
        "waiting_permission",
    }:
        current["hitl_count"] = int(current.get("hitl_count") or 0) + 1
        changed = True

    if not changed:
        return None

    # Cap by_tool map size
    if len(by_tool) > _MAX_TOOL_NAME_BUCKETS:
        # keep highest-call tools
        ranked = sorted(by_tool.items(), key=lambda item: int((item[1] or {}).get("calls") or 0), reverse=True)
        by_tool = dict(ranked[:_MAX_TOOL_NAME_BUCKETS])
    current["by_tool"] = by_tool
    current["updated_at"] = _now_iso()
    current["schema_version"] = 1
    return current


def observe_and_persist_tool_metrics(repository: Any, session_id: str, event: dict[str, Any]) -> dict[str, Any] | None:
    """Update session metadata.tool_metrics from a published event. Returns metrics if updated."""
    session = repository.get_session(session_id)
    if not session:
        return None
    metadata = dict(session.get("metadata") or {})
    current = dict(metadata.get(TOOL_METRICS_KEY) or empty_tool_metrics())
    if apply_tool_event(current, event) is None:
        # Still process recovery_state from failures / successful observations.
        if not _event_touches_recovery(event):
            return None
    # Re-read after failure_guard (called just before us) so we do not clobber loop_guard.
    session = repository.get_session(session_id) or session
    metadata = dict(session.get("metadata") or {})
    latest = dict(metadata.get(TOOL_METRICS_KEY) or empty_tool_metrics())
    updated = apply_tool_event(latest, event)
    if updated is not None:
        metadata[TOOL_METRICS_KEY] = updated
    metadata = apply_recovery_event(metadata, event)
    # Keep a compact public working-state snapshot for UI without re-scanning events.
    metadata["working_state"] = build_working_state_snapshot(metadata)
    repository.update_session(session_id, metadata=metadata)
    return metadata.get(TOOL_METRICS_KEY) if isinstance(metadata.get(TOOL_METRICS_KEY), dict) else updated


def _event_touches_recovery(event: dict[str, Any]) -> bool:
    event_type = str(event.get("event_type") or "")
    tool = _tool_name(event)
    if event_type == "tool_call_failed" and tool in {"execute", "bash", "shell"}:
        return True
    if event_type == "tool_call_completed" and tool in _OBSERVE_TOOLS:
        return True
    if event_type == "tool_call_completed" and tool in {"execute", "bash", "shell"}:
        return True
    return False


def _command_from_event(event: dict[str, Any]) -> str:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    if payload.get("command"):
        return normalize_command(str(payload.get("command")))
    part = payload.get("part") if isinstance(payload.get("part"), dict) else {}
    part_payload = part.get("payload") if isinstance(part.get("payload"), dict) else {}
    inp = part_payload.get("input")
    if isinstance(inp, dict):
        return normalize_command(str(inp.get("command") or ""))
    return normalize_command(str(inp or ""))


def apply_recovery_event(metadata: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    """Update recovery_state: failed execute requires observation before same command retry."""
    next_metadata = dict(metadata)
    recovery = dict(next_metadata.get(RECOVERY_STATE_KEY) or empty_recovery_state())
    event_type = str(event.get("event_type") or "")
    tool = _tool_name(event)
    if event_type == "tool_call_failed" and tool in {"execute", "bash", "shell"}:
        command = _command_from_event(event)
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        error = str(payload.get("error") or payload.get("summary") or event.get("message") or "")[:400]
        recovery["require_observation_before_retry"] = True
        recovery["last_failed_execute"] = {
            "command": command,
            "error_excerpt": error,
            "tool": tool,
        }
        recovery["updated_at"] = _now_iso()
        next_metadata[RECOVERY_STATE_KEY] = recovery
        return next_metadata
    if event_type == "tool_call_completed" and tool in _OBSERVE_TOOLS:
        if recovery.get("require_observation_before_retry"):
            recovery["require_observation_before_retry"] = False
            recovery["cleared_by"] = tool
            recovery["updated_at"] = _now_iso()
            next_metadata[RECOVERY_STATE_KEY] = recovery
        return next_metadata
    if event_type == "tool_call_completed" and tool in {"execute", "bash", "shell"}:
        # Successful different command also clears the latch.
        command = _command_from_event(event)
        last = recovery.get("last_failed_execute") if isinstance(recovery.get("last_failed_execute"), dict) else {}
        if last and normalize_command(str(last.get("command") or "")) != command:
            recovery["require_observation_before_retry"] = False
            recovery["cleared_by"] = "different_execute"
            recovery["updated_at"] = _now_iso()
            next_metadata[RECOVERY_STATE_KEY] = recovery
        elif not last:
            recovery["require_observation_before_retry"] = False
            recovery["updated_at"] = _now_iso()
            next_metadata[RECOVERY_STATE_KEY] = recovery
        return next_metadata
    return next_metadata


def evaluate_execute_blind_retry(metadata: dict[str, Any] | None, command: str) -> dict[str, Any] | None:
    """Return a block payload if the same failed execute is retried without observation."""
    meta = dict(metadata or {})
    recovery = meta.get(RECOVERY_STATE_KEY) if isinstance(meta.get(RECOVERY_STATE_KEY), dict) else {}
    if not recovery.get("require_observation_before_retry"):
        return None
    last = recovery.get("last_failed_execute") if isinstance(recovery.get("last_failed_execute"), dict) else {}
    last_cmd = normalize_command(str(last.get("command") or ""))
    this_cmd = normalize_command(command)
    if not last_cmd or last_cmd != this_cmd:
        return None
    return {
        "reason_code": "blind_execute_retry",
        "message": (
            "已阻止盲目重试相同的失败命令。"
            f"上次 execute 失败：`{last_cmd[:200]}`。"
            "请先用 read_file/grep 查看真实错误与源码，修改后再用不同或修复后的验证命令重试。"
            f"错误摘要：{str(last.get('error_excerpt') or '')[:200]}"
        ),
        "command": this_cmd,
    }


def evaluate_exploration_budget(metadata: dict[str, Any] | None, *, tool: str) -> dict[str, Any] | None:
    """Return soft warning or hard block decision for exploration budget."""
    meta = dict(metadata or {})
    metrics = dict(meta.get(TOOL_METRICS_KEY) or empty_tool_metrics())
    total = int(metrics.get("tools_total") or 0)
    observe = int(metrics.get("observe_total") or 0)
    # +1 for the tool about to run
    total_next = total + 1
    observe_next = observe + (1 if tool in _OBSERVE_TOOLS else 0)
    if total_next >= HARD_TOOL_BUDGET or observe_next >= HARD_OBSERVE_BUDGET:
        return {
            "level": "hard",
            "reason_code": "exploration_budget_exhausted",
            "message": (
                f"探索预算已耗尽（工具 {total_next}/{HARD_TOOL_BUDGET}，"
                f"只读探索 {observe_next}/{HARD_OBSERVE_BUDGET}）。"
                "请停止继续 ls/glob/grep 扫描；基于已有信息完成修改与验证，或输出收尾摘要。"
            ),
            "tools_total": total_next,
            "observe_total": observe_next,
        }
    if (total_next >= SOFT_TOOL_BUDGET or observe_next >= SOFT_OBSERVE_BUDGET) and not metrics.get(
        "budget_soft_warned"
    ):
        return {
            "level": "soft",
            "reason_code": "exploration_budget_warning",
            "message": (
                f"探索预算接近上限（工具 {total_next}/{SOFT_TOOL_BUDGET} soft，"
                f"硬上限 {HARD_TOOL_BUDGET}）。请收敛到具体文件修改与验证，避免继续大范围搜索。"
            ),
            "tools_total": total_next,
            "observe_total": observe_next,
        }
    return None


def mark_budget_soft_warned(metadata: dict[str, Any]) -> dict[str, Any]:
    next_metadata = dict(metadata)
    metrics = dict(next_metadata.get(TOOL_METRICS_KEY) or empty_tool_metrics())
    metrics["budget_soft_warned"] = True
    metrics["updated_at"] = _now_iso()
    next_metadata[TOOL_METRICS_KEY] = metrics
    return next_metadata


def mark_budget_hard_blocked(metadata: dict[str, Any]) -> dict[str, Any]:
    next_metadata = dict(metadata)
    metrics = dict(next_metadata.get(TOOL_METRICS_KEY) or empty_tool_metrics())
    metrics["budget_hard_blocked"] = True
    metrics["updated_at"] = _now_iso()
    next_metadata[TOOL_METRICS_KEY] = metrics
    return next_metadata


def mark_blind_retry_blocked(metadata: dict[str, Any]) -> dict[str, Any]:
    next_metadata = dict(metadata)
    recovery = dict(next_metadata.get(RECOVERY_STATE_KEY) or empty_recovery_state())
    recovery["blind_retry_blocks"] = int(recovery.get("blind_retry_blocks") or 0) + 1
    recovery["updated_at"] = _now_iso()
    next_metadata[RECOVERY_STATE_KEY] = recovery
    return next_metadata


def enrich_final_summary(content: str | None, metadata: dict[str, Any] | None, *, status: str = "completed") -> str:
    """Ensure final summary includes required sections and completion-gate facts."""
    text = str(content or "").strip() or "任务已结束。"
    meta = dict(metadata or {})
    gate = build_completion_gate(meta, status=status)
    missing = [section for section in _REQUIRED_SUMMARY_SECTIONS if section not in text]
    written = list(gate.get("written_paths") or [])
    verify_line = (
        "验证通过"
        if gate.get("verify_ok")
        else ("已尝试验证但未通过" if gate.get("verify_attempted") else "未执行验证")
    )
    if not missing and gate.get("completed_ok"):
        # Still append a compact gate stamp when not already present.
        if "平台完成核对" not in text:
            text = (
                f"{text}\n\n## 平台完成核对\n"
                f"- completed_ok: true\n"
                f"- {gate.get('summary') or verify_line}"
            )
        return text

    appendix_lines = ["", "## 平台完成核对"]
    if missing:
        appendix_lines.append(f"- 摘要缺少章节：{', '.join(missing)}（已由平台补全事实）")
    appendix_lines.append("### 已完成项")
    if gate.get("completed_ok"):
        appendix_lines.append("- 完成定义已满足（有写则 diff+验证通过，或无写盘分析任务）")
    else:
        gaps = ", ".join(str(g) for g in (gate.get("gaps") or [])) or "见下方"
        appendix_lines.append(f"- 完成定义未完全满足：{gaps}")
    appendix_lines.append("### 变更文件")
    if written:
        for path in written[:12]:
            appendix_lines.append(f"- `{path}`")
    else:
        appendix_lines.append("- （无源码写入）")
    appendix_lines.append("### 验证结果")
    appendix_lines.append(f"- {verify_line}")
    if gate.get("diff_visible") is False and gate.get("has_writes"):
        appendix_lines.append("- diff：缺失可审 diff")
    elif gate.get("has_writes"):
        appendix_lines.append("- diff：可见")
    appendix_lines.append(f"- 汇总：{gate.get('summary') or ''}")
    return text.rstrip() + "\n" + "\n".join(appendix_lines)


def _list_paths(values: Any, *, limit: int = _MAX_PATHS) -> list[str]:
    if isinstance(values, dict):
        items = [str(key) for key in values.keys() if str(key).strip()]
    elif isinstance(values, list):
        items = [str(item) for item in values if str(item).strip()]
    else:
        items = []
    # de-dupe preserve order
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered[:limit]


def _trajectory_public(metadata: dict[str, Any]) -> dict[str, Any]:
    guard = metadata.get("trajectory_guard")
    if not isinstance(guard, dict):
        return {}
    # Prefer full store; fall back to public fields if already summarized.
    if "writes" in guard or "reads" in guard:
        return {
            "read_paths": _list_paths(guard.get("reads") or guard.get("read_paths")),
            "written_paths": _list_paths(guard.get("writes") or guard.get("written_paths")),
            "verified_paths": _list_paths(guard.get("verified_paths")),
            "reread_required": _list_paths(guard.get("reread_required")),
            "successful_write_sequences": list(guard.get("successful_write_sequences") or []),
            "diff_write_sequences": list(guard.get("diff_write_sequences") or []),
            "violation_count": len(guard.get("violations") or [])
            if isinstance(guard.get("violations"), list)
            else int(guard.get("violation_count") or 0),
            "last_block_reason": guard.get("last_block_reason"),
            "auto_corrections": int(guard.get("auto_corrections") or 0),
            "last_verification_sequence": int(guard.get("last_verification_sequence") or 0),
            "last_write_sequence": int(guard.get("last_write_sequence") or 0),
        }
    return {
        "read_paths": _list_paths(guard.get("read_paths")),
        "written_paths": _list_paths(guard.get("written_paths")),
        "verified_paths": _list_paths(guard.get("verified_paths")),
        "reread_required": _list_paths(guard.get("reread_required")),
        "successful_write_sequences": list(guard.get("successful_write_sequences") or []),
        "diff_write_sequences": list(guard.get("diff_write_sequences") or []),
        "violation_count": int(guard.get("violation_count") or 0),
        "last_block_reason": guard.get("last_block_reason"),
        "auto_corrections": int(guard.get("auto_corrections") or 0),
        "last_verification_sequence": 0,
        "last_write_sequence": 0,
    }


def build_working_state_snapshot(metadata: dict[str, Any]) -> dict[str, Any]:
    traj = _trajectory_public(metadata)
    metrics = dict(metadata.get(TOOL_METRICS_KEY) or empty_tool_metrics())
    written = list(traj.get("written_paths") or [])
    verified = set(traj.get("verified_paths") or [])
    verify_ok = bool(metrics.get("verify_ok")) or (
        bool(written) and bool(verified) and set(written).issubset(verified)
    ) or int(traj.get("last_verification_sequence") or 0) > int(traj.get("last_write_sequence") or 0)
    verify_attempted = bool(metrics.get("verify_attempted")) or bool(verified) or verify_ok
    recovery = (
        metadata.get(RECOVERY_STATE_KEY)
        if isinstance(metadata.get(RECOVERY_STATE_KEY), dict)
        else {}
    )
    last_failed = recovery.get("last_failed_execute") if isinstance(recovery.get("last_failed_execute"), dict) else {}
    return {
        "schema_version": 1,
        "read_paths": list(traj.get("read_paths") or []),
        "written_paths": written,
        "verified_paths": list(traj.get("verified_paths") or []),
        "reread_required": list(traj.get("reread_required") or []),
        "trajectory_blocks": int(metrics.get("trajectory_blocks") or 0)
        or int(traj.get("violation_count") or 0),
        "last_block_reason": traj.get("last_block_reason"),
        "tools_total": int(metrics.get("tools_total") or 0),
        "tools_failed": int(metrics.get("tools_failed") or 0),
        "observe_total": int(metrics.get("observe_total") or 0),
        "verify_attempted": 1 if verify_attempted else 0,
        "verify_ok": 1 if verify_ok else 0,
        "hitl_count": int(metrics.get("hitl_count") or 0),
        "require_observation_before_retry": bool(recovery.get("require_observation_before_retry")),
        "last_failed_command": last_failed.get("command"),
        "budget_soft_warned": bool(metrics.get("budget_soft_warned")),
        "budget_hard_blocked": bool(metrics.get("budget_hard_blocked")),
        "updated_at": metrics.get("updated_at") or _now_iso(),
    }


def build_working_state_card(metadata: dict[str, Any] | None) -> str:
    """Compact Chinese status card for system-prompt injection."""
    meta = dict(metadata or {})
    snap = build_working_state_snapshot(meta)
    has_signal = any(
        [
            snap.get("read_paths"),
            snap.get("written_paths"),
            snap.get("tools_total"),
            snap.get("trajectory_blocks"),
            snap.get("reread_required"),
            snap.get("verify_attempted"),
            snap.get("require_observation_before_retry"),
            snap.get("budget_soft_warned"),
            snap.get("budget_hard_blocked"),
        ]
    )
    if not has_signal:
        return ""

    def fmt_paths(paths: list[str]) -> str:
        if not paths:
            return "（无）"
        shown = paths[:_MAX_PATHS]
        extra = len(paths) - len(shown)
        text = "、".join(f"`{p}`" for p in shown)
        if extra > 0:
            text += f" 等{len(paths)}个"
        return text

    verify_line = "未执行"
    if snap.get("verify_ok"):
        verify_line = "已成功"
    elif snap.get("verify_attempted"):
        verify_line = "已尝试但未成功 — 必须修复后重新验证"

    lines = [
        WORKING_STATE_SECTION_TITLE,
        "这是平台根据本轮真实工具轨迹生成的状态卡。你必须基于它行动，禁止忽略未完成项。",
        f"- 已读文件：{fmt_paths(list(snap.get('read_paths') or []))}",
        f"- 已写文件：{fmt_paths(list(snap.get('written_paths') or []))}",
        f"- 验证状态：{verify_line}",
        f"- 工具计数：共 {int(snap.get('tools_total') or 0)} 次，失败 {int(snap.get('tools_failed') or 0)} 次"
        f"（只读探索 {int(snap.get('observe_total') or 0)} 次）",
        f"- 轨迹拦截：{int(snap.get('trajectory_blocks') or 0)} 次"
        + (f"（{snap.get('last_block_reason')}）" if snap.get("last_block_reason") else ""),
        f"- 探索预算：soft {SOFT_TOOL_BUDGET} / hard {HARD_TOOL_BUDGET}"
        + ("；已触发 soft 警告" if snap.get("budget_soft_warned") else "")
        + ("；已 hard 阻断" if snap.get("budget_hard_blocked") else ""),
    ]
    # Phase B0: surface task scope + verify recipe hints when present.
    scope = meta.get("task_scope") if isinstance(meta.get("task_scope"), dict) else None
    if scope and (scope.get("paths") or scope.get("notes")):
        scope_paths = [str(p) for p in (scope.get("paths") or []) if str(p).strip()]
        lines.append(
            "- 任务范围 Scope："
            + ("、".join(f"`{p}`" for p in scope_paths[:8]) if scope_paths else "（仅备注）")
            + ("；写入范围外会被拦截" if scope_paths else "")
        )
    recipe = meta.get("verify_recipe") if isinstance(meta.get("verify_recipe"), dict) else None
    if recipe and recipe.get("commands"):
        cmds = [str(c) for c in (recipe.get("commands") or []) if str(c).strip()][:4]
        if cmds:
            lines.append("- 验证菜谱命令：" + "；".join(f"`{c}`" for c in cmds))
    if snap.get("require_observation_before_retry"):
        cmd = str(snap.get("last_failed_command") or "")[:160]
        lines.append(
            f"- **失败恢复门闩**：上次 execute 失败（`{cmd}`）。"
            "禁止原样重试同一命令；先 read_file/grep 查清错误再改。"
        )
    reread = list(snap.get("reread_required") or [])
    if reread:
        lines.append(f"- 再次修改前必须重新读取：{fmt_paths(reread)}")
    todos: list[str] = []
    if snap.get("written_paths") and not snap.get("verify_ok"):
        todos.append("对已写源码运行并通过测试/类型检查/lint 或语法检查")
    if reread:
        todos.append("先 read 再 edit，不要重复提交相同失败写入")
    if snap.get("require_observation_before_retry") or int(snap.get("tools_failed") or 0) > 0:
        todos.append("失败后先检查真实错误输出，禁止盲目重试同一命令")
    if int(snap.get("tools_total") or 0) >= SOFT_TOOL_BUDGET:
        todos.append("停止大范围探索，聚焦修改与验证后收尾")
    if todos:
        lines.append("- 尚未完成：")
        for item in todos:
            lines.append(f"  - {item}")
    lines.append(
        "收尾前自检：有源码写入则必须 diff 可审且验证成功；摘要需含 已完成项 / 变更文件 / 验证结果。"
    )
    return "\n".join(lines)


def build_completion_gate(metadata: dict[str, Any] | None, *, status: str | None = None) -> dict[str, Any]:
    """Protocol-aligned completion gate for Attention + metadata."""
    meta = dict(metadata or {})
    traj = _trajectory_public(meta)
    metrics = dict(meta.get(TOOL_METRICS_KEY) or empty_tool_metrics())
    written = list(traj.get("written_paths") or [])
    has_writes = bool(written) or bool(traj.get("successful_write_sequences"))
    successful_writes = set(int(x) for x in (traj.get("successful_write_sequences") or []) if str(x).strip() != "")
    diff_sequences = set(int(x) for x in (traj.get("diff_write_sequences") or []) if str(x).strip() != "")
    diff_visible = (not has_writes) or (bool(successful_writes) and successful_writes.issubset(diff_sequences)) or (
        bool(successful_writes) and bool(diff_sequences)
    )
    # If no successful_write_sequences tracked but written_paths exist, treat missing diff as gap.
    if has_writes and not successful_writes and not diff_sequences:
        # Fall back: look for coding diff parts is not available here; mark unknown via written only.
        # Prefer requiring verification; diff may still be missing.
        diff_visible = False if has_writes else True

    verified_paths = set(traj.get("verified_paths") or [])
    verify_ok = bool(metrics.get("verify_ok")) or (
        bool(written) and set(written).issubset(verified_paths) and bool(written)
    ) or int(traj.get("last_verification_sequence") or 0) > int(traj.get("last_write_sequence") or 0)
    verify_attempted = bool(metrics.get("verify_attempted")) or bool(verified_paths) or verify_ok

    gaps: list[str] = []
    if has_writes and not diff_visible:
        gaps.append("diff_coverage_required")
    if has_writes and not verify_ok:
        gaps.append("verification_required" if verify_attempted else "verification_missing")

    # analysis-only: no writes → ok if terminal completed
    completed_ok = False
    if status == "completed":
        if not has_writes:
            completed_ok = True
        else:
            completed_ok = diff_visible and verify_ok
    elif status == "needs_manual_review":
        completed_ok = False
        if not gaps:
            gaps.append("manual_review")

    summary_bits: list[str] = []
    if not has_writes:
        summary_bits.append("无源码写入")
    else:
        summary_bits.append(f"已写 {len(written)} 个路径")
        summary_bits.append("diff 可见" if diff_visible else "缺少可审 diff")
        if verify_ok:
            summary_bits.append("验证通过")
        elif verify_attempted:
            summary_bits.append("验证未通过")
        else:
            summary_bits.append("未验证")
    if gaps:
        summary_bits.append("缺口: " + ",".join(gaps))

    return {
        "schema_version": 1,
        "status": status,
        "completed_ok": bool(completed_ok),
        "has_writes": has_writes,
        "diff_visible": bool(diff_visible) if has_writes else True,
        "verify_attempted": 1 if verify_attempted else 0,
        "verify_ok": 1 if verify_ok else 0,
        "written_paths": written,
        "verified_paths": list(verified_paths),
        "gaps": gaps,
        "tools_total": int(metrics.get("tools_total") or 0),
        "tools_failed": int(metrics.get("tools_failed") or 0),
        "trajectory_blocks": int(metrics.get("trajectory_blocks") or 0)
        or int(traj.get("violation_count") or 0),
        "summary": "；".join(summary_bits),
        "updated_at": _now_iso(),
    }


def attach_completion_gate(metadata: dict[str, Any], *, status: str | None = None) -> dict[str, Any]:
    next_metadata = dict(metadata)
    next_metadata[COMPLETION_GATE_KEY] = build_completion_gate(next_metadata, status=status)
    next_metadata["working_state"] = build_working_state_snapshot(next_metadata)
    return next_metadata


__all__ = [
    "COMPLETION_GATE_KEY",
    "HARD_OBSERVE_BUDGET",
    "HARD_TOOL_BUDGET",
    "RECOVERY_STATE_KEY",
    "SOFT_OBSERVE_BUDGET",
    "SOFT_TOOL_BUDGET",
    "TOOL_METRICS_KEY",
    "WORKING_STATE_SECTION_TITLE",
    "apply_recovery_event",
    "apply_tool_event",
    "attach_completion_gate",
    "build_completion_gate",
    "build_working_state_card",
    "build_working_state_snapshot",
    "empty_recovery_state",
    "empty_tool_metrics",
    "enrich_final_summary",
    "evaluate_execute_blind_retry",
    "evaluate_exploration_budget",
    "mark_blind_retry_blocked",
    "mark_budget_hard_blocked",
    "mark_budget_soft_warned",
    "normalize_command",
    "observe_and_persist_tool_metrics",
    "reset_tool_metrics",
]
