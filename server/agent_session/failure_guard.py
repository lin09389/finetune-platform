from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .state import ensure_session_state


DEFAULT_LOOP_GUARD_THRESHOLD = 3
MAX_RECENT_FAILURES = 8
FAILURE_WINDOW_SIZE = 6
MAX_CONSECUTIVE_FAILURES = 4
NO_PROGRESS_THRESHOLD = 4
MODEL_NO_ACTION_THRESHOLD = 3
MAX_RECENT_OBSERVATIONS = 10

_OBSERVATION_TOOLS = {"read_file", "grep", "glob", "ls"}
_ERROR_PATTERNS = (
    "error",
    "exception",
    "traceback",
    "failed",
    "failure",
    "syntaxerror",
    "typeerror",
    "valueerror",
    "modulenotfounderror",
    "filenotfounderror",
    "no such file",
    "not found",
    "command failed",
    "exit code",
    "non-zero",
    "permission denied",
    "timed out",
    "timeout",
    "no matches",
    "no match",
    "0 matches",
    "nothing found",
)


class AgentLoopGuardTriggered(RuntimeError):
    """Raised when repeated failures or no-progress loops should stop the agent."""


@dataclass(frozen=True)
class FailureObservation:
    signature: str
    family_signature: str
    tool: str
    input_excerpt: str
    error_excerpt: str
    event_type: str
    part_id: str
    family: str


@dataclass(frozen=True)
class NoProgressObservation:
    signature: str
    tool: str
    input_excerpt: str
    output_excerpt: str
    event_type: str
    part_id: str
    threshold: int


