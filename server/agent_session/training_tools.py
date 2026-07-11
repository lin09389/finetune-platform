"""Safe, session-scoped DeepAgents tools for the existing training service."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from agent_training.errors import AgentTrainingError
from agent_training.models import ApprovedTrainingAction, TrainingProposalRequest, training_activity_for
from agent_training.service import AgentTrainingService
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from training_engine.schemas import TrainingConfigInput

TRAINING_TOOL_NAMES = frozenset({"propose_training", "submit_training", "get_training_summary"})
_ABSOLUTE_PATH_RE = re.compile(r"(?<!\w)(?:[A-Za-z]:[\\/]|/)[^\s,;\]\)}]+")


class ProposeTrainingInput(BaseModel):
    training_config: dict[str, Any] = Field(description="The requested training configuration.")
    use_queue: bool = Field(default=False, description="Whether to submit through the existing training queue.")
    priority: Literal["urgent", "high", "normal", "low"] = Field(default="normal", description="Requested queue priority.")


class SubmitTrainingInput(BaseModel):
    proposal_id: str = Field(description="The exact proposal_id returned by propose_training.")


class GetTrainingSummaryInput(BaseModel):
    task_id: str = Field(description="The exact task_id returned after an approved submission.")


def training_tools_enabled_for_session(session: dict[str, Any]) -> bool:
    """Return whether the session is explicitly allowed to access training tools."""

    metadata = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
    task_mode = session.get("task_mode") or metadata.get("task_mode")
    return str(session.get("agent_id") or "build") == "build" and task_mode in {"train", "hybrid"}


def training_submission_interrupt_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Force submission through DeepAgents HITL while preserving existing tool policy."""

    updated = dict(metadata or {})
    current = updated.get("deepagents_interrupt_on")
    if current is True:
        interrupt_on: dict[str, Any] = {
            "write_file": True,
            "edit_file": True,
            "execute": True,
        }
    elif isinstance(current, dict):
        interrupt_on = dict(current)
    else:
        interrupt_on = {}
    interrupt_on["submit_training"] = True
    updated["deepagents_interrupt_on"] = interrupt_on
    return updated


def grant_approved_training_submissions(
    repository: Any,
    permission_part: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> None:
    """Persist one-time grants only after an official approval response.

    This is deliberately called by the existing approval service, not by the
    LLM-facing tool.  The tool can only consume a matching grant.
    """

    payload = permission_part.get("payload") if isinstance(permission_part.get("payload"), dict) else {}
    if not payload.get("official_hitl"):
        return
    action_requests = payload.get("action_requests") if isinstance(payload.get("action_requests"), list) else []
    session_id = str(permission_part.get("session_id") or "")
    if not session_id:
        return
    proposal_ids = [
        str(action.get("args", {}).get("proposal_id") or "").strip()
        for action, decision in zip(action_requests, decisions, strict=False)
        if isinstance(action, dict)
        and str(action.get("name") or "") == "submit_training"
        and isinstance(decision, dict)
        and decision.get("type") == "approve"
    ]
    proposal_ids = [proposal_id for proposal_id in proposal_ids if proposal_id]
    if not proposal_ids:
        return
    session = repository.get_session(session_id) or {}
    if not training_tools_enabled_for_session(session):
        return
    metadata = dict(session.get("metadata") or {})
    grants = metadata.get("approved_training_submissions")
    grants = list(grants) if isinstance(grants, list) else []
    permission_part_id = str(permission_part.get("id") or "")
    for proposal_id in proposal_ids:
        grants.append({"proposal_id": proposal_id, "permission_part_id": permission_part_id})
    metadata["approved_training_submissions"] = grants
    repository.update_session(session_id, metadata=metadata)


def consume_training_submission_grant(repository: Any, session_id: str, proposal_id: str) -> bool:
    """Consume exactly one matching official approval before calling training."""

    session = repository.get_session(session_id) or {}
    if not training_tools_enabled_for_session(session):
        return False
    metadata = dict(session.get("metadata") or {})
    grants = metadata.get("approved_training_submissions")
    if not isinstance(grants, list):
        return False
    index = next(
        (
            offset
            for offset, item in enumerate(grants)
            if isinstance(item, dict) and str(item.get("proposal_id") or "") == proposal_id
        ),
        None,
    )
    if index is None:
        return False
    next_grants = list(grants)
    next_grants.pop(index)
    metadata["approved_training_submissions"] = next_grants
    repository.update_session(session_id, metadata=metadata)
    return True


def safe_training_payload(value: Any) -> Any:
    """Recursively redact absolute paths before values reach Agent events/UI."""

    if isinstance(value, str):
        return _ABSOLUTE_PATH_RE.sub("[redacted path]", value)
    if isinstance(value, list):
        return [safe_training_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): safe_training_payload(item) for key, item in value.items()}
    return value


