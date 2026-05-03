from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable

from agent_runtime.runner import resolve_saved_provider
from security.encryption import secure_storage

from .models import ChatAgentAcceptanceReport

AcceptanceModelCall = Callable[[list[dict[str, str]], str, str | None], Awaitable[str]]

ACTIVE_STATUSES = {"created", "running", "planning", "implementing", "reviewing"}


class AcceptanceReportGenerator:
    def __init__(self, model_call: AcceptanceModelCall | None = None):
        self.model_call = model_call

    def should_generate(self, workflow: dict[str, Any], observability: Any | None = None) -> bool:
        status = str(workflow.get("status") or "")
        if status in ACTIVE_STATUSES:
            return False
        if status in {"completed", "failed", "needs_manual_review"}:
            return True
        if status == "awaiting_approval":
            if self._latest_summary(workflow):
                return True
            actions = self._actions(observability)
            return bool(actions)
        return False

    async def generate(
        self,
        workflow: dict[str, Any],
        observability: Any | None = None,
    ) -> tuple[ChatAgentAcceptanceReport, str, str]:
        fallback = self.build_fallback(workflow, observability)
        try:
            raw = await self._call_model(workflow, observability, fallback)
            report = self._parse_model_report(raw)
            return report, "model", raw
        except Exception as exc:
            return fallback, "fallback", str(exc)

    def build_fallback(self, workflow: dict[str, Any], observability: Any | None = None) -> ChatAgentAcceptanceReport:
        status = str(workflow.get("status") or "")
        final_summary = self._latest_summary(workflow)
        metadata = workflow.get("metadata") if isinstance(workflow.get("metadata"), dict) else {}
        blocked_state = metadata.get("blocked_state") if isinstance(metadata, dict) else None
        blocked_reason = ""
        if isinstance(blocked_state, dict):
            blocked_reason = str(blocked_state.get("reason") or blocked_state.get("message") or "").strip()
        if not blocked_reason:
            blocked_reason = str(metadata.get("execution_state_message") or "").strip()

        actions = self._actions(observability)
        changed_files = sorted({path for action in actions for path in (action.get("changed_files") or [])})
        command_actions = [action for action in actions if action.get("action_type") == "command"]
        commands_run = [self._command_text(action) for action in command_actions if self._command_text(action)]
        failed_actions = [action for action in actions if action.get("status") == "failed" or action.get("failure_summary")]
        executed_actions = [action for action in actions if action.get("status") == "executed"]
        verification_result = self._verification_result(command_actions, failed_actions)

        if status == "needs_manual_review":
            result = "blocked"
        elif status == "failed" or failed_actions:
            result = "failed"
        elif status == "completed" and not failed_actions:
            result = "passed"
        elif executed_actions or final_summary:
            result = "partial"
        else:
            result = "blocked"

        completed_items: list[str] = []
        if final_summary:
            completed_items.append(final_summary)
        if executed_actions:
            completed_items.append(f"已执行 {len(executed_actions)} 个动作")
        if changed_files:
            completed_items.append(f"产生 {len(changed_files)} 个文件变更")

        summary = final_summary or self._summary_for_result(result, status)
        if result == "failed" and failed_actions:
            blocked_reason = blocked_reason or str(failed_actions[-1].get("failure_summary") or "动作执行失败")

        return ChatAgentAcceptanceReport(
            result=result,
            summary=summary,
            completed_items=completed_items,
            changed_files=changed_files,
            commands_run=commands_run,
            verification_result=verification_result,
            blocking_reason=blocked_reason if result in {"blocked", "failed"} else "",
            next_action=self._next_action(result, blocked_reason),
        )

    async def _call_model(
        self,
        workflow: dict[str, Any],
        observability: Any | None,
        fallback: ChatAgentAcceptanceReport,
    ) -> str:
        provider = str(workflow.get("provider") or "")
        model = workflow.get("model")
        messages = self._messages(workflow, observability, fallback)
        if self.model_call:
            return await self.model_call(messages, provider, model)

        key_data = secure_storage.get(f"cloud_{provider}_key") or {}
        api_key = key_data.get("api_key", "")
        if not provider or not api_key:
            raise RuntimeError("没有可用的云端模型配置")
        provider_instance = resolve_saved_provider(provider, key_data)
        if provider_instance is None:
            raise RuntimeError(f"不支持的云端服务商: {provider}")
        selected_model = model or key_data.get("default_model") or provider_instance.get_default_model()
        response = await provider_instance.chat(
            messages=messages,
            model=selected_model,
            api_key=api_key,
            temperature=0.1,
            max_tokens=1200,
        )
        return response.get("content", "") if isinstance(response, dict) else str(response)

    def _messages(
        self,
        workflow: dict[str, Any],
        observability: Any | None,
        fallback: ChatAgentAcceptanceReport,
    ) -> list[dict[str, str]]:
        payload = {
            "goal": workflow.get("goal"),
            "status": workflow.get("status"),
            "final_summary": self._latest_summary(workflow),
            "tool_calls": self._tool_call_summaries(observability),
            "actions": self._action_summaries(observability),
            "fallback_report": fallback.model_dump(),
        }
        return [
            {
                "role": "system",
                "content": (
                    "你是 Agent 执行验收员。只能根据输入中的真实执行记录评估结果，不能编造未发生的工具、文件或命令。"
                    "只返回 JSON，不要 Markdown。字段：result, summary, completed_items, changed_files, commands_run, "
                    "verification_result, blocking_reason, next_action。result 只能是 passed/partial/blocked/failed。"
                    "输出风格要像开发排查报告：summary 用一句话给结论；completed_items 每项尽量写成“文件或模块 —— 做了什么/修复了什么”。"
                    "如果任务被阻断，blocking_reason 必须具体说明等待审批、策略阻断或验证失败的原因，next_action 必须可执行。"
                ),
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
        ]

    def _parse_model_report(self, raw: str) -> ChatAgentAcceptanceReport:
        text = raw.strip()
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence:
            text = fence.group(1)
        elif not text.startswith("{"):
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                text = match.group(0)
        data = json.loads(text)
        return ChatAgentAcceptanceReport(
            result=data.get("result") if data.get("result") in {"passed", "partial", "blocked", "failed"} else "partial",
            summary=str(data.get("summary") or ""),
            completed_items=[str(item) for item in data.get("completed_items") or []],
            changed_files=[str(item) for item in data.get("changed_files") or []],
            commands_run=[str(item) for item in data.get("commands_run") or []],
            verification_result=str(data.get("verification_result") or ""),
            blocking_reason=str(data.get("blocking_reason") or ""),
            next_action=str(data.get("next_action") or ""),
        )

    def _actions(self, observability: Any | None) -> list[dict[str, Any]]:
        if observability is None:
            return []
        if isinstance(observability, dict):
            return list(observability.get("actions") or [])
        return [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in getattr(observability, "actions", [])]

    def _tool_call_summaries(self, observability: Any | None) -> list[dict[str, Any]]:
        if observability is None:
            return []
        calls = observability.get("tool_calls") if isinstance(observability, dict) else getattr(observability, "tool_calls", [])
        return [
            {
                "tool_name": call.get("tool_name") if isinstance(call, dict) else getattr(call, "tool_name", ""),
                "status": call.get("status") if isinstance(call, dict) else getattr(call, "status", ""),
                "summary": call.get("result_summary") if isinstance(call, dict) else getattr(call, "result_summary", ""),
            }
            for call in list(calls or [])[-12:]
        ]

    def _action_summaries(self, observability: Any | None) -> list[dict[str, Any]]:
        return [
            {
                "action_type": action.get("action_type"),
                "title": action.get("title"),
                "status": action.get("status"),
                "changed_files": action.get("changed_files") or [],
                "failure_summary": action.get("failure_summary") or "",
                "executions": action.get("executions") or [],
            }
            for action in self._actions(observability)
        ]

    def _latest_summary(self, workflow: dict[str, Any]) -> str:
        for step in reversed(workflow.get("steps") or workflow.get("tasks") or []):
            output = step.get("output") or step.get("output_data") or {}
            if isinstance(output, dict) and str(output.get("summary") or "").strip():
                return str(output.get("summary")).strip()
        return ""

    def _command_text(self, action: dict[str, Any]) -> str:
        command = (action.get("payload") or {}).get("command")
        return " ".join(str(part) for part in command) if isinstance(command, list) else str(command or "")

    def _verification_result(self, command_actions: list[dict[str, Any]], failed_actions: list[dict[str, Any]]) -> str:
        if failed_actions:
            return str(failed_actions[-1].get("failure_summary") or "验证或动作执行失败")
        if command_actions:
            executed = [action for action in command_actions if action.get("status") == "executed"]
            return "验证命令已通过" if executed else "验证命令尚未执行"
        return "未运行验证命令"

    def _summary_for_result(self, result: str, status: str) -> str:
        if result == "passed":
            return "任务已完成，未发现失败动作。"
        if result == "failed":
            return "任务执行过程中出现失败，需要查看失败摘要。"
        if result == "blocked":
            return "Agent 已暂停，等待人工确认后继续。"
        return f"任务已推进到 {status}，当前结果可用但仍需后续确认。"

    def _next_action(self, result: str, blocked_reason: str) -> str:
        if result == "passed":
            return "可以查看变更并继续下一步。"
        if result == "failed":
            return "请根据失败摘要修复，或重新发起 Agent 任务。"
        if result == "blocked":
            return blocked_reason or "请人工确认阻断原因后继续。"
        return "请审批待确认动作，或查看详情确认是否继续。"
