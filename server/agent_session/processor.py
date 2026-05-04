from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from .policy import evaluate_agent_action_policy
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
from .tools import AgentToolRegistry, parse_tool_request


ModelCall = Callable[[list[dict[str, str]]], Awaitable[str]]


READ_TOOLS = {"read", "search", "glob", "collect_context", "read_execution"}
CONTEXT_TOOLS = {"read", "search", "glob", "collect_context", "detect_project_commands"}
MAX_REPAIR_ATTEMPTS = DEFAULT_MAX_REPAIR_ATTEMPTS


class AgentSessionProcessor:
    def __init__(
        self,
        repository: AgentSessionRepository,
        tools: AgentToolRegistry | None = None,
        max_iterations: int = 8,
    ):
        self.repository = repository
        self.tools = tools or AgentToolRegistry()
        self.max_iterations = max_iterations

    async def prompt(
        self,
        session_id: str,
        content: str,
        *,
        model_call: ModelCall | None = None,
    ) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        if not session:
            raise ValueError("Agent session not found")
        metadata = self._ensure_metadata(session)
        metadata["current_goal"] = content
        metadata = set_phase(metadata, "running")
        session = self.repository.update_session(session_id, status="running", metadata=metadata)
        self._event(session_id, "session_started", "Agent 开始处理请求", {"content": content})
        self.repository.add_part(session_id, "text", status="completed", title="请求", content=content)

        messages = self._initial_messages(session, content)
        if model_call is None:
            model_call = self._fallback_model_call

        for _ in range(self.max_iterations):
            raw = await model_call(messages)
            request = parse_tool_request(raw)
            if request is None:
                self.repository.add_part(session_id, "text", status="completed", content=raw)
                messages.append({"role": "assistant", "content": raw})
                continue

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
                    payload={"tool": tool_name, "arguments": args},
                )
                self.repository.update_session(session_id, status="waiting_permission")
                self._event(session_id, "permission_asked", f"未知工具需要确认：{tool_name}", {"part_id": part["id"]})
                return self._with_parts(session_id)

            session = self.repository.get_session(session_id) or session
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
                    payload={"guidance": guidance, "required_tools": ["collect_context", "read", "search"]},
                )
                self._event(session_id, "tool_call_completed", guidance, {"part_id": result_part["id"], "tool": tool_name})
                observation = {"tool": tool_name, "status": "blocked", "summary": guidance, "payload": result_part["payload"]}
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": "工具结果：\n" + json.dumps(observation, ensure_ascii=False)})
                continue
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
                        payload={"guidance": guidance, "missing_context": missing_context, "required_tools": ["read", "search", "collect_context"]},
                    )
                    self._event(session_id, "tool_call_completed", guidance, {"part_id": result_part["id"], "tool": tool_name})
                    observation = {"tool": tool_name, "status": "blocked", "summary": guidance, "payload": result_part["payload"]}
                    messages.append({"role": "assistant", "content": raw})
                    messages.append({"role": "user", "content": "工具结果：\n" + json.dumps(observation, ensure_ascii=False)})
                    continue
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
                        payload={"guidance": guidance, "required_tools": ["detect_project_commands", "collect_context"]},
                    )
                    self._event(session_id, "tool_call_completed", guidance, {"part_id": result_part["id"], "tool": tool_name})
                    observation = {"tool": tool_name, "status": "blocked", "summary": guidance, "payload": result_part["payload"]}
                    messages.append({"role": "assistant", "content": raw})
                    messages.append({"role": "user", "content": "工具结果：\n" + json.dumps(observation, ensure_ascii=False)})
                    continue

            call_part = self.repository.add_part(
                session_id,
                "tool_call",
                status="running",
                title=tool.description,
                content=self._tool_call_text(tool_name, args),
                payload={"tool": tool_name, "arguments": args},
            )
            self._event(session_id, "tool_call_started", call_part.get("content") or tool.description, {"part_id": call_part["id"], "tool": tool_name})

            if tool_name == "bash_command":
                command_payload = args.get("payload") if isinstance(args.get("payload"), dict) else args
                policy = evaluate_agent_action_policy(session, "command", command_payload, set(metadata.get("touched_paths") or []))
                result = self._handle_command(session, call_part["id"], command_payload, policy, tool, messages, raw)
                if result is not None:
                    return result
                continue

            result = tool.execute(args, self._context(session))
            self.repository.update_part(call_part["id"], status=result.status)

            if tool_name == "patch":
                patch_payload = dict(result.payload.get("payload") or {})
                policy = evaluate_agent_action_policy(session, "diff", patch_payload, set(metadata.get("touched_paths") or []))
                part_payload = dict(result.payload)
                part_payload.update(policy)
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
                    return self._stop_with_summary(session_id, "needs_manual_review", policy["policy_reason"], part_id=part["id"])
                if policy["execution_mode"] == "approval_required":
                    metadata = set_phase(metadata, "waiting_approval")
                    self.repository.update_session(session_id, status="waiting_approval", metadata=metadata)
                    self._event(session_id, "action_proposed", policy["policy_reason"], {"part_id": part["id"], **policy})
                    return self._with_parts(session_id)
                patch_result = self.tools.apply_patch_payload(patch_payload, self._context(session))
                applied_payload = dict(part_payload)
                applied_payload.update(patch_result.payload)
                status = "executed" if patch_result.status == "completed" else "failed"
                self.repository.update_part(part["id"], status=status, payload=applied_payload, content=patch_result.summary if status == "executed" else patch_result.error)
                if status == "failed":
                    metadata = set_phase(self._ensure_metadata(self.repository.get_session(session_id) or session), "needs_manual_review")
                    metadata = record_diff(metadata, part["id"], applied_payload.get("changed_files") or [])
                    self.repository.update_session(session_id, metadata=metadata)
                    return self._stop_with_summary(session_id, "needs_manual_review", patch_result.error or "补丁执行失败", part_id=part["id"])
                metadata = set_phase(self._ensure_metadata(self.repository.get_session(session_id) or session), "verifying")
                metadata = record_diff(metadata, part["id"], applied_payload.get("changed_files") or [])
                self.repository.update_session(session_id, metadata=metadata)
                self._event(session_id, "action_executed", patch_result.summary, {"part_id": part["id"], **applied_payload})
                observation = {
                    "tool": tool_name,
                    "status": "completed",
                    "summary": "补丁已自动执行。下一步必须提出一个白名单验证命令；优先使用已识别的 commands。",
                    "payload": {**applied_payload, "available_commands": (metadata.get("detected_commands") or [])},
                }
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": "工具结果：\n" + json.dumps(observation, ensure_ascii=False)})
                continue

            if tool_name == "finalize":
                summary = self.repository.add_part(session_id, "summary", status="completed", title="最终结果", content=result.summary, payload=result.payload)
                metadata = set_phase(self._ensure_metadata(self.repository.get_session(session_id) or session), "completed")
                self.repository.update_session(session_id, status="completed", metadata=metadata)
                self._event(session_id, "summary_completed", result.summary, {"part_id": summary["id"]})
                return self._with_parts(session_id)
            else:
                result_part = self.repository.add_part(
                    session_id,
                    "tool_result",
                    status=result.status,
                    title=tool.description,
                    content=result.summary,
                    payload=result.payload,
                )
                self._event(session_id, "tool_call_completed", result.summary, {"part_id": result_part["id"], "tool": tool_name})
                if tool_name in CONTEXT_TOOLS and result.status == "completed":
                    self._record_context(session_id, result.payload)

            observation = {"tool": tool_name, "status": result.status, "summary": result.summary, "payload": result.payload, "error": result.error}
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "工具结果：\n" + json.dumps(observation, ensure_ascii=False)})

        return self._fallback_summary(session_id, "Agent 达到最大工具轮次，已根据当前执行记录生成总结。")

    def approve_part(self, part_id: str, approved: bool) -> dict[str, Any]:
        part = self.repository.get_part(part_id)
        if not part:
            raise ValueError("Agent part not found")
        if not approved:
            self.repository.update_part(part_id, status="blocked")
            metadata = set_phase(self._ensure_metadata(self.repository.get_session(part["session_id"]) or {}), "failed")
            self.repository.update_session(part["session_id"], status="failed", metadata=metadata)
            self._event(part["session_id"], "action_rejected", "动作已拒绝", {"part_id": part_id})
            return self._with_parts(part["session_id"])
        self.repository.update_part(part_id, status="approved")
        metadata = set_phase(self._ensure_metadata(self.repository.get_session(part["session_id"]) or {}), "waiting_approval")
        self.repository.update_session(part["session_id"], status="waiting_approval", metadata=metadata)
        self._event(part["session_id"], "action_approved", "动作已批准", {"part_id": part_id})
        return self._with_parts(part["session_id"])

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
            result = self.tools.get("bash_command").execute({"payload": part.get("payload") or {}}, self._context(session))  # type: ignore[union-attr]
        else:
            result = self.tools.apply_patch_payload((part.get("payload") or {}).get("payload") or part.get("payload") or {}, self._context(session))
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

    def _initial_messages(self, session: dict[str, Any], content: str) -> list[dict[str, str]]:
        tool_names = [tool.name for tool in self.tools.list()]
        return [
            {
                "role": "system",
                "content": (
                    "你是 Codex 风格的开发 Agent。直接推进任务，优先使用 collect_context/read/search 获取上下文。"
                    "每次只输出一个 JSON 工具请求，字段为 tool 和 arguments。"
                    f"可用工具：{', '.join(tool_names)}。"
                    "写文件必须用 patch，验证命令必须用 bash_command，完成时用 finalize。"
                ),
            },
            {"role": "user", "content": content},
        ]

    async def _fallback_model_call(self, _messages: list[dict[str, str]]) -> str:
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
    ) -> dict[str, Any] | None:
        session_id = session["id"]
        self.repository.update_part(call_part_id, status="completed" if policy["execution_mode"] != "blocked" else "blocked")
        part_payload = dict(command_payload)
        part_payload.update(policy)
        if policy["execution_mode"] == "blocked":
            part = self.repository.add_part(session_id, "command", status="blocked", title="验证命令", content=policy["policy_reason"], payload=part_payload)
            metadata = record_command(self._ensure_metadata(self.repository.get_session(session_id) or session), part["id"], policy["policy_reason"])
            metadata = set_phase(metadata, "needs_manual_review")
            self.repository.update_session(session_id, metadata=metadata)
            return self._stop_with_summary(session_id, "needs_manual_review", policy["policy_reason"], part_id=part["id"])
        if policy["execution_mode"] == "approval_required":
            part = self.repository.add_part(session_id, "command", status="pending", title="验证命令", content=policy["policy_reason"], payload=part_payload)
            metadata = record_command(self._ensure_metadata(self.repository.get_session(session_id) or session), part["id"])
            metadata = set_phase(metadata, "waiting_approval")
            self.repository.update_session(session_id, status="waiting_approval", metadata=metadata)
            self._event(session_id, "action_proposed", policy["policy_reason"], {"part_id": part["id"], **policy})
            return self._with_parts(session_id)

        metadata = set_phase(self._ensure_metadata(self.repository.get_session(session_id) or session), "verifying")
        self.repository.update_session(session_id, status="verifying", metadata=metadata)
        result = tool.execute({"payload": command_payload}, self._context(session))
        payload = dict(part_payload)
        payload.update(result.payload)
        part = self.repository.add_part(session_id, "command", status=result.status, title="验证命令", content=result.summary if result.status == "completed" else result.error, payload=payload)
        metadata = record_command(self._ensure_metadata(self.repository.get_session(session_id) or session), part["id"], None if result.status == "completed" else result.error or result.summary)
        self.repository.update_session(session_id, metadata=metadata)
        self._event(session_id, "command_completed" if result.status == "completed" else "command_failed", result.summary, {"part_id": part["id"], **payload})
        observation = {"tool": "bash_command", "status": result.status, "summary": result.summary, "payload": payload, "error": result.error}
        if result.status == "completed":
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "工具结果：\n" + json.dumps({**observation, "guidance": "验证通过。下一步必须调用 finalize，输出改动文件、验证命令、验证结果和剩余风险。"}, ensure_ascii=False)})
            return None

        metadata = self._ensure_metadata(self.repository.get_session(session_id) or session)
        attempts = int(metadata.get("repair_attempts") or 0)
        if attempts < int(metadata.get("max_repair_attempts") or MAX_REPAIR_ATTEMPTS):
            metadata = record_repair_attempt(metadata)
            self.repository.update_session(session_id, status="repairing", metadata=metadata)
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "工具结果：\n" + json.dumps({**observation, "guidance": "验证失败。请先调用 read_execution 或读取相关文件，基于 failure_summary 最多生成一次修复补丁，然后再次验证。"}, ensure_ascii=False)})
            return None
        detail = result.error or result.summary or "已达到最大修复次数。"
        return self._stop_with_summary(session_id, "needs_manual_review", f"验证失败，已达到最大修复次数。{detail}", part_id=part["id"])

    def _stop_with_summary(self, session_id: str, status: str, summary: str, *, part_id: str | None = None) -> dict[str, Any]:
        self.repository.add_part(session_id, "summary", status="completed", title="最终结果", content=summary, payload={"summary": summary, "blocked_part_id": part_id})
        metadata = set_phase(self._ensure_metadata(self.repository.get_session(session_id) or {}), status)
        self.repository.update_session(session_id, status=status, metadata=metadata)
        self._event(session_id, "session_blocked" if status == "needs_manual_review" else "session_failed", summary, {"part_id": part_id})
        return self._with_parts(session_id)

    def _fallback_summary(self, session_id: str, summary: str) -> dict[str, Any]:
        session = self.repository.get_session(session_id) or {}
        metadata = self._ensure_metadata(session)
        metadata = record_fallback_summary(metadata)
        self.repository.add_part(session_id, "summary", status="completed", title="最终结果", content=summary, payload={"summary": summary, "fallback": True})
        self.repository.update_session(session_id, status="needs_manual_review", metadata=metadata)
        self._event(session_id, "summary_completed", summary, {"fallback": True})
        return self._with_parts(session_id)

    def _with_parts(self, session_id: str) -> dict[str, Any]:
        session = self.repository.get_session(session_id) or {}
        session["parts"] = self.repository.list_parts(session_id)
        return session

    def _event(self, session_id: str, event_type: str, message: str, payload: dict[str, Any]) -> None:
        self.repository.add_event(session_id, event_type, message, payload)

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
