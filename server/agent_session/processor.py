from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, Awaitable, Callable

from .policy import evaluate_agent_action_policy
from .parser import parse_agent_response
from .command_policy import command_allowed, normalize_command, resolve_command_cwd, summarize_failure
from .repository import AgentSessionRepository
from .state import (
    DEFAULT_MAX_REPAIR_ATTEMPTS,
    add_touched_paths,
    ensure_session_state,
    record_command,
    record_diff,
    record_fallback_summary,
    record_repair_attempt,
    set_phase,
)
from .terminal_manager import terminal_manager, terminal_result_payload
from .tools import AgentToolRegistry


ModelCall = Callable[[list[dict[str, str]]], Awaitable[str]]
StreamModelCall = Callable[[list[dict[str, str]]], AsyncGenerator[dict[str, Any], None]]

logger = logging.getLogger(__name__)

_STREAM_THROTTLE_INTERVAL = 0.08
_STREAM_THROTTLE_CHARS = 24


READ_TOOLS = {"read", "search", "glob", "collect_context", "read_execution", "find_symbol", "find_references", "http_probe", "probe_json_endpoint", "read_local_page", "browser_validate_page", "capture_network_errors", "browser_click", "browser_fill", "browser_wait_for", "collect_test_failures", "summarize_test_results"}
CONTEXT_TOOLS = {"read", "search", "glob", "collect_context", "detect_project_commands", "find_symbol", "find_references", "http_probe", "probe_json_endpoint", "read_local_page", "browser_validate_page", "capture_network_errors", "browser_click", "browser_fill", "browser_wait_for", "collect_test_failures", "summarize_test_results"}
MAX_REPAIR_ATTEMPTS = DEFAULT_MAX_REPAIR_ATTEMPTS
MAX_PROTOCOL_REPAIRS = 4


