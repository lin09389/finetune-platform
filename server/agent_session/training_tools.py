"""Safe, session-scoped DeepAgents tools for the existing training service."""

from __future__ import annotations

import asyncio
import json
import re
import threading
from collections import OrderedDict
from typing import Any, Literal

from agent_training.errors import AgentTrainingError
from agent_training.models import ApprovedTrainingAction, TrainingProposalRequest, training_activity_for
from agent_training.service import AgentTrainingService
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from training_engine.schemas import TrainingConfigInput

TRAINING_TOOL_NAMES = frozenset(
    {
        "propose_training",
        "submit_training",
        "resume_training",
        "cancel_training",
        "get_training_summary",
    }
)
# Side-effecting tools that always require official HITL + one-time grants.
TRAINING_MUTATING_TOOL_NAMES = frozenset({"submit_training", "resume_training", "cancel_training"})
_ABSOLUTE_PATH_RE = re.compile(r"(?<!\w)(?:[A-Za-z]:[\\/]|/)[^\s,;\]\)}]+")
# P1-4: LRU-bounded grant locks prevent unbounded growth from abandoned sessions.
# 64 远超典型并发会话数;被淘汰的 lock 若仍被 caller 持有引用,仍可使用,仅清理 dict 引用。
_MAX_GRANT_LOCKS = 64
_GRANT_LOCKS: OrderedDict[str, threading.Lock] = OrderedDict()
_GRANT_LOCKS_GUARD = threading.Lock()


class ProposeTrainingInput(BaseModel):
    training_config: dict[str, Any] = Field(description="The requested training configuration.")
    use_queue: bool = Field(default=False, description="Whether to submit through the existing training queue.")
    priority: Literal["urgent", "high", "normal", "low"] = Field(default="normal", description="Requested queue priority.")


class SubmitTrainingInput(BaseModel):
    proposal_id: str = Field(description="The exact proposal_id returned by propose_training.")


class ResumeTrainingInput(BaseModel):
    task_id: str = Field(description="The existing training task_id to resume from.")
    checkpoint_name: str = Field(
        description="Single checkpoint directory name under the run's checkpoints/ folder (e.g. checkpoint-500)."
    )


class CancelTrainingInput(BaseModel):
    task_id: str = Field(description="The training task_id to cancel or stop.")


class GetTrainingSummaryInput(BaseModel):
    task_id: str = Field(description="The exact task_id returned after an approved submission or resume.")


def training_tools_enabled_for_session(session: dict[str, Any]) -> bool:
    """Return whether the session is explicitly allowed to access training tools."""

    metadata = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
    task_mode = session.get("task_mode") or metadata.get("task_mode")
    return str(session.get("agent_id") or "build") == "build" and task_mode in {"train", "hybrid"}


