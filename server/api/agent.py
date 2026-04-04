"""Unified Agent API.

Direct-cut v2 contract:
- /agent/detect-intent
- /agent/detect-intent-multi
- /agent/execute
- /agent/chat-execute
- /agent/run-loop
"""

import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent.config import ActionType, AgentConfig
from agent.core import UnifiedExecutor as AgentExecutor
from agent.intent.detector import get_detector
from api.chat.session import get_session_manager
from core.config import get_settings
from security.audit_log import get_audit_logger

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

_agent_config: AgentConfig | None = None
_executor: AgentExecutor | None = None
_detector = None
HIGH_RISK_ACTIONS = {
    "file_delete",
    "file_patch",
    "dir_delete",
    "directory_delete",
    "process_kill",
    "service_stop",
    "command_execute",
    "command_run",
    "tests_run",
}


class DetectIntentRequest(BaseModel):
    message: str
    session_id: str | None = None
    context: dict[str, Any] | None = None


class DetectIntentResponse(BaseModel):
    detected: bool
    intent_type: str = ""
    action: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    confidence: float = 0.0
    need_confirm: bool = False
    execution: dict[str, Any] | None = None


class DetectMultiIntentResponse(BaseModel):
    detected: bool
    intents: list[DetectIntentResponse] = Field(default_factory=list)
    has_ambiguity: bool = False
    clarification_dialog: dict[str, Any] | None = None
    chain: list[str] = Field(default_factory=list)


