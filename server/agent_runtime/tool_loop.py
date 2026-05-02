"""JSON tool-request loop for workflow agents."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from time import perf_counter
from typing import Any, Awaitable, Callable

from digital_team.models import AgentOutput

from .context_manager import ToolLoopContextManager, estimate_tokens
from .definitions import RuntimeExecutionContext
from .execution_state import (
    COMPLETED,
    NEEDS_MANUAL_REVIEW,
    WAITING_APPROVAL,
    WAITING_PERMISSION,
    set_workflow_state,
    state_for_tool,
)
from .permission import PermissionRule, default_rules_for_agent
from .tool_models import AgentToolRequest, AgentToolLoopResponse, AgentToolResult
from .tools import AgentToolExecutor

logger = logging.getLogger(__name__)

ModelCall = Callable[[list[dict[str, str]]], Awaitable[str]]
DelegateCall = Callable[[str, dict[str, Any], RuntimeExecutionContext, dict[str, Any]], Awaitable[AgentToolResult]]

# Timeout warning threshold (seconds)
_STEP_TIMEOUT_WARNING_SECONDS = 30.0


def _sanitize_model_output(content: str) -> str:
    """Attempt to extract a valid JSON object from potentially noisy LLM output.

    Handles common issues:
    - Markdown fenced code blocks (```json ... ```)
    - Leading/trailing text around a JSON object
    - Extra whitespace
    """
    text = content.strip()
    if not text:
        return text

    # Try extracting from markdown fence
    fence = re.search(r"```(?:json)?\s*([\[{].*?[\]}])\s*```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()

    # If starts with JSON object/array, return as-is
    if text.startswith("{") or text.startswith("["):
        return text

    # Try finding the outermost JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0).strip()

    # Some providers wrap tool requests in a top-level array.
    array_match = re.search(r"\[.*\]", text, re.DOTALL)
    if array_match:
        return array_match.group(0).strip()

    return text


def _looks_like_final_text(content: str) -> bool:
    text = content.strip()
    if len(text) < 8:
        return False
    lowered = text.lower()
    final_markers = ("完成", "总结", "最终", "结果", "done", "completed", "summary")
    tool_markers = ("propose_patch", "propose_command", "read_file", "search_code", "inspect_project")
    return any(marker in lowered or marker in text for marker in final_markers) and not any(marker in lowered for marker in tool_markers)


class AgentToolLoop:
    def __init__(
        self,
        repository: Any,
        executor: AgentToolExecutor,
        max_iterations: int = 6,
        context_manager: ToolLoopContextManager | None = None,
    ):
        self.repository = repository
        self.executor = executor
        self.max_iterations = max_iterations
        self.context_manager = context_manager or ToolLoopContextManager()

    async def run(
        self,
        *,
        agent_id: str,
        context: RuntimeExecutionContext,
        step_input: dict[str, Any],
        project: dict[str, Any],
        task: dict[str, Any],
        model_call: ModelCall,
        delegate_call: DelegateCall | None = None,
        trace_id: str | None = None,
    ) -> AgentToolLoopResponse:
        trace_id = trace_id or str(uuid.uuid4())
        # Dynamic max_iterations from agent definition
        effective_max_iterations = self._resolve_max_iterations(step_input)
        messages = self._initial_messages(agent_id, context, step_input)
        results: list[AgentToolResult] = []
        permission_rules = self._permission_rules(agent_id, step_input)
        recent_calls: list[tuple[str, str]] = []
        recent_tool_names: list[str] = []
        total_input_tokens = 0
        total_output_tokens = 0
        parse_repair_count = 0
        protocol_status = "ok"
        last_model_output_preview = ""
        loop_start_time = perf_counter()

        for _iteration in range(effective_max_iterations):
            # --- Phase 4: Context compression ---
            messages = self.context_manager.compress(messages)

            iteration_start = perf_counter()
            content = await model_call(messages)
            last_model_output_preview = self._preview(content)

            # --- Phase 6: Token estimation ---
            input_tokens = estimate_tokens(messages)
            output_tokens = estimate_tokens([{"role": "assistant", "content": content}])
            total_input_tokens += input_tokens
            total_output_tokens += output_tokens

            # --- Phase 1: JSON sanitization + retry ---
            sanitized = _sanitize_model_output(content)
            request = self._try_parse_request(sanitized)
            if request is None:
                if _looks_like_final_text(content):
                    output = self._final_output(
                        {
                            "summary": content.strip(),
                            "risks": [],
                            "next_action": "请查看最终结果。",
                            "requires_approval": False,
                        },
                        results,
                    )
                    output.raw_output = content
                    protocol_status = "fallback_summary"
                    self._set_protocol_metadata(
                        project,
                        status=protocol_status,
                        last_output=last_model_output_preview,
                        parse_repair_count=parse_repair_count,
                        fallback_summary_used=True,
                    )
                    set_workflow_state(
                        self.repository,
                        project,
                        COMPLETED,
                        "模型返回普通文本，已作为最终结果收口。",
                        step_id=task.get("id"),
                        actor=agent_id,
                    )
                    return AgentToolLoopResponse(
                        output=output,
                        tool_calls=results,
                        trace_id=trace_id,
                        total_input_tokens=total_input_tokens,
                        total_output_tokens=total_output_tokens,
                        model_protocol_status=protocol_status,
                        last_model_output_preview=last_model_output_preview,
                        parse_repair_count=parse_repair_count,
                        fallback_summary_used=True,
                    )
                # Retry once with a correction prompt
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": (
                        "你的上一次输出不是合法的 JSON 对象。请重新输出一个纯 JSON 工具请求，"
                        "不要包含 Markdown 格式或多余文本。格式：{\"thought\":\"...\",\"tool\":\"...\",\"arguments\":{...}}"
                    ),
                })
                parse_repair_count += 1
                retry_content = await model_call(messages)
                last_model_output_preview = self._preview(retry_content)
                retry_input_tokens = estimate_tokens(messages)
                retry_output_tokens = estimate_tokens([{"role": "assistant", "content": retry_content}])
                total_input_tokens += retry_input_tokens
                total_output_tokens += retry_output_tokens

                retry_sanitized = _sanitize_model_output(retry_content)
                request = self._try_parse_request(retry_sanitized)
                if request is None:
                    fallback_text = retry_content if _looks_like_final_text(retry_content) else content
                    if _looks_like_final_text(fallback_text):
                        set_workflow_state(
                            self.repository,
                            project,
                            COMPLETED,
                            "模型返回普通文本，已作为最终结果收口。",
                            step_id=task.get("id"),
                            actor=agent_id,
                        )
                        output = self._final_output(
                            {
                                "summary": fallback_text.strip(),
                                "risks": [],
                                "next_action": "请查看最终结果。",
                                "requires_approval": False,
                            },
                            results,
                        )
                        output.raw_output = fallback_text
                        return AgentToolLoopResponse(
                            output=output,
                            tool_calls=results,
                            trace_id=trace_id,
                            total_input_tokens=total_input_tokens,
                            total_output_tokens=total_output_tokens,
                            model_protocol_status="fallback_summary",
                            last_model_output_preview=last_model_output_preview,
                            parse_repair_count=parse_repair_count,
                            fallback_summary_used=True,
                        )
                    protocol_status = "needs_manual_review"
                    self._set_protocol_metadata(
                        project,
                        status=protocol_status,
                        last_output=last_model_output_preview,
                        parse_repair_count=parse_repair_count,
                        fallback_summary_used=False,
                    )
                    set_workflow_state(
                        self.repository,
                        project,
                        NEEDS_MANUAL_REVIEW,
                        "模型输出不是可解析的工具 JSON，重试后仍失败，需要人工审查。",
                        step_id=task.get("id"),
                        actor=agent_id,
                    )
                    return AgentToolLoopResponse(
                        needs_manual_review=True,
                        tool_calls=results,
                        output=AgentOutput(
                            summary="模型输出不是可解析的工具 JSON，重试后仍失败，需要人工审查。",
                            raw_output=retry_content,
                            needs_manual_review=True,
                            requires_approval=True,
                            next_action="请检查原始输出后重试。",
                        ),
                        trace_id=trace_id,
                        total_input_tokens=total_input_tokens,
                        total_output_tokens=total_output_tokens,
                        model_protocol_status=protocol_status,
                        last_model_output_preview=last_model_output_preview,
                        parse_repair_count=parse_repair_count,
                    )
                content = retry_content
                sanitized = retry_sanitized
                protocol_status = "repaired"

            self._set_protocol_metadata(
                project,
                status=protocol_status,
                last_output=last_model_output_preview,
                parse_repair_count=parse_repair_count,
                fallback_summary_used=False,
            )

            # --- Phase 1: Enhanced repeat detection ---
            call_fingerprint = (request.tool, json.dumps(request.arguments, ensure_ascii=False, sort_keys=True))
            recent_calls.append(call_fingerprint)
            recent_tool_names.append(request.tool)

            # Check exact fingerprint repeats (3 consecutive)
            exact_repeat = len(recent_calls) >= 3 and recent_calls[-1] == recent_calls[-2] == recent_calls[-3]
            # Check tool-name-only repeats (4 consecutive same tool with no finalize)
            tool_name_repeat = (
                len(recent_tool_names) >= 4
                and len(set(recent_tool_names[-4:])) == 1
                and recent_tool_names[-1] != "finalize"
            )

            if exact_repeat or tool_name_repeat:
                reason = (
                    f"检测到重复工具调用：{request.tool}，已阻断循环。"
                    if exact_repeat
                    else f"检测到工具 {request.tool} 连续调用 4 次无进展，已阻断循环。"
                )
                set_workflow_state(
                    self.repository,
                    project,
                    NEEDS_MANUAL_REVIEW,
                    reason,
                    step_id=task.get("id"),
                    actor=agent_id,
                    extra={"blocked_state": {"tool": request.tool, "reason": "repeated_tool_call"}},
                )
                self.repository.add_event(
                    project["id"],
                    task.get("id"),
                    "tool_loop_blocked",
                    agent_id,
                    reason,
                    {"tool_name": request.tool, "arguments": request.arguments, "trace_id": trace_id},
                )
                return AgentToolLoopResponse(
                    needs_manual_review=True,
                    tool_calls=results,
                    output=AgentOutput(
                        summary="检测到重复工具调用，已阻断并等待人工处理。",
                        needs_manual_review=True,
                        requires_approval=True,
                        next_action="请人工确认后重试，或调整目标描述。",
                    ),
                    trace_id=trace_id,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                )

            started_at = datetime.now().isoformat()
            start_time = perf_counter()
            set_workflow_state(
                self.repository,
                project,
                state_for_tool(request.tool),
                self._tool_message(request.tool, "started"),
                step_id=task.get("id"),
                actor=agent_id,
            )
            call = self.repository.add_tool_call(
                workflow_id=project["id"],
                step_id=task.get("id"),
                agent_id=agent_id,
                tool_name=request.tool,
                arguments={
                    **request.arguments,
                    "_raw_model_output": content,
                    "_sanitized_model_output": sanitized,
                    "_protocol_repair_attempted": protocol_status == "repaired",
                },
                status="running",
                started_at=started_at,
            )
            self.repository.add_event(
                project["id"],
                task.get("id"),
                "tool_call_started",
                agent_id,
                self._tool_message(request.tool, "started"),
                {"tool_call_id": call["id"], "tool_name": request.tool, "arguments": request.arguments, "trace_id": trace_id},
            )
            result = self.executor.execute(
                request,
                workflow_id=project["id"],
                step_id=task.get("id"),
                agent_id=agent_id,
                project=project,
                permission_rules=permission_rules,
                replay_of_call_id=call.get("id"),
            )
            if request.tool == "delegate_agent" and result.status == "completed" and delegate_call is not None:
                result = await delegate_call(agent_id, request.arguments, context, step_input)
            duration_ms = int((perf_counter() - start_time) * 1000)
            completed_at = datetime.now().isoformat()
            self.repository.update_tool_call(
                call["id"],
                status=result.status,
                result_summary=result.summary,
                result_payload={
                    **(result.payload or {}),
                    "_permission_decision": result.permission_decision,
                    "_blocked_reason": result.blocked_reason,
                    "_replay_of_call_id": result.replay_of_call_id,
                    "_trace_id": trace_id,
                    "_raw_model_output": content,
                    "_sanitized_model_output": sanitized,
                    "_protocol_repair_attempted": protocol_status == "repaired",
                },
                error=result.error,
                completed_at=completed_at,
                duration_ms=duration_ms,
            )
            if result.permission_decision == "ask":
                self.repository.add_event(
                    project["id"],
                    task.get("id"),
                    "permission_asked",
                    agent_id,
                    result.blocked_reason or f"权限审批请求：{request.tool}",
                    {"tool_call_id": call["id"], "tool_name": request.tool, "trace_id": trace_id},
                )
            elif result.permission_decision == "deny":
                self.repository.add_event(
                    project["id"],
                    task.get("id"),
                    "permission_denied",
                    agent_id,
                    result.blocked_reason or f"权限拒绝：{request.tool}",
                    {"tool_call_id": call["id"], "tool_name": request.tool, "trace_id": trace_id},
                )
            self.repository.add_event(
                project["id"],
                task.get("id"),
                "tool_call_completed" if result.status == "completed" else "tool_call_failed",
                agent_id,
                result.summary or self._tool_message(request.tool, result.status),
                {
                    "tool_call_id": call["id"],
                    "tool_name": request.tool,
                    "status": result.status,
                    "summary": result.summary,
                    "error": result.error,
                    "permission_decision": result.permission_decision,
                    "blocked_reason": result.blocked_reason,
                    "trace_id": trace_id,
                },
            )
            results.append(result)

            # --- Phase 6: Timeout warning ---
            elapsed = perf_counter() - loop_start_time
            if elapsed > _STEP_TIMEOUT_WARNING_SECONDS:
                self.repository.add_event(
                    project["id"],
                    task.get("id"),
                    "step_timeout_warning",
                    agent_id,
                    f"工具循环已运行 {elapsed:.1f} 秒，超过 {_STEP_TIMEOUT_WARNING_SECONDS} 秒阈值",
                    {"elapsed_seconds": round(elapsed, 1), "iteration": _iteration + 1, "trace_id": trace_id},
                )

            if result.status == "blocked":
                set_workflow_state(
                    self.repository,
                    project,
                    WAITING_PERMISSION if result.permission_decision == "ask" else NEEDS_MANUAL_REVIEW,
                    result.blocked_reason or "工具调用被权限门禁阻塞。",
                    step_id=task.get("id"),
                    actor=agent_id,
                    extra={
                        "permission_pending": result.permission_decision == "ask",
                        "latest_blocked_tool": request.tool,
                        "blocked_state": {
                            "tool": request.tool,
                            "reason": result.blocked_reason,
                            "permission_decision": result.permission_decision,
                        },
                    },
                )
                return AgentToolLoopResponse(
                    output=AgentOutput(
                        summary=result.summary or "工具调用被权限门禁阻塞。",
                        risks=[result.blocked_reason] if result.blocked_reason else [],
                        next_action="请审批权限请求后重试步骤。",
                        requires_approval=True,
                        artifacts=[
                            {
                                "type": "tool_trace",
                                "title": "工具调用记录",
                                "payload": {"results": [item.model_dump() for item in results]},
                            }
                        ],
                    ),
                    tool_calls=results,
                    trace_id=trace_id,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                )

            if request.tool == "finalize":
                set_workflow_state(
                    self.repository,
                    project,
                    COMPLETED,
                    str(request.arguments.get("summary") or "Agent 已生成最终结果。"),
                    step_id=task.get("id"),
                    actor=agent_id,
                )
                output = self._final_output(request.arguments, results)
                return AgentToolLoopResponse(
                    output=output,
                    tool_calls=results,
                    trace_id=trace_id,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                )

            # --- Phase 4: Trim large observation payloads ---
            observation = {
                "tool": result.tool,
                "status": result.status,
                "summary": result.summary,
                "payload": result.payload,
                "error": result.error,
                "permission_decision": result.permission_decision,
                "blocked_reason": result.blocked_reason,
            }
            observation_text = json.dumps(observation, ensure_ascii=False, indent=2)
            observation_text = self.context_manager.trim_large_payload(observation_text)

            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": "工具结果如下。请继续输出下一个工具 JSON，或调用 finalize：\n"
                    + observation_text,
                }
            )

        fallback = self._fallback_summary_output(results, project)
        if fallback:
            protocol_status = "fallback_summary"
            self._set_protocol_metadata(
                project,
                status=protocol_status,
                last_output=last_model_output_preview,
                parse_repair_count=parse_repair_count,
                fallback_summary_used=True,
            )
            set_workflow_state(
                self.repository,
                project,
                COMPLETED,
                fallback.summary,
                step_id=task.get("id"),
                actor=agent_id,
            )
            return AgentToolLoopResponse(
                tool_calls=results,
                output=fallback,
                trace_id=trace_id,
                total_input_tokens=total_input_tokens,
                total_output_tokens=total_output_tokens,
                model_protocol_status=protocol_status,
                last_model_output_preview=last_model_output_preview,
                parse_repair_count=parse_repair_count,
                fallback_summary_used=True,
            )

        protocol_status = "needs_manual_review"
        self._set_protocol_metadata(
            project,
            status=protocol_status,
            last_output=last_model_output_preview,
            parse_repair_count=parse_repair_count,
            fallback_summary_used=False,
        )
        return AgentToolLoopResponse(
            needs_manual_review=True,
            tool_calls=results,
            output=self._manual_review_output(
                summary="工具循环达到最大轮数，需要人工确认。",
                next_action="请查看工具调用记录后决定是否重试。",
                results=results,
            ),
            trace_id=trace_id,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            model_protocol_status=protocol_status,
            last_model_output_preview=last_model_output_preview,
            parse_repair_count=parse_repair_count,
        )

    def _try_parse_request(self, content: str) -> AgentToolRequest | None:
        """Attempt to parse an AgentToolRequest from sanitized content."""
        try:
            payload = json.loads(content)
            if isinstance(payload, list):
                payload = next((item for item in payload if isinstance(item, dict)), None)
            if not isinstance(payload, dict):
                return None
            for wrapper_key in ("tool_call", "toolCall", "request", "action", "function_call", "functionCall"):
                wrapped = payload.get(wrapper_key)
                if isinstance(wrapped, dict):
                    payload = wrapped
                    break
            tool = payload.get("tool") or payload.get("tool_name") or payload.get("name")
            arguments = (
                payload.get("arguments")
                if isinstance(payload.get("arguments"), dict)
                else payload.get("args")
                if isinstance(payload.get("args"), dict)
                else payload.get("input")
                if isinstance(payload.get("input"), dict)
                else payload.get("parameters")
                if isinstance(payload.get("parameters"), dict)
                else {}
            )
            if not tool:
                return None
            return AgentToolRequest(
                thought=str(payload.get("thought") or payload.get("reason") or payload.get("reasoning") or ""),
                tool=tool,
                arguments=arguments,
            )
        except Exception:
            return None

    def _preview(self, content: str, limit: int = 1000) -> str:
        text = (content or "").strip()
        return text[:limit]

    def _set_protocol_metadata(
        self,
        project: dict[str, Any],
        *,
        status: str,
        last_output: str,
        parse_repair_count: int,
        fallback_summary_used: bool,
    ) -> None:
        metadata = dict(project.get("metadata") or {})
        metadata["model_protocol_status"] = status
        metadata["last_model_output_preview"] = last_output
        metadata["parse_repair_count"] = parse_repair_count
        metadata["fallback_summary_used"] = fallback_summary_used
        self.repository.update_project(project["id"], metadata=metadata)
        project["metadata"] = metadata

    def _manual_review_output(
        self,
        *,
        summary: str,
        next_action: str,
        results: list[AgentToolResult],
        raw_output: str | None = None,
    ) -> AgentOutput:
        return AgentOutput(
            summary=summary,
            raw_output=raw_output,
            needs_manual_review=True,
            requires_approval=True,
            next_action=next_action,
            artifacts=[
                {
                    "type": "tool_trace",
                    "title": "工具调用记录",
                    "payload": {"results": [item.model_dump() for item in results]},
                }
            ],
        )

    def _fallback_summary_output(self, results: list[AgentToolResult], project: dict[str, Any]) -> AgentOutput | None:
        actions = self.repository.list_action_proposals(project["id"])
        if not actions:
            return None
        failed_tools = [item for item in results if item.status in {"failed", "blocked"}]
        if failed_tools:
            return None
        changed_files: list[str] = []
        commands: list[list[str]] = []
        failed_actions: list[str] = []
        for action in actions:
            changed_files.extend(action.get("changed_files") or [])
            payload = action.get("payload") or {}
            if action.get("action_type") == "command" and isinstance(payload.get("command"), list):
                commands.append([str(item) for item in payload["command"]])
            if action.get("status") == "failed":
                failed_actions.append(action.get("title") or action.get("id"))
        verification = "部分失败" if failed_actions else "已执行" if actions else "未运行"
        summary = "Agent 已完成可执行动作，但模型未调用 finalize，系统已根据动作和执行记录生成兜底总结。"
        if changed_files:
            summary += f" 变更文件：{', '.join(dict.fromkeys(changed_files))}。"
        if commands:
            summary += f" 验证命令：{'; '.join(' '.join(cmd) for cmd in commands)}。"
        if failed_actions:
            summary += f" 仍需处理失败动作：{', '.join(failed_actions)}。"
        return self._final_output(
            {
                "summary": summary,
                "tasks": ["生成动作建议", "执行自动策略", "汇总执行结果"],
                "risks": ["模型未显式调用 finalize，结果由系统兜底生成。"],
                "changed_files": list(dict.fromkeys(changed_files)),
                "commands": commands,
                "verification": verification,
                "next_action": "请检查自动生成的总结和动作执行结果。",
                "requires_approval": bool(failed_actions),
            },
            results,
        )

    def _resolve_max_iterations(self, step_input: dict[str, Any]) -> int:
        """Get max_iterations from agent definition, falling back to instance default."""
        agent = step_input.get("agent") or {}
        if isinstance(agent, dict):
            agent_max = agent.get("max_iterations")
            if isinstance(agent_max, int) and agent_max > 0:
                return agent_max
        return self.max_iterations

    def _initial_messages(
        self,
        agent_id: str,
        context: RuntimeExecutionContext,
        step_input: dict[str, Any],
    ) -> list[dict[str, str]]:
        agent = step_input.get("agent") or {}
        step = step_input.get("step") or {}
        tools = self._allowed_tools(agent_id)
        payload = {
            "goal": context.goal,
            "project_path": context.project_path,
            "project_context": context.project_context,
            "chat_context": context.chat_context,
            "memory_context": context.memory_context,
            "artifact_context": context.artifact_context,
            "context_pack": context.context_pack,
            "context_sources": context.context_sources,
            "current_step": step,
            "previous_outputs": step_input.get("previous_outputs", []),
            "allowed_tools": tools,
            "tool_protocol": {
                "request": {"thought": "简短判断", "tool": "search_code", "arguments": {"query": "AgentRunCard"}},
                "finalize": {
                    "thought": "完成",
                    "tool": "finalize",
                    "arguments": {
                        "summary": "已完成",
                        "tasks": ["完成项 1"],
                        "risks": [],
                        "changed_files": [],
                        "commands": [],
                        "verification": "未运行",
                        "next_action": "请审批生成的动作建议",
                    },
                },
            },
            "recommended_loop": [
                "inspect_project",
                "detect_project_commands",
                "search_code/read_file",
                "propose_patch",
                "propose_command",
                "read_execution_result 或 read_test_failures",
                "finalize",
            ],
            "safety": [
                "每次只输出一个 JSON 工具请求，不输出 Markdown。",
                "只读工具会自动执行。",
                "写文件必须使用 propose_patch；payload 可使用 files 或 format=unified_diff + diff。",
                "运行命令必须使用 propose_command；command 必须是 argv 数组，例如 [\"npm\",\"run\",\"typecheck\"]。",
                "如果需要只读协作，可以使用 delegate_agent 委派允许的子 Agent。",
                "不能凭空猜文件路径，修改前必须 inspect/search/read。",
                "最终必须调用 finalize，并总结完成项、变更文件、验证命令、失败/风险和下一步。",
            ],
        }
        system_prompt = agent.get("system_prompt") or "你是一个多 Agent 工作流中的开发 Agent。"
        if agent_id == "reviewer":
            system_prompt += "\n你不能调用 propose_patch，只能审查、读取结果、建议验证命令。"
        elif agent_id == "implementer":
            system_prompt += "\n你必须按 inspect_project -> detect_project_commands -> search/read -> propose_patch -> propose_command -> finalize 的开发闭环工作。"
        return [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": "请按工具协议工作。严格输出单个 JSON 对象。\n"
                + json.dumps(payload, ensure_ascii=False, indent=2),
            },
        ]

    def _allowed_tools(self, agent_id: str) -> list[str]:
        base = [
            "list_files",
            "search_code",
            "read_file",
            "inspect_project",
            "detect_project_commands",
            "get_git_status",
            "get_git_diff",
            "list_changed_files",
            "read_execution_result",
            "read_test_failures",
            "finalize",
        ]
        if agent_id == "planner":
            return base + ["delegate_agent"]
        if agent_id == "implementer":
            return base + ["propose_patch", "propose_command", "delegate_agent"]
        if agent_id == "reviewer":
            return base + ["propose_command"]
        return base

    def _permission_rules(self, agent_id: str, step_input: dict[str, Any]) -> list[PermissionRule]:
        config = step_input.get("agent_permissions")
        if isinstance(config, list):
            rules: list[PermissionRule] = []
            for item in config:
                if isinstance(item, dict):
                    rules.append(PermissionRule(**item))
                elif isinstance(item, PermissionRule):
                    rules.append(item)
            if rules:
                return rules
        return default_rules_for_agent(agent_id)

    def _final_output(self, arguments: dict[str, Any], results: list[AgentToolResult]) -> AgentOutput:
        artifacts: list[dict[str, Any]] = [
            {
                "type": "tool_trace",
                "title": "工具调用记录",
                "payload": {"results": [item.model_dump() for item in results]},
            },
            {
                "type": "final_summary",
                "title": "最终交付摘要",
                "payload": {
                    "changed_files": arguments.get("changed_files") if isinstance(arguments.get("changed_files"), list) else [],
                    "commands": arguments.get("commands") if isinstance(arguments.get("commands"), list) else [],
                    "verification": arguments.get("verification") or "",
                },
            },
        ]
        tasks = arguments.get("tasks") if isinstance(arguments.get("tasks"), list) else []
        normalized_tasks = [
            item if isinstance(item, dict) else {"title": str(item), "status": "completed"}
            for item in tasks
        ]
        return AgentOutput(
            summary=str(arguments.get("summary") or "Agent 工具循环已完成。"),
            tasks=normalized_tasks,
            risks=arguments.get("risks") if isinstance(arguments.get("risks"), list) else [],
            artifacts=artifacts,
            next_action=str(arguments.get("next_action") or "请查看产物和动作建议。"),
            requires_approval=bool(arguments.get("requires_approval", True)),
        )

    def _tool_message(self, tool_name: str, status: str) -> str:
        labels = {
            "list_files": "列出文件",
            "search_code": "搜索代码",
            "read_file": "读取文件",
            "inspect_project": "检查项目结构",
            "detect_project_commands": "识别验证命令",
            "get_git_status": "读取变更状态",
            "get_git_diff": "读取变更 diff",
            "list_changed_files": "列出变更文件",
            "propose_patch": "生成补丁建议",
            "propose_command": "生成命令建议",
            "read_execution_result": "读取执行结果",
            "read_test_failures": "读取失败摘要",
            "delegate_agent": "委派子 Agent",
            "finalize": "完成总结",
        }
        return f"{labels.get(tool_name, tool_name)}：{status}"