class AgentFailureGuard:
    def __init__(self, repository: Any, state_machine: Any, notify_event: Any, *, threshold: int = DEFAULT_LOOP_GUARD_THRESHOLD):
        self.repository = repository
        self.state_machine = state_machine
        self.notify_event = notify_event
        self.threshold = max(2, threshold)

    def observe_event(self, session_id: str, event: dict[str, Any]) -> None:
        failure = self._failure_observation(event)
        if failure is not None:
            self._observe_failure(session_id, failure)
            return

        no_progress = self._no_progress_observation(event)
        if no_progress is not None:
            self._observe_no_progress(session_id, no_progress)
            return

        self._reset_on_progress(session_id, event)

    def _observe_failure(self, session_id: str, observation: FailureObservation) -> None:
        session = self.repository.get_session(session_id)
        if not session:
            return
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        guard = dict(metadata.get("loop_guard") or {})
        if guard.get("blocked"):
            return

        previous_signature = str(guard.get("last_signature") or "")
        previous_family_signature = str(guard.get("last_family_signature") or "")
        repeat_count = int(guard.get("repeat_count") or 0)
        family_repeat_count = int(guard.get("family_repeat_count") or 0)
        consecutive_failure_count = int(guard.get("consecutive_failure_count") or 0) + 1
        repeat_count = repeat_count + 1 if previous_signature == observation.signature else 1
        family_repeat_count = family_repeat_count + 1 if previous_family_signature == observation.family_signature else 1

        recent = [dict(item) for item in guard.get("recent_failures") or [] if isinstance(item, dict)]
        recent.append(
            {
                "signature": observation.signature,
                "family_signature": observation.family_signature,
                "family": observation.family,
                "tool": observation.tool,
                "input_excerpt": observation.input_excerpt,
                "error_excerpt": observation.error_excerpt,
                "event_type": observation.event_type,
                "part_id": observation.part_id,
            }
        )
        guard.update(
            {
                "last_signature": observation.signature,
                "last_family_signature": observation.family_signature,
                "repeat_count": repeat_count,
                "family_repeat_count": family_repeat_count,
                "consecutive_failure_count": consecutive_failure_count,
                "threshold": self.threshold,
                "recent_failures": recent[-MAX_RECENT_FAILURES:],
                "recent_observations": [],
                "last_no_progress_signature": "",
                "no_progress_repeat_count": 0,
            }
        )
        metadata["loop_guard"] = guard
        self.repository.update_session(session_id, metadata=metadata)

        recent_window = recent[-FAILURE_WINDOW_SIZE:]
        recent_family_count = sum(1 for item in recent_window if item.get("family_signature") == observation.family_signature)
        if repeat_count >= self.threshold:
            reason_code = "repeated_identical_failure"
            reason_count = repeat_count
            message = (
                f"连续 {repeat_count} 次遇到相同工具失败，已停止 Agent 以避免重复无效操作。"
                f"工具：{observation.tool}；错误摘要：{observation.error_excerpt[:240]}"
            )
        elif family_repeat_count >= self.threshold or recent_family_count >= self.threshold:
            reason_code = "repeated_failure_family"
            reason_count = max(family_repeat_count, recent_family_count)
            message = (
                f"连续 {reason_count} 次遇到同类工具失败，已停止 Agent 以避免在同一问题上循环。"
                f"工具：{observation.tool}；失败类型：{observation.family}；错误摘要：{observation.error_excerpt[:240]}"
            )
        elif consecutive_failure_count >= MAX_CONSECUTIVE_FAILURES:
            reason_code = "consecutive_failures"
            reason_count = consecutive_failure_count
            message = (
                f"连续 {consecutive_failure_count} 次工具调用失败，已停止 Agent 以避免交替重试进入死循环。"
                f"最后工具：{observation.tool}；错误摘要：{observation.error_excerpt[:240]}"
            )
        else:
            return

        self._trigger(session_id, message, observation, reason_count=reason_count, reason_code=reason_code)
        raise AgentLoopGuardTriggered(message)

    def _observe_no_progress(self, session_id: str, observation: NoProgressObservation) -> None:
        session = self.repository.get_session(session_id)
        if not session:
            return
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        guard = dict(metadata.get("loop_guard") or {})
        if guard.get("blocked"):
            return

        previous_signature = str(guard.get("last_no_progress_signature") or "")
        repeat_count = int(guard.get("no_progress_repeat_count") or 0)
        repeat_count = repeat_count + 1 if previous_signature == observation.signature else 1
        recent = [dict(item) for item in guard.get("recent_observations") or [] if isinstance(item, dict)]
        recent.append(
            {
                "signature": observation.signature,
                "tool": observation.tool,
                "input_excerpt": observation.input_excerpt,
                "output_excerpt": observation.output_excerpt,
                "event_type": observation.event_type,
                "part_id": observation.part_id,
            }
        )
        guard.update(
            {
                "last_signature": "",
                "last_family_signature": "",
                "repeat_count": 0,
                "family_repeat_count": 0,
                "consecutive_failure_count": 0,
                "recent_failures": [],
                "last_no_progress_signature": observation.signature,
                "no_progress_repeat_count": repeat_count,
                "no_progress_threshold": observation.threshold,
                "recent_observations": recent[-MAX_RECENT_OBSERVATIONS:],
            }
        )
        metadata["loop_guard"] = guard
        self.repository.update_session(session_id, metadata=metadata)
        if repeat_count < observation.threshold:
            return

        message = (
            f"连续 {repeat_count} 次重复查看相同信息且没有产生新进展，已停止 Agent 以避免无进展循环。"
            f"工具：{observation.tool}；输入：{observation.input_excerpt[:160]}"
        )
        self._trigger(session_id, message, observation, reason_count=repeat_count, reason_code="repeated_no_progress")
        raise AgentLoopGuardTriggered(message)

    def _trigger(
        self,
        session_id: str,
        message: str,
        observation: FailureObservation | NoProgressObservation,
        *,
        reason_count: int,
        reason_code: str,
    ) -> None:
        session = self.repository.get_session(session_id) or {}
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        guard = dict(metadata.get("loop_guard") or {})
        guard.update(
            {
                "blocked": True,
                "blocked_reason": message,
                "blocked_reason_code": reason_code,
                "blocked_signature": observation.signature,
                "repeat_count": reason_count,
            }
        )
        metadata["loop_guard"] = guard
        metadata["latest_error"] = message
        state = dict(metadata.get("state") or {})
        state["latest_error"] = message
        metadata["state"] = state
        part = self.repository.add_part(
            session_id,
            "error",
            status="failed",
            title="连续失败阻断",
            content=message,
            payload={
                "summary": message,
                "guard": "loop_guard",
                "reason_code": reason_code,
                "repeat_count": reason_count,
                "threshold": self.threshold,
                "tool": observation.tool,
                "input_excerpt": observation.input_excerpt,
                "error_excerpt": getattr(observation, "error_excerpt", ""),
                "output_excerpt": getattr(observation, "output_excerpt", ""),
                "signature": observation.signature,
            },
        )
        self.state_machine.mark_failed(session_id, metadata=metadata, status="needs_manual_review", error=message)
        event = self.repository.add_event(
            session_id,
            "loop_guard_triggered",
            message,
            {
                "session_id": session_id,
                "part_id": part.get("id"),
                "part_type": "error",
                "status": "failed",
                "summary": message,
                "guard": "loop_guard",
                "reason_code": reason_code,
                "repeat_count": reason_count,
                "threshold": self.threshold,
                "tool": observation.tool,
                "input_excerpt": observation.input_excerpt,
                "error_excerpt": getattr(observation, "error_excerpt", ""),
                "output_excerpt": getattr(observation, "output_excerpt", ""),
                "signature": observation.signature,
            },
        )
        self.notify_event(session_id, event)

    def _reset_on_progress(self, session_id: str, event: dict[str, Any]) -> None:
        event_type = str(event.get("event_type") or "")
        if event_type not in {"tool_call_completed", "summary_completed", "permission_asked", "node_recovery_started", "node_recovery_completed"}:
            return
        session = self.repository.get_session(session_id)
        if not session:
            return
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        guard = dict(metadata.get("loop_guard") or {})
        if not guard or guard.get("blocked"):
            return
        guard["last_signature"] = ""
        guard["last_family_signature"] = ""
        guard["repeat_count"] = 0
        guard["family_repeat_count"] = 0
        guard["consecutive_failure_count"] = 0
        guard["recent_failures"] = []
        if event_type not in {"tool_call_completed", "model_stream_completed"}:
            guard["last_no_progress_signature"] = ""
            guard["no_progress_repeat_count"] = 0
        metadata["loop_guard"] = guard
        self.repository.update_session(session_id, metadata=metadata)

    def _failure_observation(self, event: dict[str, Any]) -> FailureObservation | None:
        event_type = str(event.get("event_type") or "")
        if event_type not in {"tool_call_completed", "tool_call_failed", "model_stream_failed", "command_failed", "action_failed"}:
            return None
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        part = payload.get("part") if isinstance(payload.get("part"), dict) else {}
        part_payload = part.get("payload") if isinstance(part.get("payload"), dict) else {}
        tool = str(payload.get("tool") or part_payload.get("tool") or part.get("title") or event_type)
        error_text = str(
            payload.get("error")
            or payload.get("summary")
            or part.get("content")
            or payload.get("content")
            or event.get("message")
            or ""
        )
        if event_type == "tool_call_completed" and not self._looks_like_failure(error_text):
            return None
        input_value = part_payload.get("input") if "input" in part_payload else payload.get("input")
        error_excerpt = self._normalize_text(error_text, limit=500)
        family = self._error_family(error_excerpt)
        input_excerpt = self._stable_excerpt(input_value, limit=500)
        signature = self._stable_json(
            {
                "event_type": "tool_failure",
                "tool": tool,
                "input": input_excerpt,
                "error": error_excerpt,
            }
        )
        family_signature = self._stable_json(
            {
                "event_type": "tool_failure_family",
                "tool": tool,
                "input": input_excerpt,
                "family": family,
            }
        )
        return FailureObservation(
            signature=signature,
            family_signature=family_signature,
            tool=tool,
            input_excerpt=self._stable_excerpt(input_value, limit=240),
            error_excerpt=error_excerpt,
            event_type=event_type,
            part_id=str(payload.get("part_id") or part.get("id") or ""),
            family=family,
        )

    def _no_progress_observation(self, event: dict[str, Any]) -> NoProgressObservation | None:
        event_type = str(event.get("event_type") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        part = payload.get("part") if isinstance(payload.get("part"), dict) else {}
        part_payload = part.get("payload") if isinstance(part.get("payload"), dict) else {}
        content = str(part.get("content") or payload.get("content") or event.get("message") or "")
        if self._looks_like_failure(content):
            return None
        if event_type == "tool_call_completed":
            tool = str(payload.get("tool") or part_payload.get("tool") or part.get("title") or "")
            if tool not in _OBSERVATION_TOOLS:
                return None
            input_value = part_payload.get("input") if "input" in part_payload else payload.get("input")
            threshold = NO_PROGRESS_THRESHOLD
            signature_event_type = "tool_no_progress"
        elif event_type == "model_stream_completed":
            if not content.strip():
                return None
            tool = "assistant_output"
            input_value = ""
            threshold = MODEL_NO_ACTION_THRESHOLD
            signature_event_type = "model_no_action"
        else:
            return None
        input_excerpt = self._stable_excerpt(input_value, limit=500)
        output_excerpt = self._normalize_text(content, limit=500)
        signature = self._stable_json(
            {
                "event_type": signature_event_type,
                "tool": tool,
                "input": input_excerpt,
                "output": output_excerpt,
            }
        )
        return NoProgressObservation(
            signature=signature,
            tool=tool,
            input_excerpt=self._stable_excerpt(input_value, limit=240),
            output_excerpt=output_excerpt,
            event_type=event_type,
            part_id=str(payload.get("part_id") or part.get("id") or ""),
            threshold=threshold,
        )

    @staticmethod
    def _looks_like_failure(text: str) -> bool:
        normalized = text.lower()
        return any(pattern in normalized for pattern in _ERROR_PATTERNS)

    @staticmethod
    def _error_family(text: str) -> str:
        normalized = AgentFailureGuard._normalize_text(text.lower(), limit=500)
        normalized = re.sub(r"`[^`]{1,160}`", "`<value>`", normalized)
        normalized = re.sub(r"['\"][^'\"]{1,160}['\"]", '"<value>"', normalized)
        normalized = re.sub(r"\b0x[0-9a-f]+\b", "<hex>", normalized)
        normalized = re.sub(r"\b[0-9a-f]{8,}\b", "<id>", normalized)
        normalized = re.sub(r"\b\d+\b", "<num>", normalized)
        normalized = re.sub(r"[a-z]:\\[^\s]+", "<path>", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"/[^\s]+", "<path>", normalized)
        if "no matches" in normalized or "no match" in normalized or "nothing found" in normalized:
            return "no_matches"
        if "not found" in normalized or "no such file" in normalized or "filenotfounderror" in normalized:
            return "not_found"
        if "syntaxerror" in normalized:
            return "syntax_error"
        if "modulenotfounderror" in normalized:
            return "module_not_found"
        if "permission denied" in normalized:
            return "permission_denied"
        if "timed out" in normalized or "timeout" in normalized:
            return "timeout"
        if "exit code" in normalized or "non-zero" in normalized or "command failed" in normalized:
            return "command_failed"
        return normalized[:240] or "unknown_failure"

    @classmethod
    def _stable_excerpt(cls, value: Any, *, limit: int) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return cls._normalize_text(value, limit=limit)
        return cls._normalize_text(cls._stable_json(value), limit=limit)

    @staticmethod
    def _stable_json(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        except TypeError:
            return str(value)

    @staticmethod
    def _normalize_text(value: str, *, limit: int) -> str:
        text = re.sub(r"\s+", " ", str(value)).strip()
        return text[:limit]
