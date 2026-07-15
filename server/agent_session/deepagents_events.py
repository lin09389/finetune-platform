from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from agent_training.models import training_activity_from_tool_result

from .execution_plan_events import apply_execution_event_to_session
from .session_state_machine import AgentSessionStateMachine
from .state import ensure_session_state
from .trajectory import content_indicates_tool_failure
from .training_tools import TRAINING_TOOL_NAMES, safe_training_payload


@dataclass
class DeepAgentsEventMapper:
    repository: Any
    notify_event: Any
    session_id: str
    active_text_part_id: str | None = None
    active_text: str = ""
    tool_parts: dict[str, str] = field(default_factory=dict)
    tool_part_payloads: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.state_machine = AgentSessionStateMachine(self.repository)

    def publish(self, event_type: str, message: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        event = self.repository.add_event(self.session_id, event_type, message, payload or {})
        apply_execution_event_to_session(self.repository, self.session_id, event)
        self.notify_event(self.session_id, event)
        return event

    def session_started(self) -> None:
        self.publish("session_started", "DeepAgents 已开始执行。", {"session_id": self.session_id, "runtime": "deepagents"})

    def handle(self, event: dict[str, Any]) -> None:
        kind = str(event.get("event") or "")
        if kind == "on_chat_model_start":
            self._start_text_part(event)
        elif kind == "on_chat_model_stream":
            self._append_text_delta(event)
        elif kind == "on_chat_model_end":
            self._complete_text_part()
        elif kind == "on_tool_start":
            self._tool_start(event)
        elif kind == "on_tool_end":
            self._tool_end(event)
        elif kind == "on_tool_error":
            self._tool_error(event)
        elif kind == "on_chain_stream":
            self._chain_stream(event)
        elif kind == "on_chain_end":
            self.publish("chain_completed", "DeepAgents 图执行完成。", {"session_id": self.session_id, "runtime": "deepagents", **self._agent_context(event)})

    def complete_summary(self, content: str) -> dict[str, Any]:
        part = self.repository.add_part(
            self.session_id,
            "summary",
            status="completed",
            title="最终结果",
            content=content,
            payload={"summary": content, "runtime": "deepagents"},
        )
        self.publish(
            "summary_completed",
            content,
            {
                "session_id": self.session_id,
                "part_id": part.get("id"),
                "part_type": "summary",
                "status": "completed",
                "summary": content,
                "part": part,
            },
        )
        self._maybe_auto_title(content)
        return part

    def _maybe_auto_title(self, summary: str) -> None:
        """Auto-update session title from summary if it's still the default.

        Uses the first meaningful line of the summary (truncated to 56 chars)
        instead of an LLM call -- zero latency, no extra dependency.
        Only fires when the title is the generic placeholder.
        """
        try:
            session = self.repository.get_session(self.session_id)
            if not session:
                return
            current_title = str(session.get("title") or "")
            if current_title and current_title not in {"Agent Session", "新任务", ""}:
                return
            for line in summary.strip().splitlines():
                clean = line.strip().lstrip("#").strip()
                if clean:
                    new_title = clean[:56]
                    self.repository.update_session(self.session_id, title=new_title)
                    self.publish(
                        "session_title_updated",
                        f"会话标题已更新: {new_title}",
                        {"session_id": self.session_id, "title": new_title},
                    )
                    return
        except Exception:
            pass

    def _start_text_part(self, event: dict[str, Any] | None = None) -> None:
        if self.active_text_part_id:
            return
        agent_context = self._agent_context(event or {})
        part = self.repository.add_part(
            self.session_id,
            "text",
            status="running",
            title="AI 正在思考...",
            content="",
            payload={"runtime": "deepagents", **agent_context},
        )
        self.active_text_part_id = part.get("id")
        self.active_text = ""
        self.publish(
            "model_stream_started",
            "AI 正在思考...",
            {"session_id": self.session_id, "part_id": self.active_text_part_id, "part_type": "text", "part": part, **agent_context},
        )

    def _append_text_delta(self, event: dict[str, Any]) -> None:
        chunk = (event.get("data") or {}).get("chunk")
        delta = getattr(chunk, "content", None)
        if isinstance(delta, list):
            delta = "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in delta)
        if not delta:
            return
        if not self.active_text_part_id:
            self._start_text_part(event)
        self.active_text += str(delta)
        part = self.repository.update_part(self.active_text_part_id, content=self.active_text)
        self.publish(
            "part_delta",
            str(delta),
            {
                "session_id": self.session_id,
                "part_id": self.active_text_part_id,
                "part_type": "text",
                "delta": str(delta),
                "content": self.active_text,
                "part": part,
                **self._agent_context_from_part(part),
            },
        )

    def _complete_text_part(self) -> None:
        if not self.active_text_part_id:
            return
        part = self.repository.update_part(self.active_text_part_id, status="completed", content=self.active_text)
        self.publish(
            "model_stream_completed",
            "AI 输出完成。",
            {"session_id": self.session_id, "part_id": self.active_text_part_id, "part_type": "text", "part": part, **self._agent_context_from_part(part)},
        )
        self.active_text_part_id = None
        self.active_text = ""

    def _tool_start(self, event: dict[str, Any]) -> None:
        name = str(event.get("name") or "tool")
        run_id = str(event.get("run_id") or "")
        payload = self._normalize_tool_input((event.get("data") or {}).get("input"))
        if name in TRAINING_TOOL_NAMES:
            payload = safe_training_payload(payload)
        agent_context = self._agent_context(event)
        part_payload = {"tool": name, "input": payload, "runtime": "deepagents", "run_id": run_id, **agent_context}
        part = self.repository.add_part(
            self.session_id,
            "tool_call",
            status="running",
            title=name,
            content=f"正在调用工具：{name}",
            payload=part_payload,
        )
        if run_id:
            self.tool_parts[run_id] = part.get("id")
            self.tool_part_payloads[run_id] = part_payload
        self.publish(
            "tool_call_started",
            f"正在调用工具：{name}",
            {"session_id": self.session_id, "part_id": part.get("id"), "part_type": "tool_call", "tool": name, "part": part, **agent_context},
        )

    def _tool_end(self, event: dict[str, Any]) -> None:
        name = str(event.get("name") or "tool")
        run_id = str(event.get("run_id") or "")
        output = (event.get("data") or {}).get("output")
        content = getattr(output, "content", output)
        output_status = getattr(output, "status", None)
        part_id = self.tool_parts.pop(run_id, None)
        part_payload = self.tool_part_payloads.pop(run_id, {})
        agent_context = self._agent_context(event)
        content_text = str(content) if content is not None else ""
        failed = content_indicates_tool_failure(
            content_text,
            tool=name,
            status=str(output_status) if output_status is not None else None,
        )
        # Only attach training activity for successful-looking payloads.
        activity = None if failed else self._training_activity(name, content)
        if activity:
            part_payload["training_activity"] = activity
        status = "failed" if failed else "completed"
        if part_id:
            part = self.repository.update_part(part_id, status=status, content=content_text, payload=part_payload)
        else:
            part = self.repository.add_part(
                self.session_id,
                "tool_result",
                status=status,
                title=name,
                content=content_text,
                payload={
                    "tool": name,
                    "runtime": "deepagents",
                    "run_id": run_id,
                    **agent_context,
                    **({"training_activity": activity} if activity else {}),
                },
            )
        agent_context = self._agent_context_from_part(part) or agent_context
        if failed:
            self._record_last_tool_error(name, content_text)
            self.publish(
                "tool_call_failed",
                f"工具调用失败：{name}",
                {
                    "session_id": self.session_id,
                    "part_id": part.get("id"),
                    "part_type": part.get("type"),
                    "status": "failed",
                    "tool": name,
                    "error": content_text,
                    "summary": content_text,
                    "part": part,
                    **agent_context,
                },
            )
            return
        self.publish(
            "tool_call_completed",
            f"工具调用完成：{name}",
            {"session_id": self.session_id, "part_id": part.get("id"), "part_type": part.get("type"), "tool": name, "part": part, **agent_context},
        )

    def _tool_error(self, event: dict[str, Any]) -> None:
        name = str(event.get("name") or "tool")
        run_id = str(event.get("run_id") or "")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        error = data.get("error") or data.get("exception") or event.get("error") or "Tool call failed."
        content = str(error)
        part_id = self.tool_parts.pop(run_id, None)
        self.tool_part_payloads.pop(run_id, None)
        agent_context = self._agent_context(event)
        if part_id:
            part = self.repository.update_part(part_id, status="failed", content=content)
        else:
            part = self.repository.add_part(
                self.session_id,
                "tool_result",
                status="failed",
                title=name,
                content=content,
                payload={"tool": name, "runtime": "deepagents", "run_id": run_id, **agent_context},
            )
        agent_context = self._agent_context_from_part(part) or agent_context
        self._record_last_tool_error(name, content)
        self.publish(
            "tool_call_failed",
            f"工具调用失败：{name}",
            {
                "session_id": self.session_id,
                "part_id": part.get("id"),
                "part_type": part.get("type"),
                "status": "failed",
                "tool": name,
                "error": content,
                "summary": content,
                "part": part,
                **agent_context,
            },
        )

    def _record_last_tool_error(self, tool: str, content: str) -> None:
        """Persist last tool failure fingerprint for ops diagnostics (Phase 4)."""
        try:
            session = self.repository.get_session(self.session_id) or {}
            metadata = dict(session.get("metadata") or {})
            trace = dict(metadata.get("execution_trace") or {})
            trace["last_tool_error"] = {
                "tool": tool,
                "message": str(content)[:600],
            }
            metadata["execution_trace"] = trace
            self.repository.update_session(self.session_id, metadata=metadata)
        except Exception:
            pass

    def _chain_stream(self, event: dict[str, Any]) -> None:
        interrupt = self._extract_interrupt(event)
        if not interrupt:
            return
        action_requests = self._normalize_dict_list(interrupt.get("action_requests"))
        review_configs = self._normalize_dict_list(interrupt.get("review_configs"))
        review_config_map = {
            str(config.get("action_name") or config.get("name") or ""): config
            for config in review_configs
            if isinstance(config, dict)
        }
        actions = []
        for index, action in enumerate(action_requests):
            tool_name = str(action.get("name") or "tool")
            review_config = review_config_map.get(tool_name) or (review_configs[index] if index < len(review_configs) else {})
            allowed_decisions = (
                review_config.get("allowed_decisions")
                or review_config.get("allowedDecisions")
                or ["approve", "edit", "reject", "respond"]
            )
            if tool_name in {"submit_training", "resume_training", "cancel_training"}:
                allowed_decisions = ["approve", "reject"]
            training_descriptions = {
                "submit_training": "将提交训练任务；批准后才会创建一个训练任务。",
                "resume_training": "将从检查点恢复训练；批准后才会创建新的恢复任务。",
                "cancel_training": "将请求取消/停止训练任务；批准后才会发出停止请求。",
            }
            actions.append(
                {
                    "index": index,
                    "name": tool_name,
                    "args": safe_training_payload(action.get("args")) if tool_name in TRAINING_TOOL_NAMES and isinstance(action.get("args"), dict) else action.get("args") if isinstance(action.get("args"), dict) else {},
                    "description": (
                        training_descriptions.get(tool_name)
                        or str(action.get("description") or f"工具 {tool_name} 需要确认后继续。")
                    ),
                    "allowed_decisions": list(allowed_decisions) if isinstance(allowed_decisions, list | tuple) else ["approve", "reject"],
                }
            )
        first_action = actions[0] if actions else {"name": "tool", "description": "工具调用需要确认后继续。"}
        title = f"确认 {len(actions) or 1} 个工具调用"
        description = str(first_action.get("description") or "工具调用需要确认后继续。")
        if len(actions) > 1:
            description = f"{len(actions)} 个工具调用需要按顺序确认后继续。"
        agent_context = self._agent_context(event)
        part = self.repository.add_part(
            self.session_id,
            "permission",
            status="pending",
            title=title,
            content=description,
            payload={
                "runtime": "deepagents",
                **agent_context,
                "official_hitl": True,
                "interrupt": interrupt,
                "action_requests": action_requests,
                "review_configs": review_configs,
                "actions": actions,
                "tool": first_action.get("name"),
                "args": first_action.get("args") or {},
                "allowed_decisions": first_action.get("allowed_decisions") or ["approve", "reject"],
                "decisions": [],
            },
        )
        session = self.repository.get_session(self.session_id) or {}
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        self.state_machine.mark_waiting_approval(
            self.session_id,
            metadata=metadata,
            pending_interrupt={
                "part_id": part.get("id"),
                "tool": first_action.get("name"),
                "action_count": len(actions),
                "action_requests": action_requests,
            },
        )
        self.publish(
            "permission_asked",
            description,
            {
                "session_id": self.session_id,
                "part_id": part.get("id"),
                "part_type": "permission",
                "status": "pending",
                "tool": first_action.get("name"),
                "action_count": len(actions),
                "summary": description,
                "part": part,
                **agent_context,
            },
        )

    @staticmethod
    def _agent_context(event: dict[str, Any]) -> dict[str, Any]:
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        agent_name = str(metadata.get("lc_agent_name") or metadata.get("agent_name") or "").strip()
        if agent_name.lower() in {"", "none", "null"}:
            agent_name = ""
        role = "subagent" if agent_name or metadata.get("ls_agent_type") == "subagent" else "parent"
        context: dict[str, Any] = {"agent_role": role}
        if agent_name:
            context["agent_name"] = agent_name
        return context

    @staticmethod
    def _agent_context_from_part(part: dict[str, Any]) -> dict[str, Any]:
        payload = part.get("payload") if isinstance(part.get("payload"), dict) else {}
        context: dict[str, Any] = {"agent_role": payload.get("agent_role") or "parent"}
        if payload.get("agent_name"):
            context["agent_name"] = payload.get("agent_name")
        return context

    @staticmethod
    def _extract_interrupt(event: dict[str, Any]) -> dict[str, Any] | None:
        chunk = (event.get("data") or {}).get("chunk")
        if not isinstance(chunk, dict) or "__interrupt__" not in chunk:
            return None
        interrupts = chunk.get("__interrupt__")
        if not interrupts:
            return None
        item = interrupts[0] if isinstance(interrupts, list | tuple) else interrupts
        value = item.get("value") if isinstance(item, dict) and "value" in item else getattr(item, "value", item)
        return dict(value) if isinstance(value, dict) else None

    @staticmethod
    def _normalize_tool_input(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return dict(value)
        return {"input": value}

    @staticmethod
    def _normalize_dict_list(value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        if isinstance(value, dict):
            return [dict(value)]
        if not isinstance(value, list | tuple):
            return []
        normalized: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(dict(item))
        return normalized

    @staticmethod
    def _training_activity(name: str, content: Any) -> dict[str, Any] | None:
        """Project only valid successful training output; old or failed output stays generic."""

        if name not in TRAINING_TOOL_NAMES:
            return None
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except (TypeError, ValueError):
                return None
        activity = training_activity_from_tool_result(name, content)
        return activity.model_dump() if activity else None


__all__ = ["DeepAgentsEventMapper"]
