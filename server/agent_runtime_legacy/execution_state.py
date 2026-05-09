"""Shared execution-state helpers for chat-first agent runs."""

from __future__ import annotations

from typing import Any


CREATED = "created"
PLANNING = "planning"
INSPECTING = "inspecting"
PROPOSING_PATCH = "proposing_patch"
WAITING_PERMISSION = "waiting_permission"
WAITING_APPROVAL = "waiting_approval"
APPLYING_PATCH = "applying_patch"
VERIFYING = "verifying"
REPAIRING = "repairing"
COMPLETED = "completed"
NEEDS_MANUAL_REVIEW = "needs_manual_review"
FAILED = "failed"


TOOL_STATE_MAP = {
    "inspect_project": INSPECTING,
    "list_files": INSPECTING,
    "search_code": INSPECTING,
    "read_file": INSPECTING,
    "detect_project_commands": INSPECTING,
    "get_git_status": INSPECTING,
    "get_git_diff": INSPECTING,
    "list_changed_files": INSPECTING,
    "read_execution_result": VERIFYING,
    "read_test_failures": VERIFYING,
    "propose_patch": PROPOSING_PATCH,
    "propose_command": VERIFYING,
    "finalize": COMPLETED,
}


def state_for_tool(tool_name: str) -> str:
    return TOOL_STATE_MAP.get(tool_name, PLANNING)


def set_workflow_state(
    repository: Any,
    project: dict[str, Any],
    state: str,
    message: str,
    *,
    step_id: str | None = None,
    actor: str = "system",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist a lightweight execution state in workflow metadata and timeline."""

    metadata = dict(project.get("metadata") or {})
    previous = metadata.get("execution_state")
    metadata["execution_state"] = state
    metadata["execution_state_message"] = message
    if extra:
        metadata.update(extra)
    repository.update_project(project["id"], metadata=metadata)
    project["metadata"] = metadata
    if previous != state:
        repository.add_event(
            project["id"],
            step_id,
            "agent_state_changed",
            actor,
            message,
            {"state": state, "previous_state": previous, **(extra or {})},
        )
    return metadata