def _session_owner_id(session: dict[str, Any]) -> str | None:
    metadata = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
    owner_id = str(metadata.get("user_id") or "").strip()
    return owner_id or None


def _proposal_projection(proposal: Any) -> dict[str, Any]:
    return _tool_result_from_activity(proposal)


def _summary_projection(summary: Any) -> dict[str, Any]:
    return _tool_result_from_activity(summary)


def _tool_result_from_activity(value: Any) -> dict[str, Any]:
    """Keep LLM tool output compatible while deriving it from the timeline DTO."""

    return safe_training_payload(
        training_activity_for(value).model_dump(exclude={"kind", "source_tool", "summary"})
    )


def _error_projection(exc: Exception) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "failed", "error": str(exc)}
    if isinstance(exc, AgentTrainingError):
        payload["code"] = exc.code
    return safe_training_payload(payload)


def _json_tool_result(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False)


def build_training_tools(
    session: dict[str, Any],
    *,
    repository: Any,
    training_service: AgentTrainingService,
) -> list[Any]:
    """Build tools for one eligible Build session; all other sessions get none."""

    if not training_tools_enabled_for_session(session):
        return []
    session_id = str(session.get("id") or "")
    owner_id = _session_owner_id(session)

    async def propose_training(
        training_config: dict[str, Any],
        use_queue: bool = False,
        priority: Literal["urgent", "high", "normal", "low"] = "normal",
    ) -> str:
        try:
            proposal = await training_service.propose_training(
                TrainingProposalRequest(
                    config=TrainingConfigInput.model_validate(training_config),
                    use_queue=use_queue,
                    priority=priority,
                ),
                owner_id=owner_id,
                session_id=session_id,
            )
            return _json_tool_result(_proposal_projection(proposal))
        except Exception as exc:
            return _json_tool_result(_error_projection(exc))

    async def submit_training(proposal_id: str) -> str:
        if not consume_training_submission_grant(repository, session_id, proposal_id):
            return _json_tool_result(
                safe_training_payload(
                    {
                        "proposal_id": proposal_id,
                        "status": "failed",
                        "error": "Official approval is required before training submission.",
                    }
                )
            )
        try:
            submission = training_service.submit_training(
                ApprovedTrainingAction(proposal_id=proposal_id, approved=True),
                owner_id=owner_id,
                session_id=session_id,
            )
        except Exception as exc:
            return _json_tool_result(_error_projection(exc))
        result = _tool_result_from_activity(submission)
        try:
            repository.create_training_link(
                session_id=session_id,
                owner_id=owner_id,
                proposal_id=submission.proposal_id,
                task_id=submission.task_id,
            )
        except Exception:
            # The training side effect already succeeded. Never report the
            # task itself as failed or invite a duplicate retry merely because
            # the optional Workbench live-sync link could not be persisted.
            result["sync_status"] = "degraded"
            result["sync_message"] = "Training started, but live progress is temporarily unavailable."
        return _json_tool_result(result)

    async def get_training_summary(task_id: str) -> str:
        try:
            return _json_tool_result(_summary_projection(training_service.get_training_run_summary(task_id)))
        except Exception as exc:
            return _json_tool_result(_error_projection(exc))

    return [
        StructuredTool.from_function(
            coroutine=propose_training,
            name="propose_training",
            description="Run read-only diagnostics for a possible training task; this never submits work.",
            args_schema=ProposeTrainingInput,
        ),
        StructuredTool.from_function(
            coroutine=submit_training,
            name="submit_training",
            description="Submit an existing training proposal. This always pauses for human approval before submission.",
            args_schema=SubmitTrainingInput,
        ),
        StructuredTool.from_function(
            coroutine=get_training_summary,
            name="get_training_summary",
            description="Read the safe status summary of an existing training task.",
            args_schema=GetTrainingSummaryInput,
        ),
    ]


__all__ = [
    "TRAINING_TOOL_NAMES",
    "build_training_tools",
    "consume_training_submission_grant",
    "grant_approved_training_submissions",
    "safe_training_payload",
    "training_submission_interrupt_metadata",
    "training_tools_enabled_for_session",
]