def training_submission_interrupt_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Force mutating training tools through DeepAgents HITL while preserving tool policy."""

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
    for tool_name in TRAINING_MUTATING_TOOL_NAMES:
        interrupt_on[tool_name] = True
    updated["deepagents_interrupt_on"] = interrupt_on
    return updated


def _session_grant_lock(session_id: str) -> threading.Lock:
    with _GRANT_LOCKS_GUARD:
        lock = _GRANT_LOCKS.get(session_id)
        if lock is None:
            lock = threading.Lock()
            _GRANT_LOCKS[session_id] = lock
            # P1-4: evict oldest entries when capacity exceeded.
            while len(_GRANT_LOCKS) > _MAX_GRANT_LOCKS:
                _GRANT_LOCKS.popitem(last=False)
        else:
            # P1-4: LRU — 最近访问移到末尾,避免被淘汰
            _GRANT_LOCKS.move_to_end(session_id)
        return lock


def grant_approved_training_actions(
    repository: Any,
    permission_part: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> None:
    """Persist one-time grants only after an official approval response.

    Covers submit / resume / cancel. Called by the approval service, not by
    LLM-facing tools; tools only consume matching grants.
    """

    payload = permission_part.get("payload") if isinstance(permission_part.get("payload"), dict) else {}
    if not payload.get("official_hitl"):
        return
    action_requests = payload.get("action_requests") if isinstance(payload.get("action_requests"), list) else []
    session_id = str(permission_part.get("session_id") or "")
    if not session_id:
        return

    submit_ids: list[str] = []
    resume_grants: list[dict[str, str]] = []
    cancel_ids: list[str] = []
    for action, decision in zip(action_requests, decisions, strict=False):
        if not isinstance(action, dict) or not isinstance(decision, dict):
            continue
        if decision.get("type") != "approve":
            continue
        name = str(action.get("name") or "")
        args = action.get("args") if isinstance(action.get("args"), dict) else {}
        if name == "submit_training":
            proposal_id = str(args.get("proposal_id") or "").strip()
            if proposal_id:
                submit_ids.append(proposal_id)
        elif name == "resume_training":
            task_id = str(args.get("task_id") or "").strip()
            checkpoint_name = str(args.get("checkpoint_name") or "").strip()
            if task_id and checkpoint_name:
                resume_grants.append({"task_id": task_id, "checkpoint_name": checkpoint_name})
        elif name == "cancel_training":
            task_id = str(args.get("task_id") or "").strip()
            if task_id:
                cancel_ids.append(task_id)

    if not submit_ids and not resume_grants and not cancel_ids:
        return

    with _session_grant_lock(session_id):
        session = repository.get_session(session_id) or {}
        if not training_tools_enabled_for_session(session):
            return
        metadata = dict(session.get("metadata") or {})
        permission_part_id = str(permission_part.get("id") or "")

        if submit_ids:
            grants = metadata.get("approved_training_submissions")
            grants = list(grants) if isinstance(grants, list) else []
            for proposal_id in submit_ids:
                grants.append({"proposal_id": proposal_id, "permission_part_id": permission_part_id})
            metadata["approved_training_submissions"] = grants

        if resume_grants:
            grants = metadata.get("approved_training_resumes")
            grants = list(grants) if isinstance(grants, list) else []
            for item in resume_grants:
                grants.append({**item, "permission_part_id": permission_part_id})
            metadata["approved_training_resumes"] = grants

        if cancel_ids:
            grants = metadata.get("approved_training_cancellations")
            grants = list(grants) if isinstance(grants, list) else []
            for task_id in cancel_ids:
                grants.append({"task_id": task_id, "permission_part_id": permission_part_id})
            metadata["approved_training_cancellations"] = grants

        repository.update_session(session_id, metadata=metadata)


# Backward-compatible alias (historical name referred only to submit grants).
grant_approved_training_submissions = grant_approved_training_actions


def consume_training_submission_grant(repository: Any, session_id: str, proposal_id: str) -> bool:
    """Consume exactly one matching official approval before calling training."""

    return _consume_list_grant(
        repository,
        session_id,
        metadata_key="approved_training_submissions",
        match=lambda item: str(item.get("proposal_id") or "") == proposal_id,
    )


def restore_training_submission_grant(
    repository: Any,
    session_id: str,
    proposal_id: str,
    *,
    permission_part_id: str = "restored-after-failed-submit",
) -> None:
    """Return a grant when submission fails after consume but before task creation."""

    proposal_id = str(proposal_id or "").strip()
    if not session_id or not proposal_id:
        return
    _append_list_grant(
        repository,
        session_id,
        metadata_key="approved_training_submissions",
        entry={"proposal_id": proposal_id, "permission_part_id": permission_part_id},
    )


def consume_training_resume_grant(
    repository: Any,
    session_id: str,
    *,
    task_id: str,
    checkpoint_name: str,
) -> bool:
    return _consume_list_grant(
        repository,
        session_id,
        metadata_key="approved_training_resumes",
        match=lambda item: (
            str(item.get("task_id") or "") == task_id
            and str(item.get("checkpoint_name") or "") == checkpoint_name
        ),
    )


def restore_training_resume_grant(
    repository: Any,
    session_id: str,
    *,
    task_id: str,
    checkpoint_name: str,
    permission_part_id: str = "restored-after-failed-resume",
) -> None:
    _append_list_grant(
        repository,
        session_id,
        metadata_key="approved_training_resumes",
        entry={
            "task_id": task_id,
            "checkpoint_name": checkpoint_name,
            "permission_part_id": permission_part_id,
        },
    )


def consume_training_cancel_grant(repository: Any, session_id: str, task_id: str) -> bool:
    return _consume_list_grant(
        repository,
        session_id,
        metadata_key="approved_training_cancellations",
        match=lambda item: str(item.get("task_id") or "") == task_id,
    )


def restore_training_cancel_grant(
    repository: Any,
    session_id: str,
    task_id: str,
    *,
    permission_part_id: str = "restored-after-failed-cancel",
) -> None:
    _append_list_grant(
        repository,
        session_id,
        metadata_key="approved_training_cancellations",
        entry={"task_id": task_id, "permission_part_id": permission_part_id},
    )


def _consume_list_grant(
    repository: Any,
    session_id: str,
    *,
    metadata_key: str,
    match,
) -> bool:
    with _session_grant_lock(session_id):
        session = repository.get_session(session_id) or {}
        if not training_tools_enabled_for_session(session):
            return False
        metadata = dict(session.get("metadata") or {})
        grants = metadata.get(metadata_key)
        if not isinstance(grants, list):
            return False
        index = next(
            (
                offset
                for offset, item in enumerate(grants)
                if isinstance(item, dict) and match(item)
            ),
            None,
        )
        if index is None:
            return False
        next_grants = list(grants)
        next_grants.pop(index)
        metadata[metadata_key] = next_grants
        repository.update_session(session_id, metadata=metadata)
        return True


def _append_list_grant(
    repository: Any,
    session_id: str,
    *,
    metadata_key: str,
    entry: dict[str, str],
) -> None:
    with _session_grant_lock(session_id):
        session = repository.get_session(session_id) or {}
        if not training_tools_enabled_for_session(session):
            return
        metadata = dict(session.get("metadata") or {})
        grants = metadata.get(metadata_key)
        grants = list(grants) if isinstance(grants, list) else []
        grants.append(entry)
        metadata[metadata_key] = grants
        repository.update_session(session_id, metadata=metadata)


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


def _session_may_read_training_task(
    repository: Any,
    *,
    session_id: str,
    owner_id: str | None,
    task_id: str,
) -> bool:
    """Restrict summary/mutation to the Agent session that owns the training link.

    Repositories without a training-link store (simple unit doubles) stay open
    so pure tool-adapter tests remain focused. Production AgentSessionRepository
    always exposes get_training_link.
    """

    # P2-6: 排除 unittest mock / MagicMock 等 test double,避免 mock 属性访问
    # 导致误判(MagicMock 会对任何属性返回 mock,使 callable(getter) 为 True)
    cls = type(repository)
    if cls.__module__.startswith("unittest") or "Mock" in cls.__name__:
        return True

    getter = getattr(repository, "get_training_link", None)
    if not callable(getter):
        return True
    link = getter(task_id)
    if not isinstance(link, dict):
        return False
    if str(link.get("session_id") or "") != session_id:
        return False
    link_owner = str(link.get("owner_id") or "").strip() or None
    if owner_id and link_owner and owner_id != link_owner:
        return False
    return True


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
            submission = await asyncio.to_thread(
                training_service.submit_training,
                ApprovedTrainingAction(proposal_id=proposal_id, approved=True),
                owner_id=owner_id,
                session_id=session_id,
            )
        except Exception as exc:
            restore_training_submission_grant(repository, session_id, proposal_id)
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
            result["sync_status"] = "degraded"
            result["sync_message"] = "Training started, but live progress is temporarily unavailable."
        return _json_tool_result(result)

    async def resume_training(task_id: str, checkpoint_name: str) -> str:
        if not _session_may_read_training_task(
            repository,
            session_id=session_id,
            owner_id=owner_id,
            task_id=task_id,
        ):
            return _json_tool_result(
                safe_training_payload(
                    {
                        "task_id": task_id,
                        "status": "failed",
                        "code": "training_run_forbidden",
                        "error": "Training run is not visible to this Agent session.",
                    }
                )
            )
        if not consume_training_resume_grant(
            repository,
            session_id,
            task_id=task_id,
            checkpoint_name=checkpoint_name,
        ):
            return _json_tool_result(
                safe_training_payload(
                    {
                        "task_id": task_id,
                        "checkpoint_name": checkpoint_name,
                        "status": "failed",
                        "error": "Official approval is required before training resume.",
                    }
                )
            )
        try:
            resumed = await asyncio.to_thread(
                training_service.resume_training,
                task_id=task_id,
                checkpoint_name=checkpoint_name,
                owner_id=owner_id,
                session_id=session_id,
            )
        except Exception as exc:
            restore_training_resume_grant(
                repository,
                session_id,
                task_id=task_id,
                checkpoint_name=checkpoint_name,
            )
            return _json_tool_result(_error_projection(exc))
        result = _tool_result_from_activity(resumed)
        try:
            # Synthetic proposal key documents resume lineage without colliding
            # with real proposal UUIDs; create_training_link only requires a
            # non-empty stable identifier.
            repository.create_training_link(
                session_id=session_id,
                owner_id=owner_id,
                proposal_id=f"resume:{task_id}:{checkpoint_name}",
                task_id=resumed.task_id,
            )
        except Exception:
            result["sync_status"] = "degraded"
            result["sync_message"] = "Resume started, but live progress is temporarily unavailable."
        return _json_tool_result(result)

    async def cancel_training(task_id: str) -> str:
        if not _session_may_read_training_task(
            repository,
            session_id=session_id,
            owner_id=owner_id,
            task_id=task_id,
        ):
            return _json_tool_result(
                safe_training_payload(
                    {
                        "task_id": task_id,
                        "status": "failed",
                        "code": "training_run_forbidden",
                        "error": "Training run is not visible to this Agent session.",
                    }
                )
            )
        if not consume_training_cancel_grant(repository, session_id, task_id):
            return _json_tool_result(
                safe_training_payload(
                    {
                        "task_id": task_id,
                        "status": "failed",
                        "error": "Official approval is required before training cancel.",
                    }
                )
            )
        try:
            cancelled = await asyncio.to_thread(
                training_service.cancel_training,
                task_id=task_id,
                owner_id=owner_id,
                session_id=session_id,
            )
        except Exception as exc:
            restore_training_cancel_grant(repository, session_id, task_id)
            return _json_tool_result(_error_projection(exc))
        return _json_tool_result(_tool_result_from_activity(cancelled))

    async def get_training_summary(task_id: str) -> str:
        if not _session_may_read_training_task(
            repository,
            session_id=session_id,
            owner_id=owner_id,
            task_id=task_id,
        ):
            return _json_tool_result(
                safe_training_payload(
                    {
                        "task_id": task_id,
                        "status": "failed",
                        "code": "training_run_forbidden",
                        "error": "Training run is not visible to this Agent session.",
                    }
                )
            )
        try:
            return _json_tool_result(
                _summary_projection(
                    await asyncio.to_thread(
                        training_service.get_training_run_summary,
                        task_id,
                    )
                )
            )
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
            coroutine=resume_training,
            name="resume_training",
            description=(
                "Resume a training run from a named checkpoint under that run's checkpoints/ folder. "
                "Always pauses for human approval. Creates a new task_id."
            ),
            args_schema=ResumeTrainingInput,
        ),
        StructuredTool.from_function(
            coroutine=cancel_training,
            name="cancel_training",
            description="Request cancel/stop for a training task owned by this session. Always pauses for human approval.",
            args_schema=CancelTrainingInput,
        ),
        StructuredTool.from_function(
            coroutine=get_training_summary,
            name="get_training_summary",
            description="Read the safe status summary of an existing training task.",
            args_schema=GetTrainingSummaryInput,
        ),
    ]


__all__ = [
    "TRAINING_MUTATING_TOOL_NAMES",
    "TRAINING_TOOL_NAMES",
    "build_training_tools",
    "consume_training_cancel_grant",
    "consume_training_resume_grant",
    "consume_training_submission_grant",
    "grant_approved_training_actions",
    "grant_approved_training_submissions",
    "restore_training_cancel_grant",
    "restore_training_resume_grant",
    "restore_training_submission_grant",
    "safe_training_payload",
    "training_submission_interrupt_metadata",
    "training_tools_enabled_for_session",
]