class ExecuteRequest(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    confirm: bool = False


class ExecuteResponse(BaseModel):
    success: bool
    status: str = "unknown"
    message: str = ""
    data: dict[str, Any] | None = None
    error: str | None = None
    error_code: str | None = None
    need_confirm: bool = False


class ChatExecuteRequest(BaseModel):
    message: str
    auto_confirm: bool = False
    context: dict[str, Any] | None = None
    session_id: str | None = None


class ResumeRequest(BaseModel):
    session_id: str
    auto_confirm: bool = False
    context: dict[str, Any] | None = None


class ResumeFromEventRequest(BaseModel):
    session_id: str
    event_id: str
    auto_confirm: bool = False
    context: dict[str, Any] | None = None


class RunLoopRequest(BaseModel):
    message: str
    auto_confirm: bool = False
    context: dict[str, Any] | None = None
    session_id: str | None = None
    max_steps: int = Field(default=5, ge=1, le=10)


class ChatExecuteResponse(BaseModel):
    detected: bool
    intent_type: str = ""
    action: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    confidence: float = 0.0
    need_confirm: bool = False
    execution: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


def get_agent_config() -> AgentConfig:
    global _agent_config
    if _agent_config is None:
        _agent_config = AgentConfig(working_dir=settings.base_dir, enable_confirm=True, enable_audit=True)
    return _agent_config


def get_executor() -> AgentExecutor:
    global _executor
    if _executor is None:
        from agent.core.executor import create_executor

        _executor = create_executor(workspace=str(get_agent_config().working_dir), enable_audit_log=True)
    return _executor


def get_unified_detector():
    global _detector
    if _detector is None:
        _detector = get_detector()
    return _detector


def _execution_payload(
    status: str,
    error: str | None = None,
    result: Any = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    return {"status": status, "error": error, "error_code": error_code, "result": result}


def _requires_confirmation(action: str) -> bool:
    return action in HIGH_RISK_ACTIONS


def _build_action_recovery_hint(action: str, result: Any, step: int) -> str:
    data = (result.data or {}) if result else {}
    if isinstance(data, dict) and data.get("kind") == "test_run":
        test_summary = data.get("test_summary") or {}
        failure_files = test_summary.get("failure_files") or []
        failure_cases = test_summary.get("failure_cases") or []
        if failure_cases:
            first_case = failure_cases[0]
            case_name = first_case.get("name") or "the failing test"
            case_message = first_case.get("message") or "Inspect the failure output and update the code or assertions."
            return f"Fix {case_name} before resuming. {case_message}"
        if failure_files:
            return f"Investigate {failure_files[0]} and rerun the tests from step {step} after applying a fix."
        return f"Review the failed test output from step {step}, fix the issue, then rerun the test command."
    if isinstance(data, dict) and action.startswith("file_"):
        target = data.get("path") or data.get("file_path") or "the target file"
        return f"Check {target} for invalid content or path issues, then retry step {step}."
    return f"Fix the failure at step {step} or resume from an earlier successful step."


def _result_message(result: Any) -> str:
    if not result:
        return ""
    return getattr(result, "message", "") or getattr(result, "feedback", "") or ""


def _result_error_code(result: Any) -> str | None:
    error_code = getattr(result, "error_code", None)
    if not error_code:
        return None
    return error_code.value if hasattr(error_code, "value") else str(error_code)


def _result_to_dict(result: Any) -> dict[str, Any]:
    if not result:
        return {}
    try:
        return result.to_dict()
    except AttributeError:
        return {
            "success": bool(getattr(result, "success", False)),
            "message": _result_message(result),
            "data": getattr(result, "data", None),
            "error": getattr(result, "error", None),
            "error_code": _result_error_code(result),
            "feedback": getattr(result, "feedback", None),
        }


def _summarize_action(action_result: dict[str, Any]) -> str:
    action = action_result.get("action") or "unknown_action"
    data = action_result.get("data") or {}
    if isinstance(data, dict):
        if action == "file_patch":
            applied_files = data.get("applied_files") or []
            if isinstance(applied_files, list) and applied_files:
                return f"patched {applied_files[0]}"
        if action == "file_write":
            target = data.get("path") or data.get("file_path")
            if isinstance(target, str) and target:
                return f"wrote {target}"
        if action == "file_read":
            target = data.get("path") or data.get("file_path")
            if isinstance(target, str) and target:
                return f"read {target}"
        if data.get("kind") == "test_run":
            test_summary = data.get("test_summary") or {}
            failed = int(test_summary.get("failed") or 0)
            passed = int(test_summary.get("passed") or 0)
            return f"ran tests ({passed} passed, {failed} failed)"
        if data.get("kind") == "command_run":
            command = data.get("command")
            if isinstance(command, str) and command:
                return f"ran command `{command}`"
    return str(action).replace("_", " ")


def _build_run_loop_summary(
    completed_actions: list[dict[str, Any]],
    step_records: list[dict[str, Any]],
    final_status: str,
    recovery_hint: str | None = None,
) -> dict[str, Any]:
    completed = sum(1 for step in step_records if step.get("status") == "completed")
    failed = sum(1 for step in step_records if step.get("status") == "failed")
    waiting = sum(1 for step in step_records if step.get("status") == "waiting_confirmation")
    inference = sum(1 for step in step_records if step.get("status") == "needs_inference")
    executed_preview = [_summarize_action(action) for action in completed_actions[-3:]]

    if final_status == "failed":
        summary = (
            f"Completed {completed} step(s) before the task failed."
            + (f" Last actions: {', '.join(executed_preview)}." if executed_preview else "")
        )
        recommended_next = recovery_hint or "Investigate the failed step and resume from the latest good state."
    elif final_status == "needs_confirmation":
        summary = (
            f"Completed {completed} step(s) and paused for confirmation."
            + (f" Last actions: {', '.join(executed_preview)}." if executed_preview else "")
        )
        recommended_next = recovery_hint or "Confirm the pending step to continue the task."
    elif final_status == "needs_inference":
        summary = (
            f"Completed {completed} step(s) and now needs model reasoning to continue."
            + (f" Last actions: {', '.join(executed_preview)}." if executed_preview else "")
        )
        recommended_next = recovery_hint or "Continue with model generation, then resume the remaining steps."
    else:
        summary = (
            f"Completed {completed} step(s) successfully."
            + (f" Last actions: {', '.join(executed_preview)}." if executed_preview else "")
        )
        if failed:
            summary += f" {failed} step(s) still failed."
        if waiting:
            summary += f" {waiting} step(s) are waiting for confirmation."
        if inference:
            summary += f" {inference} step(s) still require inference."
        recommended_next = recovery_hint or "Review the latest result and continue with the next planned task."

    return {
        "loop_summary": summary,
        "recommended_next_step": recommended_next,
        "completed_steps": completed,
        "failed_steps": failed,
        "waiting_steps": waiting,
        "inference_steps": inference,
    }


def _should_run_auto_repair_pipeline(request: RunLoopRequest, action: str, result: Any) -> bool:
    if action != "tests_run":
        return False
    context = request.context or {}
    if not context.get("auto_repair_pipeline"):
        return False
    data = getattr(result, "data", None) or {}
    if not isinstance(data, dict) or data.get("kind") != "test_run":
        return False
    test_summary = data.get("test_summary") or {}
    failure_files = test_summary.get("failure_files") or []
    return bool(isinstance(failure_files, list) and failure_files)


def _build_auto_repair_prompt(target_file: str, command: str | None = None) -> str:
    command_note = f"\n\nFailing command:\n{command}" if command else ""
    return (
        f"Read {target_file} and analyze why the latest test run is failing."
        f"{command_note}\n\n"
        "Then draft a concrete patch proposal in unified diff format. "
        "Explain the likely root cause first, then provide the patch."
    )


def _resolve_run_loop_intents(request: RunLoopRequest, detector: Any) -> list[Any]:
    override_intents = (request.context or {}).get("detected_intents")
    if isinstance(override_intents, list) and override_intents:
        resolved = []
        for item in override_intents[: request.max_steps]:
            if isinstance(item, DetectIntentResponse):
                resolved.append(item)
            elif isinstance(item, dict):
                resolved.append(DetectIntentResponse(**item))
        if resolved:
            return resolved

    multi = detector.detect_multi(request.message, session_id=request.session_id, context=request.context)
    return multi.intents[: request.max_steps] if multi.intents else []


def _append_state(session_id: str | None, stage: str, payload: dict[str, Any] | None = None) -> None:
    if not session_id:
        return
    manager = get_session_manager()
    manager.append_execution_state(
        session_id,
        {
            "stage": stage,
            "payload": payload or {},
        },
    )


def _extract_target_path(message: str, context: dict[str, Any] | None = None) -> str | None:
    if context:
        for key in ("target_path", "file_path", "path", "generated_filename"):
            value = context.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    match = re.search(r"([A-Za-z0-9_\-./\\]+\.[A-Za-z0-9]{1,8})", message)
    return match.group(1) if match else None


def _has_content(context: dict[str, Any] | None = None) -> bool:
    if not context:
        return False
    return any(
        isinstance(context.get(k), str) and context.get(k).strip()
        for k in ("content", "generated_content")
    )


def _heuristic_save_intent(message: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    text = message.lower()
    has_save = any(word in text for word in ("save", "保存", "落盘", "写入文件", "存到"))
    has_generate = any(
        word in text for word in ("generate", "write", "draft", "创建内容", "生成", "写一篇", "写一个", "起草")
    )
    target_path = _extract_target_path(message, context)
    content_exists = _has_content(context)

    if has_generate and has_save:
        return {
            "detected": True,
            "intent_type": "composite_content_save",
            "action": None,
            "params": {
                "target_path": target_path,
                "preconditions": {"has_content": content_exists, "path_writable": bool(target_path)},
            },
            "description": "generate content and save",
            "confidence": 0.92,
            "need_confirm": False,
        }

    if has_save:
        need_confirm = not content_exists or not bool(target_path)
        return {
            "detected": True,
            "intent_type": "save_content",
            "action": "file_write" if target_path else None,
            "params": {
                "target_path": target_path,
                "preconditions": {"has_content": content_exists, "path_writable": bool(target_path)},
            },
            "description": "save existing content",
            "confidence": 0.90,
            "need_confirm": need_confirm,
        }

    if has_generate:
        return {
            "detected": True,
            "intent_type": "content_generation",
            "action": None,
            "params": {"preconditions": {"has_content": content_exists}},
            "description": "generate content",
            "confidence": 0.85,
            "need_confirm": False,
        }

    return None


def _find_resume_event(timeline: list[dict[str, Any]]) -> dict[str, Any] | None:
    interesting_types = {"tool_result", "file_change", "command_output", "confirmation_request"}
    interesting_stages = {"persisted", "generated", "planned"}

    for item in reversed(timeline):
        if item.get("type") in interesting_types:
            return item
        if item.get("stage") in interesting_stages:
            return item
    return None


def _find_resume_event_by_id(timeline: list[dict[str, Any]], event_id: str) -> dict[str, Any] | None:
    for item in timeline:
        if str(item.get("id") or "") == event_id:
            return item
    return None


def _build_resume_message(session: Any, event_id: str | None = None) -> tuple[str, dict[str, Any]]:
    metadata = session.metadata or {}
    timeline = metadata.get("execution_timeline", [])
    if not isinstance(timeline, list):
        timeline = []

    last_goal = metadata.get("last_agent_goal")
    if not isinstance(last_goal, str) or not last_goal.strip():
        for message in reversed(session.messages):
            if getattr(message, "role", "") == "user" and getattr(message, "content", "").strip():
                last_goal = message.content.strip()
                break
    if not isinstance(last_goal, str) or not last_goal.strip():
        last_goal = "Continue the previous task from the most recent execution state."

    pending_confirmation = metadata.get("pending_confirmation")
    if isinstance(pending_confirmation, dict) and pending_confirmation.get("action"):
        action = pending_confirmation.get("action")
        description = pending_confirmation.get("description") or "Continue the pending action."
        return (
            last_goal,
            {
                "resume_reason": "pending_confirmation",
                "pending_confirmation": pending_confirmation,
                "resume_action": action,
                "resume_description": description,
            },
        )

    if event_id:
        last_event = _find_resume_event_by_id(timeline, event_id)
        if not last_event:
            raise HTTPException(status_code=404, detail="Execution event not found")
    else:
        last_event = _find_resume_event(timeline)
    if not last_event:
        return (
            last_goal,
            {
                "resume_reason": "last_goal_only",
            },
        )

    title = last_event.get("title") or last_event.get("stage") or "latest execution step"
    payload = last_event.get("payload") or {}
    description = last_event.get("description") or ""
    return (
        (
            f"{last_goal}\n\n"
            "Continue from the last execution state instead of restarting.\n\n"
            f"Latest step: {title}\n"
            f"Latest result: {payload or description}"
        ),
        {
            "resume_reason": "selected_event" if event_id else "latest_event",
            "resume_event": last_event,
            "resume_title": title,
        },
    )


@router.post("/detect-intent", response_model=DetectIntentResponse)
async def detect_intent(request: DetectIntentRequest):
    heuristic = _heuristic_save_intent(request.message, request.context)
    if heuristic is not None:
        return DetectIntentResponse(
            detected=heuristic["detected"],
            intent_type=heuristic["intent_type"],
            action=heuristic["action"],
            params=heuristic["params"],
            description=heuristic["description"],
            confidence=float(heuristic["confidence"]),
            need_confirm=bool(heuristic["need_confirm"]),
            execution=_execution_payload("planned"),
        )

    detector = get_unified_detector()
    result = detector.detect(request.message, session_id=request.session_id, context=request.context)
    return DetectIntentResponse(
        detected=result.detected,
        intent_type=result.intent_type or "",
        action=result.action,
        params=result.params or {},
        description=result.description,
        confidence=float(result.confidence or 0.0),
        need_confirm=bool(result.need_confirm),
        execution=_execution_payload("planned" if result.detected else "skipped"),
    )


@router.post("/detect-intent-multi", response_model=DetectMultiIntentResponse)
async def detect_intent_multi(request: DetectIntentRequest):
    heuristic = _heuristic_save_intent(request.message, request.context)
    if heuristic is not None:
        return DetectMultiIntentResponse(
            detected=True,
            intents=[
                DetectIntentResponse(
                    detected=True,
                    intent_type=heuristic["intent_type"],
                    action=heuristic["action"],
                    params=heuristic["params"],
                    description=heuristic["description"],
                    confidence=float(heuristic["confidence"]),
                    need_confirm=bool(heuristic["need_confirm"]),
                    execution=_execution_payload("planned"),
                )
            ],
            has_ambiguity=bool(heuristic["need_confirm"]),
            clarification_dialog={"reason": "missing_content_or_target_path"} if heuristic["need_confirm"] else None,
            chain=["detect", "plan"],
        )

    detector = get_unified_detector()
    result = detector.detect_multi(request.message, session_id=request.session_id, context=request.context)

    intents: list[DetectIntentResponse] = []
    for item in result.intents:
        intents.append(
            DetectIntentResponse(
                detected=item.detected,
                intent_type=item.intent_type or "",
                action=item.action,
                params=item.params or {},
                description=item.description,
                confidence=float(item.confidence or 0.0),
                need_confirm=bool(item.need_confirm),
                execution=_execution_payload("planned" if item.detected else "skipped"),
            )
        )

    return DetectMultiIntentResponse(
        detected=bool(result.detected),
        intents=intents,
        has_ambiguity=bool(result.has_ambiguity),
        clarification_dialog=result.clarification_dialog,
        chain=result.chain or [],
    )


@router.post("/execute", response_model=ExecuteResponse)
async def execute_action(request: ExecuteRequest):
    executor = get_executor()

    action_value = request.action
    try:
        action_enum = ActionType(request.action)
        action_value = action_enum.value
    except Exception:
        if request.action not in executor.get_supported_actions():
            raise HTTPException(400, f"Unsupported action: {request.action}")

    params = dict(request.params)
    if _requires_confirmation(action_value):
        params["confirmed"] = bool(request.confirm)
        if not request.confirm:
            return ExecuteResponse(
                success=False,
                status="needs_confirmation",
                message=f"Action '{action_value}' requires explicit confirmation",
                data={"action": action_value, "params": params},
                error="confirmation_required",
                error_code="needs_confirmation",
                need_confirm=True,
            )

    result = await executor.execute(action_value, params)
    need_confirm = bool((result.data or {}).get("need_confirm"))
    error_code = None
    if result.error_code:
        error_code = result.error_code.value if hasattr(result.error_code, "value") else str(result.error_code)
    return ExecuteResponse(
        success=result.success,
        status="executed" if result.success else "failed",
        message=_result_message(result),
        data=result.data,
        error=result.error,
        error_code=error_code,
        need_confirm=need_confirm,
    )


@router.post("/chat-execute", response_model=ChatExecuteResponse)
async def chat_execute(request: ChatExecuteRequest):
    detector = get_unified_detector()
    executor = get_executor()

    heuristic = _heuristic_save_intent(request.message, request.context)
    if heuristic is not None:
        _append_state(request.session_id, "detected", {"message": request.message, "intent_type": heuristic["intent_type"]})
        _append_state(request.session_id, "planned", {"intent_type": heuristic["intent_type"], "params": heuristic["params"]})

        if heuristic["intent_type"] == "content_generation":
            _append_state(request.session_id, "generated", {"source": "inference_required"})
            return ChatExecuteResponse(
                detected=True,
                intent_type="content_generation",
                action=None,
                params=heuristic["params"],
                description=heuristic["description"],
                confidence=float(heuristic["confidence"]),
                need_confirm=False,
                execution=_execution_payload("planned"),
                result={"reason": "content_generation", "need_inference": True},
            )

        if heuristic["intent_type"] == "save_content":
            pre = heuristic["params"].get("preconditions", {})
            if not pre.get("has_content") or not pre.get("path_writable"):
                return ChatExecuteResponse(
                    detected=True,
                    intent_type="save_content",
                    action=None,
                    params=heuristic["params"],
                    description="missing prerequisites for save",
                    confidence=float(heuristic["confidence"]),
                    need_confirm=True,
                    execution=_execution_payload(
                        "needs_confirmation",
                        error="missing prerequisites for save",
                        error_code="validation_error",
                    ),
                    result={"need_confirm": True, "missing": pre},
                )

            content = (request.context or {}).get("content") or (request.context or {}).get("generated_content") or ""
            exec_result = await executor.execute(
                "file_write",
                {"path": heuristic["params"]["target_path"], "content": content},
            )
            if exec_result.success:
                _append_state(request.session_id, "persisted", {"action": "file_write", "result": exec_result.to_dict()})
            else:
                _append_state(request.session_id, "persisted", {"action": "file_write", "error": exec_result.error})
            return ChatExecuteResponse(
                detected=True,
                intent_type="save_content",
                action="file_write",
                params=heuristic["params"],
                description=heuristic["description"],
                confidence=float(heuristic["confidence"]),
                need_confirm=False,
                execution=_execution_payload(
                    "executed" if exec_result.success else "failed",
                    exec_result.error,
                    exec_result.to_dict(),
                    _result_error_code(exec_result),
                ),
                result=exec_result.to_dict(),
                error=exec_result.error if not exec_result.success else None,
            )

        if heuristic["intent_type"] == "composite_content_save":
            _append_state(request.session_id, "generated", {"source": "inference_required"})
            return ChatExecuteResponse(
                detected=True,
                intent_type="composite_content_save",
                action=None,
                params=heuristic["params"],
                description=heuristic["description"],
                confidence=float(heuristic["confidence"]),
                need_confirm=False,
                execution=_execution_payload("planned"),
                result={
                    "reason": "composite_content_save",
                    "need_inference": True,
                    "target_path": heuristic["params"].get("target_path"),
                },
            )

    _append_state(request.session_id, "detected", {"message": request.message})
    intent = detector.detect(request.message, session_id=request.session_id, context=request.context)
    if not intent.detected:
        _append_state(request.session_id, "planned", {"status": "no_intent"})
        return ChatExecuteResponse(
            detected=False,
            execution=_execution_payload("skipped"),
            result={"reason": "no_intent_detected"},
        )

    if intent.intent_type == "conversation" or not intent.action:
        _append_state(request.session_id, "planned", {"intent_type": intent.intent_type or "conversation"})
        return ChatExecuteResponse(
            detected=True,
            intent_type=intent.intent_type or "conversation",
            action="conversation",
            params=intent.params or {},
            description=intent.description,
            confidence=float(intent.confidence or 0.0),
            need_confirm=False,
            execution=_execution_payload("planned"),
            result={"type": "conversation", "need_inference": True},
        )

    if intent.intent_type in ("content_generation", "generate_content"):
        _append_state(request.session_id, "planned", {"intent_type": "content_generation"})
        _append_state(request.session_id, "generated", {"source": "inference_required"})
        return ChatExecuteResponse(
            detected=True,
            intent_type="content_generation",
            action=None,
            params=intent.params or {},
            description=intent.description,
            confidence=float(intent.confidence or 0.0),
            need_confirm=False,
            execution=_execution_payload("planned"),
            result={"reason": "content_generation", "need_inference": True},
        )

    params = dict(intent.params or {})
    need_confirm = bool(intent.need_confirm)
    if _requires_confirmation(intent.action):
        params["confirmed"] = bool(request.auto_confirm)
        if (need_confirm or _requires_confirmation(intent.action)) and not request.auto_confirm:
            _append_state(request.session_id, "planned", {"action": intent.action, "needs_confirmation": True})
            return ChatExecuteResponse(
                detected=True,
                intent_type=intent.intent_type or "",
                action=intent.action,
                params=params,
                description=intent.description,
                confidence=float(intent.confidence or 0.0),
                need_confirm=True,
                execution=_execution_payload("needs_confirmation"),
                result={"need_confirm": True, "params": params},
            )

    _append_state(request.session_id, "planned", {"action": intent.action, "params": params})
    result = await executor.execute(intent.action, params)
    if result.success:
        _append_state(request.session_id, "persisted", {"action": intent.action, "result": result.to_dict()})
    else:
        _append_state(request.session_id, "persisted", {"action": intent.action, "error": result.error})
    return ChatExecuteResponse(
        detected=True,
        intent_type=intent.intent_type or "",
        action=intent.action,
        params=params,
        description=intent.description,
        confidence=float(intent.confidence or 0.0),
        need_confirm=False,
        execution=_execution_payload(
            "executed" if result.success else "failed",
            result.error,
            result.to_dict(),
            _result_error_code(result),
        ),
        result=result.to_dict(),
        error=result.error if not result.success else None,
    )


@router.post("/resume", response_model=ChatExecuteResponse)
async def resume_chat_execute(request: ResumeRequest):
    manager = get_session_manager()
    session = manager.get_session(request.session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    metadata = session.metadata or {}
    pending_confirmation = metadata.get("pending_confirmation")

    if isinstance(pending_confirmation, dict) and pending_confirmation.get("action") and request.auto_confirm:
        executor = get_executor()
        action = str(pending_confirmation["action"])
        params = dict(pending_confirmation.get("params") or {})
        if _requires_confirmation(action):
            params["confirmed"] = True

        _append_state(request.session_id, "resumed", {"action": action, "mode": "confirm_pending"})
        result = await executor.execute(action, params)
        if result.success:
            _append_state(request.session_id, "persisted", {"action": action, "result": result.to_dict()})
        else:
            _append_state(request.session_id, "persisted", {"action": action, "error": result.error})

        return ChatExecuteResponse(
            detected=True,
            intent_type="resume_pending_confirmation",
            action=action,
            params=params,
            description=str(pending_confirmation.get("description") or "Resumed pending confirmation"),
            confidence=1.0,
            need_confirm=False,
            execution=_execution_payload(
                "executed" if result.success else "failed",
                result.error,
                result.to_dict(),
                _result_error_code(result),
            ),
            result=result.to_dict(),
            error=result.error if not result.success else None,
        )

    message, resume_context = _build_resume_message(session)
    merged_context = {
        **resume_context,
        **(request.context or {}),
        "workspace_root": (request.context or {}).get("workspace_root") or metadata.get("workspace_root"),
    }
    _append_state(request.session_id, "resumed", {"mode": resume_context.get("resume_reason")})
    return await chat_execute(
        ChatExecuteRequest(
            message=message,
            auto_confirm=request.auto_confirm,
            context=merged_context,
            session_id=request.session_id,
        )
    )


@router.post("/resume-from-event", response_model=ChatExecuteResponse)
async def resume_from_event(request: ResumeFromEventRequest):
    manager = get_session_manager()
    session = manager.get_session(request.session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    message, resume_context = _build_resume_message(session, request.event_id)
    merged_context = {
        **resume_context,
        **(request.context or {}),
        "workspace_root": (request.context or {}).get("workspace_root")
        or (session.metadata or {}).get("workspace_root"),
    }
    _append_state(
        request.session_id,
        "resumed",
        {"mode": "selected_event", "event_id": request.event_id},
    )
    return await chat_execute(
        ChatExecuteRequest(
            message=message,
            auto_confirm=request.auto_confirm,
            context=merged_context,
            session_id=request.session_id,
        )
    )


@router.post("/run-loop", response_model=ChatExecuteResponse)
async def run_loop(request: RunLoopRequest):
    detector = get_unified_detector()
    executor = get_executor()

    _append_state(request.session_id, "detected", {"message": request.message, "mode": "run_loop"})
    intents = _resolve_run_loop_intents(request, detector)
    completed_actions: list[dict[str, Any]] = []
    step_records: list[dict[str, Any]] = []

    if not intents:
        summary = _build_run_loop_summary(completed_actions, step_records, "skipped", "No executable steps were found.")
        return ChatExecuteResponse(
            detected=False,
            execution=_execution_payload("skipped"),
            result={
                "reason": "no_intent_detected",
                "completed_actions": completed_actions,
                "step_records": step_records,
                **summary,
            },
        )

    for index, intent in enumerate(intents, start=1):
        if not intent.detected:
            step_records.append(
                {
                    "step": index,
                    "status": "skipped",
                    "intent_type": intent.intent_type or "unknown",
                    "reason": "intent_not_detected",
                }
            )
            continue

        intent_type = intent.intent_type or ""
        params = dict(intent.params or {})
        step_record: dict[str, Any] = {
            "step": index,
            "intent_type": intent_type,
            "action": intent.action,
            "params": params,
            "status": "pending",
            "description": intent.description,
        }

        if intent_type in ("conversation", "content_generation", "generate_content") or not intent.action:
            step_record["status"] = "needs_inference"
            step_records.append(step_record)
            summary = _build_run_loop_summary(
                completed_actions,
                step_records,
                "needs_inference",
                f"Resume from step {index} after content generation.",
            )
            _append_state(
                request.session_id,
                "planned",
                {
                    "step": index,
                    "intent_type": intent_type or "conversation",
                    "remaining_requires_inference": True,
                    "completed_actions": completed_actions,
                    "step_records": step_records,
                },
            )
            return ChatExecuteResponse(
                detected=True,
                intent_type=intent_type or "conversation",
                action=intent.action or "conversation",
                params=params,
                description=intent.description,
                confidence=float(intent.confidence or 0.0),
                need_confirm=False,
                execution=_execution_payload("planned"),
                result={
                    "type": intent_type or "conversation",
                    "need_inference": True,
                    "completed_actions": completed_actions,
                    "step_records": step_records,
                    "recovery_hint": f"Resume from step {index} after content generation.",
                    **summary,
                },
            )

        if _requires_confirmation(intent.action):
            params["confirmed"] = bool(request.auto_confirm)
            if not request.auto_confirm:
                step_record["status"] = "waiting_confirmation"
                step_records.append(step_record)
                summary = _build_run_loop_summary(
                    completed_actions,
                    step_records,
                    "needs_confirmation",
                    f"Confirm step {index} to continue the loop.",
                )
                _append_state(
                    request.session_id,
                    "planned",
                    {
                        "step": index,
                        "action": intent.action,
                        "needs_confirmation": True,
                        "completed_actions": completed_actions,
                        "step_records": step_records,
                    },
                )
                return ChatExecuteResponse(
                    detected=True,
                    intent_type=intent_type,
                    action=intent.action,
                    params=params,
                    description=intent.description,
                    confidence=float(intent.confidence or 0.0),
                    need_confirm=True,
                    execution=_execution_payload("needs_confirmation"),
                    result={
                        "need_confirm": True,
                        "completed_actions": completed_actions,
                        "step_records": step_records,
                        "pending_action": intent.action,
                        "pending_params": params,
                        "recovery_hint": f"Confirm step {index} to continue the loop.",
                        **summary,
                    },
                )

        _append_state(request.session_id, "planned", {"action": intent.action, "params": params})
        result = await executor.execute(intent.action, params)
        action_result = {
            "action": intent.action,
            "params": params,
            "success": result.success,
            "message": _result_message(result),
            "error": result.error,
            "data": result.data,
        }
        completed_actions.append(action_result)
        step_record["status"] = "completed" if result.success else "failed"
        step_record["result"] = action_result
        step_records.append(step_record)

        if result.success:
            _append_state(request.session_id, "persisted", {"action": intent.action, "result": _result_to_dict(result)})
        else:
            _append_state(request.session_id, "persisted", {"action": intent.action, "error": result.error})
            recovery_hint = _build_action_recovery_hint(intent.action, result, index)
            prompt_override = None
            rerun_command = None
            target_file = None
            if _should_run_auto_repair_pipeline(request, intent.action, result):
                test_data = getattr(result, "data", None) or {}
                test_summary = test_data.get("test_summary") or {}
                failure_files = test_summary.get("failure_files") or []
                target_file = failure_files[0] if failure_files else None
                rerun_command = test_data.get("command")
                if isinstance(target_file, str) and target_file.strip():
                    read_params = {"path": target_file.strip()}
                    read_result = await executor.execute("file_read", read_params)
                    read_action_result = {
                        "action": "file_read",
                        "params": read_params,
                        "success": read_result.success,
                        "message": _result_message(read_result),
                        "error": read_result.error,
                        "data": getattr(read_result, "data", None),
                    }
                    completed_actions.append(read_action_result)
                    step_records.append(
                        {
                            "step": index + 1,
                            "intent_type": "file_read",
                            "action": "file_read",
                            "params": read_params,
                            "status": "completed" if read_result.success else "failed",
                            "description": "Read the first failing test file for automatic repair analysis.",
                            "result": read_action_result,
                        }
                    )
                    if read_result.success:
                        _append_state(
                            request.session_id,
                            "persisted",
                            {"action": "file_read", "result": _result_to_dict(read_result)},
                        )
                        command = test_data.get("command")
                        prompt_override = _build_auto_repair_prompt(
                            target_file.strip(),
                            command if isinstance(command, str) else None,
                        )
                        recovery_hint = (
                            f"Automatic repair prep completed for {target_file.strip()}. "
                            "Review the generated patch proposal before applying changes."
                        )
                    else:
                        _append_state(
                            request.session_id,
                            "persisted",
                            {"action": "file_read", "error": read_result.error},
                        )
            summary = _build_run_loop_summary(completed_actions, step_records, "failed", recovery_hint)
            return ChatExecuteResponse(
                detected=True,
                intent_type=intent_type,
                action=intent.action,
                params=params,
                description=intent.description,
                confidence=float(intent.confidence or 0.0),
                need_confirm=False,
                execution=_execution_payload(
                    "failed",
                    result.error,
                    _result_to_dict(result),
                    _result_error_code(result),
                ),
                result={
                    "completed_actions": completed_actions,
                    "step_records": step_records,
                    "last_result": _result_to_dict(result),
                    "recovery_hint": recovery_hint,
                    "prompt_override": prompt_override,
                    "need_inference": bool(prompt_override),
                    "auto_repair_pipeline": bool(prompt_override),
                    "pipeline_stage": "repair_context_loaded" if prompt_override else "execution_failed",
                    "target_file": target_file.strip() if isinstance(target_file, str) else None,
                    "rerun_command": (
                        rerun_command
                        if isinstance(rerun_command, str)
                        else " ".join(str(part) for part in rerun_command)
                        if isinstance(rerun_command, list)
                        else None
                    ),
                    **summary,
                },
                error=result.error,
            )

    summary = _build_run_loop_summary(completed_actions, step_records, "completed")
    return ChatExecuteResponse(
        detected=True,
        intent_type="multi_action" if len(completed_actions) > 1 else intents[0].intent_type or "",
        action=completed_actions[-1]["action"] if completed_actions else None,
        params=completed_actions[-1]["params"] if completed_actions else {},
        description=f"Executed {len(completed_actions)} action(s)",
        confidence=1.0 if completed_actions else 0.0,
        need_confirm=False,
        execution=_execution_payload("executed", result={"completed_actions": completed_actions, "step_records": step_records}),
        result={
            "completed_actions": completed_actions,
            "step_records": step_records,
            "message": f"Executed {len(completed_actions)} action(s)",
            **summary,
        },
    )


@router.get("/capabilities")
async def get_capabilities():
    executor = get_executor()
    actions = sorted(executor.get_supported_actions())
    return {
        "actions": actions,
        "capabilities": actions,
        "workspace": str(get_agent_config().working_dir),
    }


@router.get("/audit/stats")
async def get_audit_stats():
    return get_audit_logger().get_stats()


@router.get("/audit/recent")
async def get_recent_audit_events(limit: int = 50):
    events = get_audit_logger().get_recent_events(limit=limit)
    return {"events": [event.to_dict() for event in events], "total": len(events)}
