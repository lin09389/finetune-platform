from __future__ import annotations

from typing import Any, Iterable


DEFAULT_MAX_REPAIR_ATTEMPTS = 1


def normalize_path(path: Any) -> str:
    return str(path).replace("\\", "/")


def ensure_session_state(metadata: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(metadata or {})
    data.setdefault("autonomy_mode", "safe_auto")
    data.setdefault("touched_paths", [])
    data.setdefault("had_context", False)
    data.setdefault("repair_attempts", 0)
    data.setdefault("max_repair_attempts", DEFAULT_MAX_REPAIR_ATTEMPTS)
    data.setdefault("fallback_summary_used", False)

    state = dict(data.get("state") or {})
    state.setdefault("touched_paths", list(data.get("touched_paths") or []))
    state.setdefault("changed_files", list(data.get("changed_files") or []))
    state.setdefault("latest_diff_part_id", data.get("latest_diff_part_id"))
    state.setdefault("latest_command_part_id", data.get("latest_command_part_id"))
    state.setdefault("latest_error", data.get("latest_error") or "")
    state.setdefault("repair_attempts", int(data.get("repair_attempts") or 0))
    state.setdefault("max_repair_attempts", int(data.get("max_repair_attempts") or DEFAULT_MAX_REPAIR_ATTEMPTS))
    state.setdefault("fallback_summary_used", bool(data.get("fallback_summary_used")))
    state.setdefault("current_phase", data.get("current_phase") or "idle")

    data["state"] = state
    return data


def set_phase(metadata: dict[str, Any], phase: str) -> dict[str, Any]:
    state = dict(metadata.get("state") or {})
    state["current_phase"] = phase
    metadata["current_phase"] = phase
    metadata["state"] = state
    return metadata


def add_touched_paths(metadata: dict[str, Any], paths: Iterable[Any]) -> dict[str, Any]:
    touched = {normalize_path(path) for path in metadata.get("touched_paths") or [] if path}
    touched.update(normalize_path(path) for path in paths if path)
    ordered = sorted(touched)
    metadata["touched_paths"] = ordered
    metadata["had_context"] = True
    state = dict(metadata.get("state") or {})
    state["touched_paths"] = ordered
    state["current_phase"] = "inspecting"
    metadata["state"] = state
    metadata["current_phase"] = "inspecting"
    return metadata


def record_diff(metadata: dict[str, Any], part_id: str, changed_files: Iterable[Any] | None = None) -> dict[str, Any]:
    metadata["latest_diff_part_id"] = part_id
    state = dict(metadata.get("state") or {})
    state["latest_diff_part_id"] = part_id
    if changed_files is not None:
        changed = {normalize_path(path) for path in metadata.get("changed_files") or [] if path}
        changed.update(normalize_path(path) for path in changed_files if path)
        ordered = sorted(changed)
        metadata["changed_files"] = ordered
        state["changed_files"] = ordered
    metadata["state"] = state
    return metadata


def record_command(metadata: dict[str, Any], part_id: str, error: str | None = None) -> dict[str, Any]:
    metadata["latest_command_part_id"] = part_id
    state = dict(metadata.get("state") or {})
    state["latest_command_part_id"] = part_id
    if error:
        metadata["latest_error"] = error
        state["latest_error"] = error
    else:
        metadata["latest_error"] = ""
        state["latest_error"] = ""
    metadata["state"] = state
    return metadata


def record_repair_attempt(metadata: dict[str, Any]) -> dict[str, Any]:
    attempts = int(metadata.get("repair_attempts") or 0) + 1
    metadata["repair_attempts"] = attempts
    state = dict(metadata.get("state") or {})
    state["repair_attempts"] = attempts
    state["current_phase"] = "repairing"
    metadata["current_phase"] = "repairing"
    metadata["state"] = state
    return metadata


def record_fallback_summary(metadata: dict[str, Any]) -> dict[str, Any]:
    metadata["fallback_summary_used"] = True
    state = dict(metadata.get("state") or {})
    state["fallback_summary_used"] = True
    state["current_phase"] = "needs_manual_review"
    metadata["current_phase"] = "needs_manual_review"
    metadata["state"] = state
    return metadata