class AgentSessionProcessor:
    def __init__(
        self,
        repository: AgentSessionRepository,
        tools: AgentToolRegistry | None = None,
        max_iterations: int = 8,
        event_callback: Any | None = None,
    ):
        self.repository = repository
        self.tools = tools or AgentToolRegistry(repository=repository)
        self.max_iterations = max_iterations
        self._event_callback = event_callback

    async def prompt(
        self,
        session_id: str,
        content: str,
        *,
        model_call: ModelCall | None = None,
        stream_model_call: StreamModelCall | None = None,
    ) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        if self._interrupt_requested(session):
            return self._interrupt_summary(session_id)
        metadata = self._ensure_metadata(session)
        metadata["current_goal"] = content
        metadata["task_intent"] = self._classify_task_intent(content)
        metadata = set_phase(metadata, "running")
        session = self.repository.update_session(session_id, status="running", metadata=metadata)
        request_part = self.repository.add_part(session_id, "text", status="completed", title="请求", content=content)
        self._event(session_id, "session_started", "Agent 开始处理请求", {"content": content, "part_id": request_part["id"]})
        logger.info(
            "agent_session.processor.prompt invoked: session_id=%s model_call=%s stream_model_call=%s",
            session_id,
            bool(model_call),
            bool(stream_model_call),
        )
        runner = getattr(self, "_graph_runner", None)
        if runner is not None and hasattr(runner, "run_prompt_legacy"):
            logger.info("agent_session.processor.prompt delegated to LangGraph entry: session_id=%s", session_id)
            self._event(session_id, "phase_change", "尝试使用 LangGraph 执行链路", {"phase": "langgraph_dispatch"})
            return await runner.run_prompt_legacy(session_id, content, model_call=model_call, stream_model_call=stream_model_call)
        logger.info("agent_session.processor.prompt using processor legacy fallback path: session_id=%s", session_id)
        return await self._run_prompt_legacy(
            session_id,
            content,
            session=session,
            model_call=model_call,
            stream_model_call=stream_model_call,
        )

    async def _run_prompt_legacy(
        self,
        session_id: str,
        content: str,
        *,
        session: dict[str, Any],
        model_call: ModelCall | None = None,
        stream_model_call: StreamModelCall | None = None,
    ) -> dict[str, Any]:
        return await self._run_prompt_legacy_loop(session_id, content, session=session, model_call=model_call, stream_model_call=stream_model_call)

    async def _run_prompt_legacy_loop(
        self,
        session_id: str,
        content: str,
        *,
        session: dict[str, Any],
        model_call: ModelCall | None = None,
        stream_model_call: StreamModelCall | None = None,
    ) -> dict[str, Any]:
        metadata = self._ensure_metadata(session)
        if metadata.get("runtime") == "langgraph":
            self._event(session_id, "phase_change", "旧兼容入口已转交 LangGraph 执行", {"phase": "langgraph"})
            return self._with_parts(session_id)

        logger.warning(
            "agent_session.processor legacy prompt entered unexpectedly: session_id=%s provider=%s model=%s stream=%s",
            session_id,
            session.get("provider") or "",
            session.get("model") or "",
            bool(stream_model_call),
        )
        messages = self._initial_messages(session, content)
        self._event(
            session_id,
            "phase_change",
            "旧兼容入口已进入，等待 LangGraph 迁移完成",
            {
                "phase": "langgraph_migration",
                "runtime": "legacy",
                "has_model_call": bool(model_call),
                "has_stream_model_call": bool(stream_model_call),
            },
        )
        active_model_call = model_call or self._fallback_model_call

        for iteration in range(self.max_iterations):
            interrupted = self._maybe_interrupt(session_id)
            if interrupted is not None:
                return interrupted

            raw = ""
            streaming_part_id: str | None = None
            if stream_model_call is not None:
                try:
                    logger.info(
                        "agent_session.processor legacy prompt entering chat_stream: session_id=%s iteration=%s",
                        session_id,
                        iteration + 1,
                    )
                    raw, streaming_part_id = await self._stream_model_output(session_id, messages, stream_model_call)
                    logger.info("agent_session.processor legacy prompt chat_stream completed: session_id=%s", session_id)
                except Exception as exc:
                    failed_part_id = getattr(self, "_pending_stream_part_id", None)
                    if failed_part_id:
                        self.repository.update_part(failed_part_id, status="failed", title="流式输出失败")
                    self._pending_stream_part_id = None
                    logger.exception("agent_session.processor legacy prompt chat_stream failed: session_id=%s", session_id)
                    self._event(
                        session_id,
                        "model_stream_failed",
                        "legacy chat_stream 失败，回退到 model_call",
                        {"error": str(exc)[:600], "part_id": failed_part_id},
                    )
                    self._update_streaming_diagnostics(
                        session_id,
                        status="failed_then_fallback",
                        mode="non_stream",
                        fallback_to_non_stream=True,
                        error=str(exc)[:600],
                    )

            if not raw:
                logger.info(
                    "agent_session.processor legacy prompt entering model_call: session_id=%s iteration=%s",
                    session_id,
                    iteration + 1,
                )
                raw = await active_model_call(messages)
                logger.info("agent_session.processor legacy prompt model_call completed: session_id=%s", session_id)

            parts = parse_agent_response(raw)
            finalized_type = self._finalize_streaming_text_part(session_id, raw, parts, streaming_part_id)
            if finalized_type == "summary":
                summary_part = self.repository.get_part(streaming_part_id) if streaming_part_id else None
                summary_text = str((summary_part or {}).get("content") or raw.strip() or "任务已完成。")
                metadata = set_phase(self._ensure_metadata(self.repository.get_session(session_id) or session), "completed")
                self.repository.update_session(session_id, status="completed", metadata=metadata)
                self._event(session_id, "summary_completed", summary_text, {"part_id": streaming_part_id or "", "streaming": True})
                return self._with_parts(session_id)

            if not parts:
                handled = self._handle_protocol_miss(session_id, raw, messages)
                if handled is not None:
                    return handled
                continue

            text_index = 0
            next_model = False
            session_finalized = False
            for part_index, part in enumerate(parts):
                if session_finalized and part.type == "tool_call" and part.tool:
                    self._event(session_id, "tool_call_ignored", f"工具 {part.tool} 在 finalize 后被忽略", {"tool": part.tool, "arguments": part.arguments or {}})
                    continue
                if part.type == "text":
                    content_text = part.content.strip()
                    if content_text and not streaming_part_id:
                        text_part = self.repository.add_part(
                            session_id,
                            "text",
                            status="completed",
                            title="说明",
                            content=content_text,
                            payload={"part_index": text_index, "source": "legacy_processor"},
                        )
                        text_index += 1
                        self._event(session_id, "part_created", content_text, {"part_id": text_part["id"], "part_type": "text", "status": "completed"})
                    continue
                if part.type == "summary":
                    summary_text = part.content.strip() or str((part.payload or {}).get("summary") or "") or raw.strip() or "任务已完成。"
                    summary_part = self.repository.add_part(
                        session_id,
                        "summary",
                        status="completed",
                        title="最终结果",
                        content=summary_text,
                        payload={"summary": summary_text, "part_index": part_index},
                    )
                    metadata = set_phase(self._ensure_metadata(self.repository.get_session(session_id) or session), "completed")
                    self.repository.update_session(session_id, status="completed", metadata=metadata)
                    self._event(session_id, "summary_completed", summary_text, {"part_id": summary_part["id"]})
                    session_finalized = True
                    continue
                if part.type != "tool_call" or not part.tool:
                    continue
                handled, should_continue = self._execute_tool_request(
                    session_id,
                    {"tool": part.tool, "arguments": dict(part.arguments or {})},
                    raw,
                    messages,
                    part_index=part_index,
                )
                if handled is not None:
                    result_parts = self.repository.list_parts(session_id)
                    has_summary = any(p.get("type") == "summary" for p in result_parts)
                    if has_summary:
                        session_finalized = True
                        continue
                    return handled
                next_model = next_model or should_continue

            if session_finalized:
                return self._with_parts(session_id)
            if next_model or any(part.type == "tool_call" for part in parts):
                continue

            handled = self._handle_protocol_miss(session_id, raw, messages)
            if handled is not None:
                return handled

        logger.warning("agent_session.processor legacy prompt reached max iterations: session_id=%s", session_id)
        return self._fallback_summary(session_id, "Agent 达到最大工具轮次，已根据当前执行记录生成总结。")

    def _execute_tool_request(
        self,
        session_id: str,
        request: dict[str, Any],
        raw: str,
        messages: list[dict[str, str]],
        *,
        part_index: int = 0,
    ) -> tuple[dict[str, Any] | None, bool]:
        session = self.repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        interrupted = self._maybe_interrupt(session_id)
        if interrupted is not None:
            return interrupted, False
        tool_name = request["tool"]
        args = request["arguments"]
        tool = self.tools.get(tool_name)
        if tool is None:
            part = self.repository.add_part(
                session_id,
                "permission",
                status="pending",
                title=f"未知工具：{tool_name}",
                content="该工具不在内置工具列表中，需要人工确认。",
                payload={"tool": tool_name, "arguments": args, "part_index": part_index},
            )
            self.repository.update_session(session_id, status="waiting_permission")
            self._event(session_id, "permission_asked", f"未知工具需要确认：{tool_name}", {"part_id": part["id"]})
            return self._with_parts(session_id), False

        metadata = self._ensure_metadata(session)
        if tool_name == "patch" and not metadata.get("had_context"):
            metadata = set_phase(metadata, "inspecting")
            self.repository.update_session(session_id, metadata=metadata)
            guidance = "请先读取项目上下文或目标文件，再生成补丁。"
            result_part = self.repository.add_part(
                session_id,
                "tool_result",
                status="completed",
                title="需要上下文",
                content=guidance,
                payload={"guidance": guidance, "required_tools": ["collect_context", "read", "search"], "part_index": part_index},
            )
            self._event(session_id, "tool_call_completed", guidance, {"part_id": result_part["id"], "tool": tool_name})
            observation = self._compact_observation(tool_name, "blocked", guidance, result_part["payload"])
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "工具结果：\n" + json.dumps(observation, ensure_ascii=False)})
            return None, True
        if tool_name == "patch":
            missing_context = self._missing_patch_context(args, set(metadata.get("touched_paths") or []))
            if missing_context:
                metadata = set_phase(metadata, "inspecting")
                self.repository.update_session(session_id, metadata=metadata)
                guidance = f"补丁目标 {', '.join(missing_context)} 还没有在本轮被读取或搜索命中。请先 read 或 search 这些相关文件，再生成补丁。"
                result_part = self.repository.add_part(
                    session_id,
                    "tool_result",
                    status="completed",
                    title="需要更多上下文",
                    content=guidance,
                    payload={"guidance": guidance, "missing_context": missing_context, "required_tools": ["read", "search", "collect_context"], "part_index": part_index},
                )
                self._event(session_id, "tool_call_completed", guidance, {"part_id": result_part["id"], "tool": tool_name})
                observation = self._compact_observation(tool_name, "blocked", guidance, result_part["payload"])
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": "工具结果：\n" + json.dumps(observation, ensure_ascii=False)})
                return None, True
        if tool_name == "bash_command":
            command_payload = args.get("payload") if isinstance(args.get("payload"), dict) else args
            if isinstance(command_payload.get("command"), str):
                metadata = set_phase(metadata, "running")
                metadata["command_protocol_repair_count"] = int(metadata.get("command_protocol_repair_count") or 0) + 1
                self.repository.update_session(session_id, metadata=metadata)
                guidance = (
                    "bash_command 的 command 必须是 argv 数组，不能是 shell 字符串，也不能使用 &&、>、|。"
                    "如果目标是写文件，请改用 patch 工具；如果目标是验证，请使用如 "
                    '{"command":["npm","run","typecheck"]} 的数组格式。'
                )
                result_part = self.repository.add_part(
                    session_id,
                    "tool_result",
                    status="completed",
                    title="命令格式需要修正",
                    content=guidance,
                    payload={
                        "guidance": guidance,
                        "invalid_command": command_payload.get("command"),
                        "required_format": {"command": ["npm", "run", "typecheck"]},
                        "part_index": part_index,
                    },
                )
                self._event(session_id, "tool_call_completed", guidance, {"part_id": result_part["id"], "tool": tool_name})
                observation = self._compact_observation(tool_name, "blocked", guidance, result_part["payload"])
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": "工具结果：\n" + json.dumps(observation, ensure_ascii=False)})
                return None, True
        if tool_name == "bash_command" and not metadata.get("detected_commands"):
            command_payload = args.get("payload") if isinstance(args.get("payload"), dict) else args
            pre_policy = evaluate_agent_action_policy(session, "command", command_payload, set(metadata.get("touched_paths") or []))
            if pre_policy["execution_mode"] != "blocked":
                guidance = "请先调用 detect_project_commands 或 collect_context 识别当前项目可用的验证命令，再提出 bash_command。"
                result_part = self.repository.add_part(
                    session_id,
                    "tool_result",
                    status="completed",
                    title="需要识别验证命令",
                    content=guidance,
                    payload={"guidance": guidance, "required_tools": ["detect_project_commands", "collect_context"], "part_index": part_index},
                )
                self._event(session_id, "tool_call_completed", guidance, {"part_id": result_part["id"], "tool": tool_name})
                observation = self._compact_observation(tool_name, "blocked", guidance, result_part["payload"])
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": "工具结果：\n" + json.dumps(observation, ensure_ascii=False)})
                return None, True

        call_part = self.repository.add_part(
            session_id,
            "tool_call",
            status="running",
            title=tool.description,
            content=self._tool_call_text(tool_name, args),
            payload={"tool": tool_name, "arguments": args, "part_index": part_index},
        )
        self._event(session_id, "tool_call_started", call_part.get("content") or tool.description, {"part_id": call_part["id"], "tool": tool_name, "detail": self._tool_summary(args)})
        self._event(session_id, "phase_change", f"执行工具：{tool_name}", {"phase": "tool_execution", "tool": tool_name, "detail": self._tool_summary(args)})

        if tool.permission == "command":
            if tool_name == "run_targeted_test":
                prepared = tool.execute(args, self._context(session))
                if prepared.status != "completed":
                    self.repository.update_part(call_part["id"], status=prepared.status)
                    result_part = self.repository.add_part(
                        session_id,
                        "tool_result",
                        status=prepared.status,
                        title=tool.description,
                        content=prepared.summary,
                        payload={**prepared.payload, "part_index": part_index},
                    )
                    self._event(session_id, "tool_call_completed", prepared.summary, {"part_id": result_part["id"], "tool": tool_name})
                    observation = self._compact_observation(tool_name, prepared.status, prepared.summary, prepared.payload, prepared.error)
                    messages.append({"role": "assistant", "content": raw})
                    messages.append({"role": "user", "content": "工具结果：\n" + json.dumps(observation, ensure_ascii=False)})
                    return None, False
                command_payload = dict(prepared.payload)
            else:
                command_payload = args.get("payload") if isinstance(args.get("payload"), dict) else dict(args)
            command_payload.setdefault("tool", tool_name)
            if tool_name == "run_dev_server":
                command_payload.setdefault("command", ["npm", "run", "dev"])
                command_payload["long_running"] = True
            policy = evaluate_agent_action_policy(session, "command", command_payload, set(metadata.get("touched_paths") or []))
            result = self._handle_command(session, call_part["id"], command_payload, policy, tool, messages, raw, tool_name=tool_name)
            return result, result is None

        result = tool.execute(args, self._context(session))
        self.repository.update_part(call_part["id"], status=result.status)

        if tool_name == "patch":
            patch_payload = dict(result.payload)
            policy = evaluate_agent_action_policy(session, "diff", patch_payload, set(metadata.get("touched_paths") or []))
            part_payload = dict(result.payload)
            part_payload.update(policy)
            part_payload["part_index"] = part_index
            part = self.repository.add_part(
                session_id,
                "diff",
                status="pending",
                title=str(args.get("title") or "补丁建议"),
                content=result.summary,
                payload=part_payload,
            )
            metadata = record_diff(self._ensure_metadata(self.repository.get_session(session_id) or session), part["id"])
            if policy["execution_mode"] == "blocked":
                metadata = set_phase(metadata, "needs_manual_review")
                self.repository.update_session(session_id, metadata=metadata)
                self.repository.update_part(part["id"], status="blocked", content=policy["policy_reason"])
                return self._stop_with_summary(session_id, "needs_manual_review", policy["policy_reason"], part_id=part["id"]), False
            if policy["execution_mode"] == "approval_required":
                metadata = set_phase(metadata, "waiting_approval")
                self.repository.update_session(session_id, status="waiting_approval", metadata=metadata)
                self._event(session_id, "action_proposed", policy["policy_reason"], {"part_id": part["id"], **policy})
                return self._with_parts(session_id), False
            patch_result = self.tools.apply_patch_payload(patch_payload, self._context(session))
            applied_payload = dict(part_payload)
            applied_payload.update(patch_result.payload)
            status = "executed" if patch_result.status == "completed" else "failed"
            self.repository.update_part(part["id"], status=status, payload=applied_payload, content=patch_result.summary if status == "executed" else patch_result.error)
            if status == "failed":
                metadata = set_phase(self._ensure_metadata(self.repository.get_session(session_id) or session), "needs_manual_review")
                metadata = record_diff(metadata, part["id"], applied_payload.get("changed_files") or [])
                self.repository.update_session(session_id, metadata=metadata)
                return self._stop_with_summary(session_id, "needs_manual_review", patch_result.error or "补丁执行失败", part_id=part["id"]), False
            metadata = set_phase(self._ensure_metadata(self.repository.get_session(session_id) or session), "verifying")
            metadata = record_diff(metadata, part["id"], applied_payload.get("changed_files") or [])
            self.repository.update_session(session_id, metadata=metadata)
            self._event(session_id, "action_executed", patch_result.summary, {"part_id": part["id"], **applied_payload})
            observation = self._compact_observation(
                tool_name,
                "completed",
                "补丁已自动执行。下一步必须提出一个白名单验证命令；优先使用已识别的 commands。",
                {**applied_payload, "available_commands": (metadata.get("detected_commands") or [])},
            )
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "工具结果：\n" + json.dumps(observation, ensure_ascii=False)})
            return None, False

        if tool_name == "finalize":
            summary = self.repository.add_part(session_id, "summary", status="completed", title="最终结果", content=result.summary, payload={**result.payload, "part_index": part_index})
            metadata = set_phase(self._ensure_metadata(self.repository.get_session(session_id) or session), "completed")
            self.repository.update_session(session_id, status="completed", metadata=metadata)
            self._event(session_id, "summary_completed", result.summary, {"part_id": summary["id"]})
            return self._with_parts(session_id), False

        result_part = self.repository.add_part(
            session_id,
            "tool_result",
            status=result.status,
            title=tool.description,
            content=result.summary,
            payload={**result.payload, "part_index": part_index},
        )
        self._event(session_id, "tool_call_completed", result.summary, {"part_id": result_part["id"], "tool": tool_name})
        if tool_name in CONTEXT_TOOLS and result.status == "completed":
            self._record_context(session_id, result.payload)
        guidance_payload = self._next_tool_guidance(tool_name, result.status, result.payload, result.error)
        result_payload = dict(result.payload)
        if guidance_payload:
            result_payload.update(guidance_payload)
            self.repository.update_part(result_part["id"], payload={**result_payload, "part_index": part_index})
        observation = self._compact_observation(tool_name, result.status, result.summary, result_payload, result.error)
        messages.append({"role": "assistant", "content": raw})
        if guidance_payload:
            messages.append({"role": "user", "content": "工具结果：\n" + json.dumps({**observation, "guidance": guidance_payload.get("guidance"), "recommended_tools": guidance_payload.get("recommended_tools") or []}, ensure_ascii=False)})
        else:
            messages.append({"role": "user", "content": "工具结果：\n" + json.dumps(observation, ensure_ascii=False)})
        self._event(session_id, "phase_change", "工具执行完成，准备继续", {"phase": "tool_completed", "tool": tool_name})
        return None, False

    def approve_part(self, part_id: str, approved: bool) -> dict[str, Any]:
        part = self.repository.get_part(part_id)
        if not part:
            raise ValueError("Agent part not found")
        session_id = part["session_id"]
        if not approved:
            self.repository.update_part(part_id, status="blocked")
            metadata = set_phase(self._ensure_metadata(self.repository.get_session(session_id) or {}), "failed")
            self.repository.update_session(session_id, status="failed", metadata=metadata)
            self._event(session_id, "action_rejected", "动作已拒绝", {"part_id": part_id, "compatibility_mode": True})
            return self._with_parts(session_id)
        self.repository.update_part(part_id, status="approved")
        metadata = set_phase(self._ensure_metadata(self.repository.get_session(session_id) or {}), "waiting_approval")
        self.repository.update_session(session_id, status="waiting_approval", metadata=metadata)
        self._event(session_id, "action_approved", "动作已批准", {"part_id": part_id, "compatibility_mode": True})
        return self._with_parts(session_id)

    def execute_part(self, part_id: str) -> dict[str, Any]:
        part = self.repository.get_part(part_id)
        if not part:
            raise ValueError("Agent part not found")
        if part.get("status") == "executed":
            return self._with_parts(part["session_id"])
        if part.get("type") not in {"diff", "command"} or part.get("status") != "approved":
            raise ValueError("Only approved action parts can be executed")
        session = self.repository.get_session(part["session_id"]) or {}
        if part.get("type") == "command":
            self._start_command_terminal(session, part)
            return self._with_parts(part["session_id"])
        else:
            outer_payload = dict(part.get("payload") or {})
            hunk_decisions = {k: str(v) for k, v in (outer_payload.pop("hunk_decisions", None) or {}).items()}
            raw_payload = outer_payload.get("payload") or outer_payload
            result = self.tools.apply_patch_payload_with_decisions(raw_payload, self._context(session), hunk_decisions)
        status = "executed" if result.status == "completed" else "failed"
        payload = dict(part.get("payload") or {})
        payload.update(result.payload)
        self.repository.update_part(part_id, status=status, payload=payload, content=result.summary if result.status == "completed" else result.error)
        metadata = self._ensure_metadata(session)
        if part.get("type") == "command":
            metadata = record_command(metadata, part_id, None if status == "executed" else result.error or result.summary)
        else:
            metadata = record_diff(metadata, part_id, payload.get("changed_files") or [])
        metadata = set_phase(metadata, "completed" if status == "executed" else "failed")
        self.repository.update_session(part["session_id"], status="completed" if status == "executed" else "failed", metadata=metadata)
        self._event(part["session_id"], "action_executed" if status == "executed" else "action_failed", result.summary, {"part_id": part_id, **result.payload})
        return self._with_parts(part["session_id"])

    def _start_command_terminal(self, session: dict[str, Any], part: dict[str, Any]) -> None:
        payload = dict(part.get("payload") or {})
        command = normalize_command(payload.get("command"))
        if not command_allowed(command):
            raise ValueError("Command is not allowlisted")
        root = Path(str(session.get("project_path") or Path.cwd())).resolve()
        command_root = resolve_command_cwd(root, command)
        timeout_seconds = int(payload.get("timeout_seconds") or 120)

        def on_exit(terminal_session: Any) -> None:
            result_payload = terminal_result_payload(terminal_session)
            current_part = self.repository.get_part(part["id"]) or part
            final_payload = dict(current_part.get("payload") or {})
            final_payload.update(result_payload)
            exit_code = terminal_session.exit_code if terminal_session.exit_code is not None else 1
            status = "executed" if exit_code == 0 else "failed"
            failure = result_payload.get("failure_summary") or summarize_failure(terminal_session.stdout, terminal_session.stderr)
            summary = "命令执行完成" if status == "executed" else failure or "命令执行失败"
            self.repository.update_part(part["id"], status=status, payload=final_payload, content=summary)
            metadata = record_command(
                self._ensure_metadata(self.repository.get_session(part["session_id"]) or session),
                part["id"],
                None if status == "executed" else summary,
            )
            metadata = set_phase(metadata, "completed" if status == "executed" else "failed")
            self.repository.update_session(part["session_id"], status="completed" if status == "executed" else "failed", metadata=metadata)
            self._event(part["session_id"], "action_executed" if status == "executed" else "action_failed", summary, {"part_id": part["id"], **final_payload})

        def on_output(terminal_session: Any, data: str) -> None:
            self._event(
                part["session_id"],
                "command_output",
                "",
                {"part_id": part["id"], "terminal_id": terminal_session.id, "delta": data},
            )

        terminal_session = terminal_manager.start(
            part_id=part["id"],
            session_id=part["session_id"],
            command=command,
            cwd=command_root,
            timeout_seconds=timeout_seconds,
            on_output=on_output,
            on_exit=on_exit,
        )
        running_payload = {
            **payload,
            "terminal_id": terminal_session.id,
            "interactive": terminal_session.interactive,
            "command": command,
            "cwd": str(command_root),
        }
        current_part = self.repository.get_part(part["id"]) or part
        if current_part.get("status") in {"executed", "failed"}:
            current_payload = dict(current_part.get("payload") or {})
            current_payload.update({k: v for k, v in running_payload.items() if k not in current_payload})
            self.repository.update_part(part["id"], payload=current_payload)
            return
        self.repository.update_part(part["id"], status="running", payload=running_payload, content="命令正在交互式终端中运行")
        metadata = set_phase(self._ensure_metadata(self.repository.get_session(part["session_id"]) or session), "verifying")
        self.repository.update_session(part["session_id"], status="verifying", metadata=metadata)
        self._event(part["session_id"], "command_started", "命令已在交互式终端中启动", {"part_id": part["id"], **running_payload})

    def _initial_messages(self, session: dict[str, Any], content: str) -> list[dict[str, str]]:
        tool_names = [tool.name for tool in self.tools.list()]
        metadata = self._ensure_metadata(session)
        intent = metadata.get("task_intent") or self._classify_task_intent(content)
        intent_guidance = {
            "analyze": "本任务是只读分析；允许 collect_context 后直接 finalize，不要 patch。",
            "verify": "本任务偏验证；优先 detect_project_commands，再 bash_command，成功后 finalize。",
            "develop": "本任务是开发任务；除非确认无需修改，否则需要 patch 或 bash_command。",
        }.get(str(intent), "默认先 collect_context，再按需要 patch/bash_command，完成时 finalize。")
        return [
            {
                "role": "system",
                "content": (
                    "## 你的身份\n"
                    "你是一位资深全栈软件工程师，与用户是平等的结对编程搭档。"
                    "你直接动手解决问题，用简洁专业的工程师口吻交流。\n\n"

                    "## 自然语言输出规范（最高优先级）\n"
                    "1. **严禁**在自然语言中提及任何内部工具名称"
                    "（如 read, search, glob, patch, bash_command, collect_context, finalize 等）。\n"
                    "2. **严禁**解释内部协议或 JSON 格式机制。\n"
                    "3. **严禁**在聊天文本中输出超过 5 行的代码。"
                    "所有代码修改必须通过 patch 工具提交，由编辑器展示 Diff。\n"
                    "4. 执行只读操作（浏览文件、搜索代码）时**保持完全静默**，"
                    "不要输出“我正在查看…”“让我先看看…”之类的过程描述。"
                    "直接输出工具 JSON 即可，不需要任何自然语言陪伴。\n"
                    "5. 只在以下时机输出自然语言：\n"
                    "   - 简要说明你的修改意图和设计决策（1-3 句话）\n"
                    "   - 汇报验证结果\n"
                    "   - 需要用户确认或决策时\n"
                    "6. 说话示范：\n"
                    '   - ✅ "我将重构数据加载模块，把同步 I/O 改为异步流式读取，避免大文件时的内存溢出。"\n'
                    '   - ❌ "我现在要调用 read 工具读取 main.py 文件的内容"\n'
                    '   - ❌ "接下来我会使用 patch 工具来修改代码"\n\n'

                    "## 工具调用协议（内部机制，不要向用户解释）\n"
                    "输出 JSON 对象执行操作，直接输出，不要用 markdown 代码块包裹：\n"
                    '{"tool": "工具名", "arguments": {"参数名": "参数值"}}\n\n'
                    "批量调用时输出 JSON 数组：\n"
                    '[{"tool": "工具1", "arguments": {...}}, {"tool": "工具2", "arguments": {...}}]\n\n'

                    "## 工作流程\n"
                    "1. 先理解项目结构和上下文\n"
                    "2. 阅读相关源码和类型定义\n"
                    "3. 提交代码修改\n"
                    "4. 运行验证（编译检查、测试）\n"
                    "5. 验证通过后总结完成\n\n"

                    "## 工具速查\n"
                    f"- collect_context — 收集项目上下文\n"
                    f"- read — 读取文件\n"
                    f"- search — 搜索代码\n"
                    f"- glob — 查找文件\n"
                    f"- patch — 修改文件（必须先 read 相关文件）\n"
                    f"- bash_command — 运行命令（command 必须是 argv 数组）\n"
                    f"- finalize — 完成任务（需要 summary 参数）\n\n"

                    "## 命令格式示例\n"
                    '{"tool": "bash_command", "arguments": {"command": ["npm", "run", "typecheck"]}}\n'
                    '{"tool": "bash_command", "arguments": {"command": ["pytest", "server/tests/test_device.py", "-v"]}}\n\n'
                    "## patch 格式示例\n"
                    '{"tool": "patch", "arguments": {"file_path": "server/main.py", "old_string": "旧代码", "new_string": "新代码"}}\n\n'

                    "## 核心规则\n"
                    "- 不要把自然语言混入 JSON 工具对象\n"
                    "- bash_command 的 command 必须是数组，禁止 shell 字符串、&&、管道\n"
                    "- patch 前必须先读取相关文件\n"
                    "- patch 后必须运行验证命令\n"
                    "- 验证通过后必须 finalize\n"
                    "- 同一轮可批量调用只读工具\n\n"
                    f"{intent_guidance}\n"
                    f"可用工具：{', '.join(tool_names)}"
                ),
            },
            {"role": "user", "content": content},
        ]


    async def _stream_model_output(
        self,
        session_id: str,
        messages: list[dict[str, str]],
        stream_model_call,
    ) -> tuple[str, str]:
        logger.info("agent_session.processor entering chat_stream: session_id=%s message_count=%s", session_id, len(messages))
        self._event(session_id, "phase_change", "模型思考中", {"phase": "model_thinking"})
        text_part = self.repository.add_part(
            session_id, "text", status="running", title="生成中",
            content="", payload={"streaming": True},
        )
        self._pending_stream_part_id = text_part["id"]
        self._event(
            session_id, "model_stream_started", "流式输出开始",
            {"part_id": text_part["id"], "part_type": "text", "status": "running", "streaming": True},
        )
        self._update_streaming_diagnostics(
            session_id,
            status="streaming",
            mode="chat_stream",
            fallback_to_non_stream=False,
            current_part_id=text_part["id"],
        )

        accumulated = ""
        last_flush_time = time.monotonic()
        chars_since_flush = 0

        async for delta_chunk in stream_model_call(messages):
            if self._interrupt_requested(self.repository.get_session(session_id) or {}):
                self.repository.update_part(text_part["id"], status="completed", title="已中断")
                self._event(
                    session_id,
                    "session_interrupted",
                    "用户已中断 Agent 任务。",
                    {"part_id": text_part["id"], "part_type": "text", "status": "completed", "interrupted": True},
                )
                break
            content_delta = delta_chunk.get("content", "")
            if not content_delta:
                continue
            accumulated += content_delta
            chars_since_flush += len(content_delta)
            now = time.monotonic()
            should_flush = (now - last_flush_time >= _STREAM_THROTTLE_INTERVAL) or (chars_since_flush >= _STREAM_THROTTLE_CHARS)
            if should_flush:
                self.repository.update_part(text_part["id"], content=accumulated)
                self._event(session_id, "part_delta", content_delta, {
                    "part_id": text_part["id"], "part_type": "text",
                    "delta": content_delta, "content": accumulated,
                    "status": "running", "streaming": True,
                })
                last_flush_time = now
                chars_since_flush = 0

        self.repository.update_part(text_part["id"], status="completed", content=accumulated)
        self._event(session_id, "part_delta", "", {
            "part_id": text_part["id"], "part_type": "text",
            "delta": "", "content": accumulated,
            "status": "completed", "streaming": False,
        })
        self._event(
            session_id, "model_stream_completed", "流式输出完成",
            {"part_id": text_part["id"], "part_type": "text", "streaming": True, "content_length": len(accumulated)},
        )
        self._update_streaming_diagnostics(
            session_id,
            status="completed",
            mode="chat_stream",
            fallback_to_non_stream=False,
            current_part_id=text_part["id"],
            content_length=len(accumulated),
        )

        self._pending_stream_part_id = None
        logger.info("agent_session.processor chat_stream completed: session_id=%s content_length=%s", session_id, len(accumulated))
        return accumulated, text_part["id"]

    def _update_streaming_diagnostics(self, session_id: str, **updates: Any) -> None:
        session = self.repository.get_session(session_id)
        if not session:
            return
        metadata = ensure_session_state(dict(session.get("metadata") or {}))
        diagnostics = dict(metadata.get("streaming_diagnostics") or {})
        diagnostics.update({key: value for key, value in updates.items() if value is not None})
        diagnostics["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        metadata["streaming_diagnostics"] = diagnostics
        self.repository.update_session(session_id, metadata=metadata)

    def _finalize_streaming_text_part(
        self,
        session_id: str,
        raw: str,
        model_parts: list,
        streaming_part_id: str | None,
    ) -> str:
        if streaming_part_id is None:
            return ""
        has_tool_calls = any(p.type == "tool_call" for p in model_parts)
        has_summary = any(p.type == "summary" for p in model_parts)
        has_finalize = any(p.type == "tool_call" and p.tool == "finalize" for p in model_parts)

        if has_summary and not has_tool_calls:
            summary_text = ""
            for p in model_parts:
                if p.type == "summary":
                    summary_text = p.content.strip() or str((p.payload or {}).get("summary") or "")
                    break
            self.repository.update_part(
                streaming_part_id, status="completed", type="summary",
                title="最终结果",
                content=summary_text or raw.strip(),
                payload={"streaming": True, "converted_from_text": True, "summary": summary_text or raw.strip()},
            )
            self._event(session_id, "part_delta", "", {
                "part_id": streaming_part_id, "part_type": "summary",
                "delta": "", "content": summary_text or raw.strip(),
                "status": "completed", "streaming": False,
            })
            return "summary"

        if has_tool_calls:
            natural_text = ""
            for p in model_parts:
                if p.type == "text" and p.content.strip():
                    natural_text += p.content.strip() + "\n"
            finalize_summary = ""
            for p in model_parts:
                if p.type == "tool_call" and p.tool == "finalize" and p.arguments:
                    finalize_summary = str(p.arguments.get("summary") or "")
            if has_finalize and not natural_text.strip():
                self.repository.update_part(
                    streaming_part_id, status="completed", type="summary",
                    title="最终结果",
                    content=finalize_summary or raw.strip(),
                    payload={"streaming": True, "converted_from_text": True, "summary": finalize_summary or raw.strip()},
                )
                self._event(session_id, "part_delta", "", {
                    "part_id": streaming_part_id, "part_type": "summary",
                    "delta": "", "content": finalize_summary or raw.strip(),
                    "status": "completed", "streaming": False,
                })
                return "summary"
            if has_finalize and natural_text.strip():
                self.repository.update_part(
                    streaming_part_id, status="completed", type="summary",
                    title="最终结果",
                    content=finalize_summary or natural_text.strip(),
                    payload={"streaming": True, "converted_from_text": True, "summary": finalize_summary or natural_text.strip()},
                )
                self._event(session_id, "part_delta", "", {
                    "part_id": streaming_part_id, "part_type": "summary",
                    "delta": "", "content": finalize_summary or natural_text.strip(),
                    "status": "completed", "streaming": False,
                })
                return "summary"
            self.repository.update_part(
                streaming_part_id, status="completed",
                title="工具请求" if not natural_text.strip() else "说明",
                content=natural_text.strip(),
                payload={"streaming": True, "protocol_only": not bool(natural_text.strip())},
            )
            self._event(session_id, "part_delta", "", {
                "part_id": streaming_part_id, "part_type": "text",
                "delta": "", "content": natural_text.strip(),
                "status": "completed", "streaming": False,
                "payload": {"protocol_only": not bool(natural_text.strip())},
            })
            return "text"

        self.repository.update_part(streaming_part_id, status="completed", title="说明", content=raw.strip())
        self._event(session_id, "part_delta", "", {
            "part_id": streaming_part_id, "part_type": "text",
            "delta": "", "content": raw.strip(),
            "status": "completed", "streaming": False,
        })
        return "text"

    async def _fallback_model_call(self, _messages: list[dict[str, str]]) -> str:
        logger.info("agent_session.processor fallback model call used: no external model_call configured")
        return json.dumps({"tool": "finalize", "arguments": {"summary": "没有配置模型调用，已创建 Agent Session。"}}, ensure_ascii=False)

    def _context(self, session: dict[str, Any]) -> dict[str, Any]:
        return {"project_path": session.get("project_path"), "session": session}

    def _ensure_metadata(self, session: dict[str, Any]) -> dict[str, Any]:
        return ensure_session_state(dict(session.get("metadata") or {}))

    def _record_context(self, session_id: str, payload: dict[str, Any]) -> None:
        session = self.repository.get_session(session_id) or {}
        metadata = self._ensure_metadata(session)
        touched = set(metadata.get("touched_paths") or [])
        for key in ("path",):
            if payload.get(key):
                touched.add(str(payload[key]).replace("\\", "/"))
        for path in payload.get("touched_paths") or []:
            if path:
                touched.add(str(path).replace("\\", "/"))
        for item in payload.get("files") or []:
            if isinstance(item, dict) and item.get("path"):
                touched.add(str(item["path"]).replace("\\", "/"))
        for item in payload.get("matches") or []:
            if isinstance(item, dict) and item.get("path"):
                touched.add(str(item["path"]).replace("\\", "/"))
        metadata = add_touched_paths(metadata, sorted(touched))
        if payload.get("commands"):
            metadata["detected_commands"] = payload.get("commands") or []
            state = dict(metadata.get("state") or {})
            state["detected_commands"] = metadata["detected_commands"]
            metadata["state"] = state
        self.repository.update_session(session_id, metadata=metadata)

    def _handle_command(
        self,
        session: dict[str, Any],
        call_part_id: str,
        command_payload: dict[str, Any],
        policy: dict[str, str],
        tool: Any,
        messages: list[dict[str, str]],
        raw: str,
        *,
        tool_name: str,
    ) -> dict[str, Any] | None:
        session_id = session["id"]
        self.repository.update_part(call_part_id, status="completed" if policy["execution_mode"] != "blocked" else "blocked")
        part_payload = dict(command_payload)
        part_payload.update(policy)
        title = {
            "run_dev_server": "开发服务器",
            "stop_dev_server": "停止开发服务器",
            "run_targeted_test": "精准测试",
            "bash_command": "验证命令",
        }.get(tool_name, tool.description)
        if policy["execution_mode"] == "blocked":
            part = self.repository.add_part(session_id, "command", status="blocked", title=title, content=policy["policy_reason"], payload=part_payload)
            metadata = record_command(self._ensure_metadata(self.repository.get_session(session_id) or session), part["id"], policy["policy_reason"])
            metadata = set_phase(metadata, "needs_manual_review")
            self.repository.update_session(session_id, metadata=metadata)
            return self._stop_with_summary(session_id, "needs_manual_review", policy["policy_reason"], part_id=part["id"])
        if policy["execution_mode"] == "approval_required":
            part = self.repository.add_part(session_id, "command", status="pending", title=title, content=policy["policy_reason"], payload=part_payload)
            metadata = record_command(self._ensure_metadata(self.repository.get_session(session_id) or session), part["id"])
            metadata = set_phase(metadata, "waiting_approval")
            self.repository.update_session(session_id, status="waiting_approval", metadata=metadata)
            self._event(session_id, "action_proposed", policy["policy_reason"], {"part_id": part["id"], **policy})
            return self._with_parts(session_id)

        metadata = set_phase(self._ensure_metadata(self.repository.get_session(session_id) or session), "verifying")
        self.repository.update_session(session_id, status="verifying", metadata=metadata)
        payload = dict(part_payload)
        command = normalize_command(command_payload.get("command"))
        if not command_allowed(command):
            part = self.repository.add_part(session_id, "command", status="failed", title=title, content="command is not allowlisted", payload={**payload, "command": command})
            metadata = record_command(self._ensure_metadata(self.repository.get_session(session_id) or session), part["id"], "command is not allowlisted")
            self.repository.update_session(session_id, status="failed", metadata=set_phase(metadata, "failed"))
            self._event(session_id, "command_failed", "command is not allowlisted", {"part_id": part["id"], "command": command})
            return self._stop_with_summary(session_id, "needs_manual_review", "command is not allowlisted", part_id=part["id"])
        command_root = resolve_command_cwd(Path(str(session.get("project_path") or Path.cwd())).resolve(), command)
        part = self.repository.add_part(session_id, "command", status="running", title=title, content="命令正在交互式终端中运行", payload={**payload, "command": command, "cwd": str(command_root)})
        self._start_command_terminal(session, part)
        terminal_id = str((self.repository.get_part(part["id"]) or {}).get("payload", {}).get("terminal_id") or "")
        if terminal_id:
            terminal_manager.wait(terminal_id, float(command_payload.get("timeout_seconds") or 120) + 5)
        completed_part = self.repository.get_part(part["id"]) or part
        payload = dict(completed_part.get("payload") or {})
        result_status = "completed" if completed_part.get("status") == "executed" else "failed"
        result_summary = str(completed_part.get("content") or ("命令执行完成" if result_status == "completed" else "命令执行失败"))
        result_error = None if result_status == "completed" else result_summary
        metadata = record_command(self._ensure_metadata(self.repository.get_session(session_id) or session), part["id"], result_error)
        self.repository.update_session(session_id, metadata=metadata)
        self._event(session_id, "command_completed" if result_status == "completed" else "command_failed", result_summary, {"part_id": part["id"], **payload})
        observation = self._compact_observation("bash_command", result_status, result_summary, payload, result_error)
        if result_status == "completed":
            messages.append({"role": "assistant", "content": raw})
            guidance = (
                "开发服务器已启动。优先调用 http_probe 确认 localhost 可访问，再用 read_local_page 或 browser_validate_page 做页面验证；完成后用 finalize 总结 server_url。"
                if tool_name == "run_dev_server"
                else "开发服务器已停止。可以调用 get_server_status 确认状态，或重新 collect_context 后继续开发。"
                if tool_name == "stop_dev_server"
                else "精准测试已执行。建议调用 summarize_test_results 汇总结果；如果失败，再调用 collect_test_failures 提炼失败块。"
                if tool_name == "run_targeted_test"
                else "验证通过。下一步必须调用 finalize，输出改动文件、验证命令、验证结果和剩余风险。"
            )
            messages.append({"role": "user", "content": "工具结果：\n" + json.dumps({**observation, "guidance": guidance}, ensure_ascii=False)})
            return None

        metadata = self._ensure_metadata(self.repository.get_session(session_id) or session)
        attempts = int(metadata.get("repair_attempts") or 0)
        if attempts < int(metadata.get("max_repair_attempts") or MAX_REPAIR_ATTEMPTS):
            metadata = record_repair_attempt(metadata)
            self.repository.update_session(session_id, status="repairing", metadata=metadata)
            messages.append({"role": "assistant", "content": raw})
            failure_guidance = (
                "测试命令失败。请先调用 summarize_test_results 查看统计，再调用 collect_test_failures 提炼失败块，然后调用 read_execution 或读取相关文件，基于 failure_summary 最多生成一次修复补丁，再次验证时优先使用 run_targeted_test。"
                if self._is_test_command(payload.get("command"))
                else "验证失败。请先调用 read_execution 或读取相关文件，基于 failure_summary 最多生成一次修复补丁，然后再次验证。"
            )
            messages.append({"role": "user", "content": "工具结果：\n" + json.dumps({**observation, "guidance": failure_guidance}, ensure_ascii=False)})
            return None
        detail = result_error or result_summary or "已达到最大修复次数。"
        return self._stop_with_summary(session_id, "needs_manual_review", f"验证失败，已达到最大修复次数。{detail}", part_id=part["id"])

    def _stop_with_summary(self, session_id: str, status: str, summary: str, *, part_id: str | None = None) -> dict[str, Any]:
        self.repository.add_part(session_id, "summary", status="completed", title="最终结果", content=summary, payload={"summary": summary, "blocked_part_id": part_id})
        metadata = set_phase(self._ensure_metadata(self.repository.get_session(session_id) or {}), status)
        self.repository.update_session(session_id, status=status, metadata=metadata)
        self._event(session_id, "session_blocked" if status == "needs_manual_review" else "session_failed", summary, {"part_id": part_id})
        return self._with_parts(session_id)

    def _interrupt_requested(self, session: dict[str, Any] | None = None) -> bool:
        if session is None:
            return False
        metadata = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
        return bool(metadata.get("interrupt_requested") or session.get("status") == "interrupted")

    def _maybe_interrupt(self, session_id: str) -> dict[str, Any] | None:
        session = self.repository.get_session(session_id) or {}
        if not self._interrupt_requested(session):
            return None
        return self._interrupt_summary(session_id)

    def _interrupt_summary(self, session_id: str) -> dict[str, Any]:
        session = self.repository.get_session(session_id) or {}
        metadata = self._ensure_metadata(session)
        if metadata.get("interrupt_recorded"):
            return self._with_parts(session_id)
        summary = "用户已中断 Agent 任务。已停止继续调用模型和工具，当前 transcript 已保留。"
        metadata = set_phase(metadata, "interrupted")
        metadata["interrupt_requested"] = True
        metadata["interrupt_recorded"] = True
        metadata["active_prompt_id"] = None
        state = dict(metadata.get("state") or {})
        state["latest_error"] = summary
        metadata["state"] = state
        self.repository.add_part(
            session_id,
            "summary",
            status="completed",
            title="已中断",
            content=summary,
            payload={"summary": summary, "interrupted": True},
        )
        self.repository.update_session(session_id, status="interrupted", metadata=metadata)
        self._event(session_id, "session_interrupted", summary, {"interrupted": True})
        return self._with_parts(session_id)

    def _fallback_summary(self, session_id: str, summary: str) -> dict[str, Any]:
        session = self.repository.get_session(session_id) or {}
        metadata = self._ensure_metadata(session)
        metadata = record_fallback_summary(metadata)
        existing_parts = self.repository.list_parts(session_id)
        has_execution = any(part.get("type") in {"diff", "command"} for part in existing_parts)
        has_summary = any(part.get("type") == "summary" for part in existing_parts)
        if has_summary:
            metadata = set_phase(metadata, "completed")
            self.repository.update_session(session_id, status="completed", metadata=metadata)
            return self._with_parts(session_id)
        final_status = "completed" if has_execution else "needs_manual_review"
        self.repository.add_part(session_id, "summary", status="completed", title="最终结果", content=summary, payload={"summary": summary, "fallback": True, "has_execution": has_execution})
        self.repository.update_session(session_id, status=final_status, metadata=metadata)
        self._event(session_id, "summary_completed", summary, {"fallback": True, "has_execution": has_execution})
        return self._with_parts(session_id)

    def _with_parts(self, session_id: str) -> dict[str, Any]:
        session = self.repository.get_session(session_id) or {}
        session["parts"] = self.repository.list_parts(session_id)
        return session

    _CHUNK_TYPE_MAP: dict[str, str] = {
        "phase_change": "phase",
        "model_stream_started": "part_start",
        "part_delta": "part_delta",
        "model_stream_completed": "part_complete",
        "tool_call_started": "tool_call",
        "tool_call_completed": "tool_result",
        "summary_completed": "summary",
        "permission_asked": "permission_request",
        "action_proposed": "action",
        "action_approved": "action",
        "action_rejected": "action",
        "action_executed": "action",
        "action_failed": "action",
        "command_completed": "action",
        "command_failed": "action",
        "model_stream_failed": "error",
        "session_failed": "error",
        "session_blocked": "error",
        "session_started": "status",
        "prompt_queued": "status",
        "prompt_already_running": "status",
    }

    def _resolve_chunk_type(self, event_type: str, payload: dict[str, Any]) -> str:
        mapped = self._CHUNK_TYPE_MAP.get(event_type)
        if mapped:
            return mapped
        if payload.get("part_id"):
            return "part_snapshot"
        if payload.get("tool"):
            return "tool"
        return "event"

    def _event(self, session_id: str, event_type: str, message: str, payload: dict[str, Any]) -> None:
        enriched = dict(payload or {})
        enriched.setdefault("session_id", session_id)
        enriched.setdefault("chunk_type", self._resolve_chunk_type(event_type, enriched))
        part_id = enriched.get("part_id")
        if not enriched.get("part") and part_id and isinstance(part_id, str) and part_id.startswith("agp_"):
            part = self.repository.get_part(part_id)
            if part:
                if not enriched.get("part_type"):
                    enriched.setdefault("part_type", part.get("type"))
                if not enriched.get("status"):
                    enriched.setdefault("status", part.get("status"))
                if not enriched.get("summary"):
                    enriched.setdefault("summary", part.get("content") or part.get("title") or message)
                enriched["part"] = part
        elif part_id and not enriched.get("part_type"):
            part = self.repository.get_part(str(part_id)) if isinstance(part_id, str) and part_id.startswith("agp_") else None
            if part:
                enriched.setdefault("part_type", part.get("type"))
                enriched.setdefault("status", part.get("status"))
                enriched.setdefault("summary", part.get("content") or part.get("title") or message)
        enriched.setdefault("summary", message)
        event_row = self.repository.add_event(session_id, event_type, message, enriched)
        if self._event_callback:
            try:
                self._event_callback(session_id, event_row)
            except Exception:
                logger.debug("agent_session event callback failed for session %s", session_id, exc_info=True)

    def _tool_call_text(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name == "read":
            return f"读取 {args.get('path') or args.get('file_path') or ''}"
        if tool_name == "search":
            return f"搜索 {args.get('query') or ''}"
        if tool_name == "collect_context":
            return "收集上下文"
        if tool_name == "detect_project_commands":
            return "识别验证命令"
        if tool_name == "patch":
            return "生成补丁"
        if tool_name == "bash_command":
            command = args.get("payload", {}).get("command") if isinstance(args.get("payload"), dict) else args.get("command")
            return "运行 " + (" ".join(command) if isinstance(command, list) else str(command or "命令"))
        return tool_name

    def _tool_summary(self, args: dict[str, Any]) -> str:
        path = args.get("path") or args.get("file_path") or ""
        query = args.get("query") or ""
        command = args.get("payload", {}).get("command") if isinstance(args.get("payload"), dict) else args.get("command")
        if path:
            return path if len(path) <= 80 else "..." + path[-77:]
        if query:
            return query if len(query) <= 80 else query[:77] + "..."
        if command:
            cmd_str = " ".join(command) if isinstance(command, list) else str(command)
            return cmd_str if len(cmd_str) <= 80 else cmd_str[:77] + "..."
        return ""

    def _next_tool_guidance(
        self,
        tool_name: str,
        status: str,
        payload: dict[str, Any],
        error: str | None = None,
    ) -> dict[str, Any] | None:
        if status != "completed":
            if tool_name == "http_probe":
                return {
                    "guidance": "页面探测失败。请先调用 get_server_status 或 read_logs 检查开发服务器，再决定是否重新 run_dev_server。",
                    "recommended_tools": ["get_server_status", "read_logs", "run_dev_server"],
                }
            if tool_name in {"browser_validate_page", "browser_click", "browser_fill", "browser_wait_for"}:
                return {
                    "guidance": "浏览器验证失败。请先查看 console_errors / page_errors，再决定是否 read_local_page、read_logs 或修复代码后重新验证。",
                    "recommended_tools": ["read_local_page", "read_logs", "read", "patch"],
                }
            return None
        if tool_name == "run_dev_server":
            return {
                "guidance": "开发服务器已启动。优先调用 http_probe 验证地址可访问，再用 read_local_page 或 browser_validate_page 检查页面。",
                "recommended_tools": ["http_probe", "read_local_page", "browser_validate_page"],
            }
        if tool_name == "http_probe":
            if payload.get("ok") and "html" in str(payload.get("content_type") or "").lower():
                return {
                    "guidance": "HTTP 探测已通过。下一步优先调用 read_local_page 查看标题和结构，或调用 browser_validate_page 做浏览器级验证。",
                    "recommended_tools": ["read_local_page", "browser_validate_page"],
                }
            if payload.get("ok") and "json" in str(payload.get("content_type") or "").lower():
                return {
                    "guidance": "HTTP 探测返回了 JSON。下一步优先调用 probe_json_endpoint 查看结构，必要时再结合 capture_network_errors 做联调。",
                    "recommended_tools": ["probe_json_endpoint", "capture_network_errors"],
                }
            return {
                "guidance": "HTTP 探测完成。若需要继续前端验证，可调用 read_local_page 或 browser_validate_page。",
                "recommended_tools": ["read_local_page", "browser_validate_page"],
            }
        if tool_name == "probe_json_endpoint":
            if payload.get("ok"):
                return {
                    "guidance": "JSON 接口探测成功。若需要排查页面请求链路，可继续调用 capture_network_errors 或 browser_validate_page。",
                    "recommended_tools": ["capture_network_errors", "browser_validate_page", "finalize"],
                }
            return {
                "guidance": "JSON 接口探测失败。请先检查 parse_error、status_code 和 body_excerpt，再读取相关后端文件或日志。",
                "recommended_tools": ["read_logs", "read", "search", "patch"],
            }
        if tool_name == "read_local_page":
            return {
                "guidance": "页面摘要已读取。若要检查控制台错误、关键选择器或文本断言，请继续调用 browser_validate_page。",
                "recommended_tools": ["browser_validate_page", "browser_click", "browser_fill", "browser_wait_for"],
            }
        if tool_name == "browser_validate_page":
            if payload.get("ok"):
                return {
                    "guidance": "浏览器验证通过。若还需交互验证，可继续调用 browser_click、browser_fill 或 browser_wait_for；否则可 finalize。",
                    "recommended_tools": ["browser_click", "browser_fill", "browser_wait_for", "finalize"],
                }
            return {
                "guidance": "浏览器验证发现问题。请先查看 console_errors、page_errors 和 selector_results，再读取相关文件或补丁修复。",
                "recommended_tools": ["read", "search", "patch", "read_logs"],
            }
        if tool_name in {"browser_click", "browser_fill", "browser_wait_for"}:
            return {
                "guidance": "交互步骤已执行。建议再调用 browser_validate_page 或继续 browser_wait_for，确认交互后的页面状态稳定。",
                "recommended_tools": ["browser_validate_page", "browser_wait_for", "finalize"],
            }
        if tool_name == "capture_network_errors":
            if payload.get("ok"):
                return {
                    "guidance": "网络请求检查通过。若页面和接口都符合预期，可以 finalize；否则可继续做交互验证。",
                    "recommended_tools": ["browser_validate_page", "browser_click", "finalize"],
                }
            return {
                "guidance": "检测到网络错误。请先查看 request_failures 和 error_responses，再读取前后端相关文件或日志定位问题。",
                "recommended_tools": ["read_logs", "read_local_page", "read", "search", "patch"],
            }
        if tool_name == "collect_test_failures":
            return {
                "guidance": "测试失败摘要已提取。下一步优先调用 read_execution 或 read 相关文件，基于失败块修复后再次验证；如果只需重跑受影响测试，优先使用 run_targeted_test。",
                "recommended_tools": ["read_execution", "read", "patch", "run_targeted_test", "bash_command"],
            }
        if tool_name == "summarize_test_results":
            if int(payload.get("failed") or 0) > 0 or int(payload.get("exit_code") or 0) != 0:
                return {
                    "guidance": "测试结果显示存在失败。建议继续调用 collect_test_failures 提炼失败块，再读取相关文件进行修复。",
                    "recommended_tools": ["collect_test_failures", "read_execution", "read", "patch"],
                }
            return {
                "guidance": "测试结果已汇总且没有失败。若验证范围足够，可以直接 finalize；否则可继续 run_targeted_test 补跑相关测试。",
                "recommended_tools": ["finalize", "run_targeted_test"],
            }
        if tool_name == "run_targeted_test":
            return {
                "guidance": "精准测试命令已生成。执行后建议调用 summarize_test_results；若失败，再调用 collect_test_failures。",
                "recommended_tools": ["summarize_test_results", "collect_test_failures", "finalize"],
            }
        return None

    def _is_test_command(self, command: Any) -> bool:
        if not isinstance(command, list):
            return False
        lowered = [str(item).lower() for item in command]
        joined = " ".join(lowered)
        return any(marker in joined for marker in ("pytest", "vitest", "npm test", "npm run test", "unittest"))

    def _handle_protocol_miss(self, session_id: str, raw: str, messages: list[dict[str, str]]) -> dict[str, Any] | None:
        session = self.repository.get_session(session_id) or {}
        metadata = self._ensure_metadata(session)
        metadata["last_raw_model_output"] = raw[:4000]
        metadata["last_parse_error"] = "model_output_not_tool_json"
        existing_parts = self.repository.list_parts(session_id)
        has_execution = any(part.get("type") in {"diff", "command"} for part in existing_parts)
        looks_final = self._looks_like_final_text(raw)
        if has_execution or looks_final:
            summary_text = raw.strip() or "任务已有执行记录，系统已生成兜底总结。"
            metadata = set_phase(metadata, "completed" if has_execution else "needs_manual_review")
            metadata["model_protocol_status"] = "fallback_summary"
            metadata["fallback_summary_used"] = True
            state = dict(metadata.get("state") or {})
            state["fallback_summary_used"] = True
            metadata["state"] = state
            self.repository.add_part(session_id, "summary", status="completed", title="最终结果", content=summary_text, payload={"summary": summary_text, "fallback": True, "raw_model_output": raw})
            self.repository.update_session(session_id, status="completed" if has_execution else "needs_manual_review", metadata=metadata)
            self._event(session_id, "summary_completed", summary_text, {"fallback": True})
            return self._with_parts(session_id)

        attempts = int(metadata.get("protocol_repair_count") or 0)
        if attempts < MAX_PROTOCOL_REPAIRS:
            metadata["protocol_repair_count"] = attempts + 1
            metadata["model_protocol_status"] = "repaired"
            self.repository.update_session(session_id, metadata=metadata)
            tool_names = [t.name for t in self.tools.list()]
            tool_list = ", ".join(tool_names)
            guidance = (
                f'你的上一条回复没有包含有效的工具调用。请直接输出一个 JSON 对象来调用工具。\n'
                f'可用工具：{tool_list}\n'
                f'格式：{{"tool": "工具名", "arguments": {{...}}}}\n'
                f'示例：{{"tool": "collect_context", "arguments": {{}}}}\n'
                f'注意：不要输出任何解释文字，不要用 markdown 代码块包裹，直接输出 JSON。'
            )
            part = self.repository.add_part(
                session_id,
                "tool_result",
                status="completed",
                title="协议纠偏",
                content=guidance,
                payload={"guidance": guidance, "raw_model_output_preview": raw[:500]},
            )
            self._event(session_id, "tool_call_completed", guidance, {"part_id": part["id"], "tool": "protocol"})
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "工具结果：\n" + json.dumps({"tool": "protocol", "status": "blocked", "summary": guidance, "payload": {"guidance": guidance}}, ensure_ascii=False)})
            return None

        metadata["model_protocol_status"] = "needs_manual_review"
        self.repository.update_session(session_id, metadata=metadata)
        return self._stop_with_summary(session_id, "needs_manual_review", "模型连续没有按 JSON 工具协议输出，已停止等待人工处理。")

    def _compact_observation(
        self,
        tool_name: str,
        status: str,
        summary: str,
        payload: dict[str, Any],
        error: str | None = None,
    ) -> dict[str, Any]:
        compact: dict[str, Any] = {"tool": tool_name, "status": status, "summary": summary, "payload": {}, "compact_observation_used": True}
        if error:
            compact["error"] = self._truncate(str(error), 1200)
        if tool_name == "collect_context":
            compact["payload"] = {
                "goal": payload.get("goal"),
                "markers": payload.get("markers") or {},
                "files": [item.get("path") for item in (payload.get("files") or [])[:8] if isinstance(item, dict)],
                "matches": [
                    {"path": item.get("path"), "line": item.get("line"), "preview": self._truncate(str(item.get("preview") or ""), 180)}
                    for item in (payload.get("matches") or [])[:8]
                    if isinstance(item, dict)
                ],
                "symbols": [
                    {
                        "symbol": item.get("symbol"),
                        "engine": item.get("engine"),
                        "definitions": [
                            {"path": match.get("path"), "line": match.get("line"), "kind": match.get("kind")}
                            for match in (item.get("definitions") or [])[:4]
                            if isinstance(match, dict)
                        ],
                        "references": [
                            {"path": match.get("path"), "line": match.get("line"), "is_definition": match.get("is_definition")}
                            for match in (item.get("references") or [])[:6]
                            if isinstance(match, dict)
                        ],
                    }
                    for item in (payload.get("symbols") or [])[:4]
                    if isinstance(item, dict)
                ],
                "commands": (payload.get("commands") or [])[:6],
                "touched_paths": (payload.get("touched_paths") or [])[:12],
            }
            return compact
        if tool_name == "read":
            compact["payload"] = {
                "path": payload.get("path"),
                "content": self._truncate(str(payload.get("content") or ""), 2000),
                "truncated": bool(payload.get("truncated") or len(str(payload.get("content") or "")) > 2000),
            }
            return compact
        if tool_name == "search":
            compact["payload"] = {
                "query": payload.get("query"),
                "matches": (payload.get("matches") or [])[:8],
                "touched_paths": (payload.get("touched_paths") or [])[:12],
            }
            return compact
        if tool_name == "http_probe":
            compact["payload"] = {
                "url": payload.get("url"),
                "final_url": payload.get("final_url"),
                "status_code": payload.get("status_code"),
                "ok": payload.get("ok"),
                "content_type": payload.get("content_type"),
                "title": payload.get("title"),
                "body_excerpt": self._truncate(str(payload.get("body_excerpt") or ""), 800),
            }
            return compact
        if tool_name == "probe_json_endpoint":
            compact["payload"] = {
                "url": payload.get("url"),
                "final_url": payload.get("final_url"),
                "status_code": payload.get("status_code"),
                "ok": payload.get("ok"),
                "content_type": payload.get("content_type"),
                "json_type": payload.get("json_type"),
                "json_preview": payload.get("json_preview"),
                "parse_error": payload.get("parse_error"),
            }
            return compact
        if tool_name == "read_local_page":
            compact["payload"] = {
                "url": payload.get("url"),
                "final_url": payload.get("final_url"),
                "status_code": payload.get("status_code"),
                "ok": payload.get("ok"),
                "content_type": payload.get("content_type"),
                "title": payload.get("title"),
                "headings": (payload.get("headings") or [])[:6],
                "links": (payload.get("links") or [])[:8],
                "text_excerpt": self._truncate(str(payload.get("text_excerpt") or ""), 1200),
            }
            return compact
        if tool_name == "browser_validate_page":
            compact["payload"] = {
                "url": payload.get("url"),
                "final_url": payload.get("final_url"),
                "status_code": payload.get("status_code"),
                "ok": payload.get("ok"),
                "title": payload.get("title"),
                "headings": (payload.get("headings") or [])[:6],
                "console_errors": (payload.get("console_errors") or [])[:6],
                "page_errors": (payload.get("page_errors") or [])[:6],
                "selector_results": (payload.get("selector_results") or [])[:6],
                "text_results": (payload.get("text_results") or [])[:6],
                "body_excerpt": self._truncate(str(payload.get("body_excerpt") or ""), 1200),
                "engine": payload.get("engine"),
            }
            return compact
        if tool_name == "capture_network_errors":
            compact["payload"] = {
                "url": payload.get("url"),
                "final_url": payload.get("final_url"),
                "status_code": payload.get("status_code"),
                "ok": payload.get("ok"),
                "request_failures": (payload.get("request_failures") or [])[:8],
                "error_responses": (payload.get("error_responses") or [])[:8],
                "console_errors": (payload.get("console_errors") or [])[:6],
                "page_errors": (payload.get("page_errors") or [])[:6],
                "engine": payload.get("engine"),
            }
            return compact
        if tool_name in {"browser_click", "browser_fill", "browser_wait_for"}:
            compact["payload"] = {
                "url": payload.get("url"),
                "final_url": payload.get("final_url"),
                "status_code": payload.get("status_code"),
                "ok": payload.get("ok"),
                "title": payload.get("title"),
                "action": payload.get("action"),
                "headings": (payload.get("headings") or [])[:6],
                "console_errors": (payload.get("console_errors") or [])[:6],
                "page_errors": (payload.get("page_errors") or [])[:6],
                "selector_results": (payload.get("selector_results") or [])[:6],
                "text_results": (payload.get("text_results") or [])[:6],
                "body_excerpt": self._truncate(str(payload.get("body_excerpt") or ""), 1200),
                "engine": payload.get("engine"),
            }
            return compact
        if tool_name == "collect_test_failures":
            compact["payload"] = {
                "failure_summary": payload.get("failure_summary"),
                "failures": (payload.get("failures") or [])[:8],
                "stdout_excerpt": self._truncate(str(payload.get("stdout_excerpt") or ""), 1200),
                "stderr_excerpt": self._truncate(str(payload.get("stderr_excerpt") or ""), 1200),
            }
            return compact
        if tool_name == "summarize_test_results":
            compact["payload"] = {
                "framework": payload.get("framework"),
                "exit_code": payload.get("exit_code"),
                "headline": payload.get("headline"),
                "passed": payload.get("passed"),
                "failed": payload.get("failed"),
                "skipped": payload.get("skipped"),
                "collected": payload.get("collected"),
                "duration": payload.get("duration"),
            }
            return compact
        if tool_name == "patch":
            compact["payload"] = {
                "changed_files": payload.get("changed_files") or [],
                "applied_hunks": payload.get("applied_hunks"),
                "patch_summaries": payload.get("patch_summaries") or [],
                "policy_decision": payload.get("policy_decision"),
                "risk_level": payload.get("risk_level"),
                "policy_reason": payload.get("policy_reason"),
                "available_commands": payload.get("available_commands") or [],
            }
            return compact
        if tool_name == "bash_command":
            compact["payload"] = {
                "command": payload.get("command"),
                "exit_code": payload.get("exit_code"),
                "stdout": self._truncate(str(payload.get("stdout") or ""), 2000),
                "stderr": self._truncate(str(payload.get("stderr") or ""), 2000),
                "failure_summary": payload.get("failure_summary") or "",
                "policy_decision": payload.get("policy_decision"),
                "risk_level": payload.get("risk_level"),
                "policy_reason": payload.get("policy_reason"),
            }
            return compact
        if tool_name == "detect_project_commands":
            compact["payload"] = {"commands": (payload.get("commands") or [])[:8]}
            return compact
        compact["payload"] = payload
        return compact

    def _classify_task_intent(self, content: str) -> str:
        lowered = content.lower()
        analyze_markers = ("分析", "看看", "排查", "不要写文件", "不写文件", "只读", "解释")
        develop_markers = ("修改", "新增", "修复", "实现", "增加")
        verify_markers = ("验证", "测试", "检查", "typecheck", "pytest")
        if any(marker in lowered for marker in develop_markers):
            return "develop"
        if any(marker in lowered for marker in verify_markers):
            return "verify"
        if any(marker in lowered for marker in analyze_markers):
            return "analyze"
        return "develop"

    def _looks_like_final_text(self, raw: str) -> bool:
        text = raw.strip()
        if len(text) < 12:
            return False
        strong_markers = ("已完成", "已经完成", "最终总结", "最终结果", "任务完成", "全部完成")
        if any(marker in text for marker in strong_markers):
            return True
        weak_markers = ("总结", "建议", "风险", "验证结果", "改动")
        return any(marker in text for marker in weak_markers) and len(text) > 40

    def _truncate(self, value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        head = value[: max(limit - 120, 0)]
        return f"{head}\n... 已截断 {len(value) - len(head)} 字符 ..."

    def _missing_patch_context(self, args: dict[str, Any], touched_paths: set[str]) -> list[str]:
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else args
        files = payload.get("files") or payload.get("file_changes") or []
        if not isinstance(files, list):
            return []
        safe_prefixes = ("tmp/", "docs/", "tests/", "server/tests/", "client/src/test/")
        source_suffixes = (".py", ".ts", ".tsx", ".css")
        missing: list[str] = []
        for item in files:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or item.get("file_path") or "").replace("\\", "/")
            if not path or path.startswith(safe_prefixes) or path.endswith(".md"):
                continue
            if path.endswith(source_suffixes) and path not in touched_paths:
                missing.append(path)
        return missing
