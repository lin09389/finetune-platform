from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import interrupt

from agent_runtime.definitions import RuntimeExecutionContext
from agent_runtime.langgraph.provider_adapter import get_chat_model

from ..parser import parse_agent_response
from ..state import ensure_session_state, record_command, record_diff, set_phase
from .state import AgentSessionGraphState


class AgentSessionLangGraphRuntime:
    def __init__(self, repository: Any, processor: Any, model_call: Any = None):
        self.repository = repository
        self.processor = processor
        self.model_call = model_call
        self._invocation_contexts: dict[str, dict[str, Any]] = {}

    def set_invocation_context(
        self,
        session_id: str,
        *,
        model_call: Any = None,
        stream_model_call: Any = None,
    ) -> None:
        self._invocation_contexts[session_id] = {
            "model_call": model_call,
            "stream_model_call": stream_model_call,
        }

    def clear_invocation_context(self, session_id: str) -> None:
        self._invocation_contexts.pop(session_id, None)

    async def bootstrap_node(self, state: AgentSessionGraphState) -> dict[str, Any]:
        if state.get("messages"):
            return {}
        session = self._session(state["session_id"])
        prompt = str(state.get("prompt") or "")
        metadata = self.processor._ensure_metadata(session)
        metadata["current_goal"] = prompt
        metadata["task_intent"] = self.processor._classify_task_intent(prompt)
        metadata["runtime"] = "langgraph"
        metadata = set_phase(metadata, "running")
        session = self.repository.update_session(session["id"], status="running", metadata=metadata)
        request_part = self.repository.add_part(session["id"], "text", status="completed", title="请求", content=prompt)
        self.processor._event(session["id"], "session_started", "Agent 开始处理请求", {"content": prompt, "part_id": request_part["id"]})
        return {
            "messages": self.processor._initial_messages(session, prompt),
            "pending_tool_calls": [],
            "tool_results": [],
            "pending_part_id": None,
            "pending_permission_call": None,
            "final_summary": None,
            "phase": "running",
            "repair_attempts": int(metadata.get("repair_attempts") or 0),
            "protocol_repair_count": int(metadata.get("protocol_repair_count") or 0),
            "execution_state": "running",
            "iterations": 0,
            "last_model_raw": "",
            "streaming_enabled": False,
            "streaming_part_id": None,
            "streaming_failed": False,
            "last_stream_error": None,
            "streaming_raw": "",
        }

    async def model_call_node(self, state: AgentSessionGraphState) -> dict[str, Any]:
        session = self._session(state["session_id"])
        messages = list(state.get("messages") or [])
        iterations = int(state.get("iterations") or 0)
        if iterations >= self.processor.max_iterations:
            result = self.processor._fallback_summary(session["id"], "Agent 达到最大工具轮次，已根据当前执行记录生成总结。")
            summary = self._latest_summary(session["id"], result)
            return {"final_summary": summary, "execution_state": result.get("status") or "needs_manual_review", "iterations": iterations}

        raw, text_chunks, summary_text, tool_calls, streaming_finalized_type, streaming_part_id, streaming_failed, stream_error = await self._invoke_model(session, messages)
        for index, text in enumerate(text_chunks):
            content = text.strip()
            if not content or streaming_finalized_type:
                continue
            text_part = self.repository.add_part(
                session["id"],
                "text",
                status="completed",
                title="说明",
                content=content,
                payload={"part_index": index, "source": "langgraph"},
            )
            self.processor._event(session["id"], "part_created", content, {"part_id": text_part["id"], "part_type": "text", "status": "completed"})

        execution_state = "running" if tool_calls else "completed"
        final_summary = summary_text
        if not tool_calls and not final_summary:
            stripped = raw.strip()
            if stripped:
                final_summary = stripped
        if streaming_finalized_type == "summary":
            final_summary = summary_text or final_summary or raw.strip() or "任务已完成。"
            metadata = set_phase(self.processor._ensure_metadata(self._session(session["id"])), "completed")
            self.repository.update_session(session["id"], status="completed", metadata=metadata)
            self.processor._event(
                session["id"],
                "summary_completed",
                final_summary,
                {"part_id": streaming_part_id or "streaming", "streaming": True},
            )
            execution_state = "completed"
            tool_calls = []
        return {
            "pending_tool_calls": tool_calls,
            "final_summary": final_summary,
            "execution_state": execution_state,
            "iterations": iterations + 1,
            "last_model_raw": raw,
            "streaming_enabled": bool(self._invocation_context(state["session_id"]).get("stream_model_call")),
            "streaming_part_id": streaming_part_id,
            "streaming_failed": streaming_failed,
            "last_stream_error": stream_error,
            "streaming_raw": raw if streaming_part_id else "",
        }

    async def tool_exec_node(self, state: AgentSessionGraphState) -> dict[str, Any]:
        session_id = state["session_id"]
        messages = list(state.get("messages") or [])
        pending_tool_calls = list(state.get("pending_tool_calls") or [])
        for index, call in enumerate(pending_tool_calls):
            raw = json.dumps({"tool": call.get("name"), "arguments": call.get("args") or {}}, ensure_ascii=False)
            handled, next_model = self.processor._execute_tool_request(
                session_id,
                {"tool": str(call.get("name") or ""), "arguments": dict(call.get("args") or {})},
                raw,
                messages,
                part_index=index,
            )
            refreshed = self._session(session_id)
            if handled is not None:
                status = str(refreshed.get("status") or "")
                if status == "waiting_permission":
                    return {
                        "messages": messages,
                        "pending_tool_calls": [],
                        "pending_part_id": self._latest_part_id(session_id, {"permission"}, {"pending"}),
                        "pending_permission_call": dict(call),
                        "execution_state": "waiting_permission",
                    }
                if status == "waiting_approval":
                    return {
                        "messages": messages,
                        "pending_tool_calls": [],
                        "pending_part_id": self._latest_part_id(session_id, {"diff", "command"}, {"pending", "approved"}),
                        "execution_state": "waiting_approval",
                    }
                return {
                    "messages": messages,
                    "pending_tool_calls": [],
                    "final_summary": self._latest_summary(session_id, handled),
                    "execution_state": status or "completed",
                }
            if next_model:
                return {"messages": messages, "pending_tool_calls": [], "execution_state": "running"}
        return {"messages": messages, "pending_tool_calls": [], "execution_state": "running"}

    async def permission_gate_node(self, state: AgentSessionGraphState) -> dict[str, Any]:
        session = self._session(state["session_id"])
        part_id = str(state.get("pending_part_id") or self._latest_part_id(session["id"], {"permission"}, {"pending"}) or "")
        if not part_id:
            return {"execution_state": "running"}
        permission_part = self.repository.get_part(part_id)
        payload = {
            "interrupt_kind": "permission_request",
            "session_id": session["id"],
            "part_id": part_id,
            "tool": (permission_part or {}).get("payload", {}).get("tool"),
            "arguments": (permission_part or {}).get("payload", {}).get("arguments"),
        }
        decision = interrupt(payload)
        approved = bool((decision or {}).get("approved"))
        if not approved:
            self.repository.update_part(part_id, status="blocked")
            metadata = set_phase(self.processor._ensure_metadata(session), "failed")
            self.repository.update_session(session["id"], status="failed", metadata=metadata)
            self.processor._event(session["id"], "action_rejected", "权限请求已拒绝", {"part_id": part_id})
            return {"pending_part_id": None, "pending_permission_call": None, "final_summary": "权限请求已拒绝，Agent 已停止。", "execution_state": "failed"}

        self.repository.update_part(part_id, status="approved")
        guidance = "权限已批准，但该工具仍不可直接执行。请改用内置工具继续完成任务。"
        result_part = self.repository.add_part(
            session["id"],
            "tool_result",
            status="completed",
            title="权限已批准",
            content=guidance,
            payload={"guidance": guidance, "tool": (permission_part or {}).get("payload", {}).get("tool"), "source": "langgraph_permission_resume"},
        )
        metadata = set_phase(self.processor._ensure_metadata(self._session(session["id"])), "running")
        self.repository.update_session(session["id"], status="running", metadata=metadata)
        self.processor._event(session["id"], "tool_call_completed", guidance, {"part_id": result_part["id"], "tool": "permission"})
        observation = self.processor._compact_observation(
            "permission",
            "completed",
            guidance,
            result_part.get("payload") or {},
        )
        messages = list(state.get("messages") or [])
        messages.append({"role": "user", "content": "工具结果：\n" + json.dumps(observation, ensure_ascii=False)})
        return {
            "messages": messages,
            "pending_part_id": None,
            "pending_permission_call": None,
            "execution_state": "running",
        }

    async def action_gate_node(self, state: AgentSessionGraphState) -> dict[str, Any]:
        session = self._session(state["session_id"])
        part_id = str(state.get("pending_part_id") or self._latest_part_id(session["id"], {"diff", "command"}, {"pending", "approved", "failed", "executed"}) or "")
        if not part_id:
            return {"execution_state": "running"}
        action_part = self.repository.get_part(part_id)
        payload = {
            "interrupt_kind": "action_approval",
            "session_id": session["id"],
            "part_id": part_id,
            "action_type": (action_part or {}).get("type"),
            "title": (action_part or {}).get("title"),
            "policy_reason": ((action_part or {}).get("payload") or {}).get("policy_reason"),
        }
        _ = interrupt(payload)
        action_part = self.repository.get_part(part_id)
        if not action_part:
            return {"pending_part_id": None, "execution_state": "failed", "final_summary": "待执行动作不存在，Agent 已停止。"}
        status = str(action_part.get("status") or "")
        if status in {"pending", "approved"}:
            return {"pending_part_id": part_id, "execution_state": "waiting_approval"}
        if status == "blocked":
            return {"pending_part_id": None, "execution_state": "failed", "final_summary": "动作已被拒绝，Agent 已停止。"}

        payload_data = dict(action_part.get("payload") or {})
        tool_name = "patch" if action_part.get("type") == "diff" else str(payload_data.get("tool") or "bash_command")
        summary = str(action_part.get("content") or payload_data.get("failure_summary") or "动作已执行。")
        observation_status = "completed" if status == "executed" else "failed"
        observation = self.processor._compact_observation(tool_name, observation_status, summary, payload_data, summary if observation_status == "failed" else None)
        messages = list(state.get("messages") or [])
        messages.append({"role": "user", "content": "工具结果：\n" + json.dumps(observation, ensure_ascii=False)})
        if action_part.get("type") == "diff" and status == "failed":
            return {"messages": messages, "pending_part_id": None, "execution_state": "needs_manual_review", "final_summary": summary}
        metadata = self.processor._ensure_metadata(self._session(session["id"]))
        metadata = set_phase(metadata, "repairing" if status == "failed" else "verifying")
        self.repository.update_session(session["id"], status="running", metadata=metadata)
        return {"messages": messages, "pending_part_id": None, "execution_state": "running"}

    async def finalize_node(self, state: AgentSessionGraphState) -> dict[str, Any]:
        session = self._session(state["session_id"])
        status = str(session.get("status") or "")
        if status in {"completed", "needs_manual_review", "failed"}:
            return {"execution_state": status}
        summary = str(state.get("final_summary") or "").strip() or "任务已完成。"
        summary_part = self.repository.add_part(
            session["id"],
            "summary",
            status="completed",
            title="最终结果",
            content=summary,
            payload={"summary": summary, "source": "langgraph"},
        )
        metadata = set_phase(self.processor._ensure_metadata(session), "completed")
        self.repository.update_session(session["id"], status="completed", metadata=metadata)
        self.processor._event(session["id"], "summary_completed", summary, {"part_id": summary_part["id"]})
        return {"execution_state": "completed", "final_summary": summary}

    async def execute_action_part(self, part_id: str) -> dict[str, Any]:
        part = self.repository.get_part(part_id)
        if not part:
            raise ValueError("Agent part not found")
        if part.get("type") not in {"diff", "command"} or part.get("status") != "approved":
            raise ValueError("Only approved action parts can be executed")
        session = self._session(str(part.get("session_id") or ""))
        payload = dict(part.get("payload") or {})
        if part.get("type") == "command":
            tool_name = str(payload.get("tool") or "bash_command")
            tool = self.processor.tools.get(tool_name)
            result = tool.execute({"payload": payload}, self.processor._context(session))  # type: ignore[union-attr]
            status = "executed" if result.status == "completed" else "failed"
            payload.update(result.payload)
            self.repository.update_part(part_id, status=status, payload=payload, content=result.summary if status == "executed" else result.error)
            metadata = record_command(self.processor._ensure_metadata(session), part_id, None if status == "executed" else result.error or result.summary)
            metadata = set_phase(metadata, "verifying" if status == "executed" else "repairing")
            self.repository.update_session(session["id"], status="running", metadata=metadata)
            self.processor._event(session["id"], "action_executed" if status == "executed" else "action_failed", result.summary, {"part_id": part_id, **result.payload})
            return self.repository.get_part(part_id) or part

        patch_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
        result = self.processor.tools.apply_patch_payload(patch_payload, self.processor._context(session))
        status = "executed" if result.status == "completed" else "failed"
        payload.update(result.payload)
        self.repository.update_part(part_id, status=status, payload=payload, content=result.summary if status == "executed" else result.error)
        metadata = record_diff(self.processor._ensure_metadata(session), part_id, payload.get("changed_files") or [])
        if status == "executed":
            metadata = set_phase(metadata, "verifying")
            self.repository.update_session(session["id"], status="running", metadata=metadata)
            self.processor._event(session["id"], "action_executed", result.summary, {"part_id": part_id, **result.payload})
        else:
            metadata = set_phase(metadata, "needs_manual_review")
            self.repository.update_session(session["id"], status="needs_manual_review", metadata=metadata)
            self.processor._event(session["id"], "action_failed", result.error or result.summary, {"part_id": part_id, **result.payload})
        return self.repository.get_part(part_id) or part

    def _session(self, session_id: str) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        return session

    async def _invoke_model(
        self,
        session: dict[str, Any],
        messages: list[dict[str, str]],
    ) -> tuple[str, list[str], str | None, list[dict[str, Any]], str, str | None, bool, str | None]:
        session_id = str(session["id"])
        invocation = self._invocation_context(session_id)
        stream_model_call = invocation.get("stream_model_call")
        if stream_model_call is not None:
            try:
                raw, streaming_part_id = await self.processor._stream_model_output(session_id, messages, stream_model_call)
                return self._parse_model_output(
                    raw,
                    streaming_part_id=streaming_part_id,
                    session_id=session_id,
                ) + (False, None)
            except Exception as exc:
                failed_part_id = getattr(self.processor, "_pending_stream_part_id", None)
                if failed_part_id:
                    self.repository.update_part(failed_part_id, status="failed", title="流式输出失败")
                self.processor._event(
                    session_id,
                    "model_stream_failed",
                    f"流式输出失败，回退到非流式：{str(exc)[:200]}",
                    {"error": str(exc)[:600], "part_id": failed_part_id},
                )
                self.processor._update_streaming_diagnostics(
                    session_id,
                    status="failed_then_fallback",
                    mode="non_stream",
                    fallback_to_non_stream=True,
                    error=str(exc)[:600],
                )
                raw, text_chunks, summary, tool_calls, finalized_type, streaming_part_id = await self._invoke_non_stream_model(session, messages)
                return raw, text_chunks, summary, tool_calls, finalized_type, streaming_part_id, True, str(exc)[:600]

        self.processor._event(session_id, "phase_change", "模型思考中", {"phase": "model_thinking"})
        raw, text_chunks, summary, tool_calls, finalized_type, streaming_part_id = await self._invoke_non_stream_model(session, messages)
        return raw, text_chunks, summary, tool_calls, finalized_type, streaming_part_id, False, None

    async def _invoke_non_stream_model(
        self,
        session: dict[str, Any],
        messages: list[dict[str, str]],
    ) -> tuple[str, list[str], str | None, list[dict[str, Any]], str, str | None]:
        invocation = self._invocation_context(str(session["id"]))
        model_call = invocation.get("model_call") or self.model_call
        if model_call is not None:
            raw = await model_call(messages)
            return self._parse_model_output(raw, session_id=str(session["id"]))

        context = RuntimeExecutionContext(
            workflow_id=session["id"],
            goal=str((session.get("metadata") or {}).get("current_goal") or session.get("title") or ""),
            project_path=session.get("project_path"),
            provider=str(session.get("provider") or ""),
            model=session.get("model"),
            metadata={"source": "agent_session_langgraph"},
        )
        model = get_chat_model(context).bind_tools(self._tool_schemas())
        response = await model.ainvoke(self._to_langchain_messages(messages))
        ai_message = response if isinstance(response, AIMessage) else AIMessage(content=str(response))
        content = str(ai_message.content or "")
        raw, text_chunks, summary, tool_calls, finalized_type, streaming_part_id = self._parse_model_output(
            content,
            session_id=str(session["id"]),
        )
        if ai_message.tool_calls:
            tool_calls = [
                {"name": str(call.get("name") or ""), "args": dict(call.get("args") or {}), "id": str(call.get("id") or f"tool_{index}")}
                for index, call in enumerate(ai_message.tool_calls or [])
            ]
        return raw, text_chunks, summary, tool_calls, finalized_type, streaming_part_id

    def _parse_model_output(
        self,
        raw: str,
        *,
        session_id: str,
        streaming_part_id: str | None = None,
    ) -> tuple[str, list[str], str | None, list[dict[str, Any]], str, str | None]:
        parts = parse_agent_response(raw)
        finalized_type = self.processor._finalize_streaming_text_part(session_id, raw, parts, streaming_part_id)
        text_chunks = [part.content for part in parts if part.type == "text" and part.content.strip()]
        summary = next(
            (part.content.strip() or str((part.payload or {}).get("summary") or "") for part in parts if part.type == "summary"),
            None,
        )
        tool_calls = [
            {"name": str(part.tool or ""), "args": dict(part.arguments or {}), "id": f"tool_{index}"}
            for index, part in enumerate(parts)
            if part.type == "tool_call" and part.tool
        ]
        if not parts and raw.strip():
            text_chunks = [raw]
        if finalized_type == "summary":
            tool_calls = []
        return raw, text_chunks, summary, tool_calls, finalized_type, streaming_part_id

    def _tool_schemas(self) -> list[dict[str, Any]]:
        schemas: list[dict[str, Any]] = []
        for tool in self.processor.tools.list():
            properties = {
                key: {"type": value if value in {"string", "array", "object", "number", "boolean"} else "string"}
                for key, value in (tool.input_schema or {}).items()
            }
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": {"type": "object", "properties": properties, "additionalProperties": True},
                    },
                }
            )
        return schemas

    @staticmethod
    def _to_langchain_messages(messages: list[dict[str, str]]) -> list[Any]:
        converted: list[Any] = []
        for message in messages:
            role = str(message.get("role") or "user")
            content = str(message.get("content") or "")
            if role == "system":
                converted.append(SystemMessage(content=content))
            elif role == "assistant":
                converted.append(AIMessage(content=content))
            else:
                converted.append(HumanMessage(content=content))
        return converted

    def _latest_part_id(self, session_id: str, part_types: set[str], statuses: set[str]) -> str | None:
        for part in reversed(self.repository.list_parts(session_id)):
            if str(part.get("type")) in part_types and str(part.get("status") or "") in statuses:
                return str(part.get("id") or "")
        return None

    def _latest_summary(self, session_id: str, result: dict[str, Any] | None = None) -> str | None:
        if isinstance(result, dict):
            parts = list(result.get("parts") or [])
            for part in reversed(parts):
                if str(part.get("type")) == "summary":
                    return str(part.get("content") or "")
        for part in reversed(self.repository.list_parts(session_id)):
            if str(part.get("type")) == "summary":
                return str(part.get("content") or "")
        return None

    def _invocation_context(self, session_id: str) -> dict[str, Any]:
        return dict(self._invocation_contexts.get(session_id) or {})
