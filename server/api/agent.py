"""Unified Agent API.

Direct-cut v2 contract:
- /agent/detect-intent
- /agent/detect-intent-multi
- /agent/execute
- /agent/chat-execute
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

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

_agent_config: AgentConfig | None = None
_executor: AgentExecutor | None = None
_detector = None


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
    message: str = ""
    data: dict[str, Any] | None = None
    error: str | None = None
    need_confirm: bool = False


class ChatExecuteRequest(BaseModel):
    message: str
    auto_confirm: bool = False
    context: dict[str, Any] | None = None
    session_id: str | None = None


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
    if action_value in ("file_delete", "dir_delete", "directory_delete"):
        params["confirmed"] = bool(request.confirm)

    result = await executor.execute(action_value, params)
    need_confirm = bool((result.data or {}).get("need_confirm"))
    return ExecuteResponse(
        success=result.success,
        message=result.message or result.feedback or "",
        data=result.data,
        error=result.error,
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
                    exec_result.error_code.value if exec_result.error_code else None,
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
    if intent.action in ("file_delete", "dir_delete", "directory_delete"):
        params["confirmed"] = bool(request.auto_confirm)
        if need_confirm and not request.auto_confirm:
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
            result.error_code.value if result.error_code else None,
        ),
        result=result.to_dict(),
        error=result.error if not result.success else None,
    )


@router.get("/capabilities")
async def get_capabilities():
    executor = get_executor()
    return {
        "actions": sorted(executor.get_supported_actions()),
        "workspace": str(get_agent_config().working_dir),
    }
