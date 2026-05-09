"""Generic runtime runner for provider resolution, prompt building and parsing."""

from __future__ import annotations

import json
from typing import Any

from ai.gateway import AnthropicMessagesProvider, OpenAICompatibleProvider, get_provider
from digital_team.models import AgentOutput
from digital_team.prompts import ceo_prompt, developer_prompt, reviewer_prompt
from security.encryption import secure_storage

from .definitions import RuntimeExecutionContext
from .tool_loop import AgentToolLoop
from .tool_models import AgentToolResult
from .tools import AgentToolExecutor


ACTION_ARTIFACT_GUIDE = {
    "patch": {
        "type": "patch",
        "title": "写入安全补丁",
        "description": "说明补丁用途。只能建议写入 project_path 内的相对路径。",
        "payload": {
            "files": [
                {
                    "path": "tmp/workflow-smoke.txt",
                    "content": "workflow action executed",
                }
            ]
        },
    },
    "command": {
        "type": "command",
        "title": "运行类型检查",
        "description": "验证建议补丁或项目状态。",
        "payload": {
            "command": ["npm", "run", "typecheck"],
            "timeout_seconds": 120,
        },
    },
}


def resolve_saved_provider(provider_name: str, key_data: dict[str, Any]):
    group_id = key_data.get("group_id", "")
    base_url = key_data.get("base_url", "")
    provider = get_provider(provider_name, group_id=group_id, base_url=base_url)
    if provider is not None:
        return provider

    interface_format = key_data.get("interface_format", "openai-compatible")
    default_model = key_data.get("default_model", "")
    if interface_format in {"openai-compatible", "openai-chat-completions"} and base_url:
        return OpenAICompatibleProvider(base_url=base_url, default_model=default_model)
    if interface_format == "anthropic-messages":
        return AnthropicMessagesProvider(base_url=base_url, default_model=default_model)
    return None


def parse_agent_output(content: str) -> AgentOutput:
    try:
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("Agent output is not a JSON object")
        return AgentOutput(**parsed)
    except Exception:
        return AgentOutput(
            summary="模型输出不是可解析的结构化 JSON，需要人工审查。",
            raw_output=content,
            needs_manual_review=True,
            requires_approval=True,
            next_action="请检查原始输出后重试或手动推进。",
        )


class AgentRuntimeRunner:
    def __init__(self, executor: AgentToolExecutor | None = None):
        self.executor = executor

    def _provider_for_context(self, context: RuntimeExecutionContext):
        key_data = secure_storage.get(f"cloud_{context.provider}_key") or {}
        api_key = key_data.get("api_key", "")
        if not api_key:
            raise RuntimeError(f"未配置 {context.provider} 的 API Key")

        provider = resolve_saved_provider(context.provider, key_data)
        if provider is None:
            raise RuntimeError(f"不支持的云端服务商: {context.provider}")
        selected_model = context.model or key_data.get("default_model") or provider.get_default_model()
        return provider, api_key, selected_model

    async def execute(
        self,
        agent_id: str,
        context: RuntimeExecutionContext,
        step_input: dict[str, Any] | None = None,
    ) -> AgentOutput:
        provider, api_key, selected_model = self._provider_for_context(context)
        messages = self._build_messages(agent_id, context, step_input or {})
        response = await provider.chat(
            messages=messages,
            model=selected_model,
            api_key=api_key,
            temperature=0.3,
            max_tokens=3000,
        )
        return parse_agent_output(response.get("content", ""))

    async def execute_tool_loop(
        self,
        agent_id: str,
        context: RuntimeExecutionContext,
        step_input: dict[str, Any],
        *,
        project: dict[str, Any],
        task: dict[str, Any],
        repository: Any,
        action_service: Any,
        trace_id: str | None = None,
    ) -> AgentOutput:
        provider, api_key, selected_model = self._provider_for_context(context)

        async def model_call(messages: list[dict[str, str]]) -> str:
            response = await provider.chat(
                messages=messages,
                model=selected_model,
                api_key=api_key,
                temperature=0.2,
                max_tokens=2200,
            )
            return response.get("content", "")

        async def delegate_call(
            parent_agent_id: str,
            arguments: dict[str, Any],
            delegate_context: RuntimeExecutionContext,
            raw_step_input: dict[str, Any],
        ) -> AgentToolResult:
            return await self.execute_subagent(
                parent_agent_id,
                arguments,
                delegate_context,
                raw_step_input,
                project=project,
                task=task,
                repository=repository,
            )

        loop = AgentToolLoop(
            repository=repository,
            executor=AgentToolExecutor(repository, action_service),
            max_iterations=6,
        )
        response = await loop.run(
            agent_id=agent_id,
            context=context,
            step_input=step_input,
            project=project,
            task=task,
            model_call=model_call,
            delegate_call=delegate_call,
            trace_id=trace_id,
        )
        return response.output

    async def execute_subagent(
        self,
        parent_agent_id: str,
        arguments: dict[str, Any],
        context: RuntimeExecutionContext,
        step_input: dict[str, Any],
        *,
        project: dict[str, Any],
        task: dict[str, Any],
        repository: Any,
    ) -> AgentToolResult:
        available = {
            item.get("id"): item
            for item in (step_input.get("available_subagents") or [])
            if isinstance(item, dict) and item.get("id")
        }
        target_id = str(arguments.get("agent_id") or "").strip()
        if not target_id:
            return AgentToolResult(tool="delegate_agent", status="failed", error="agent_id is required")
        if target_id not in list((step_input.get("agent") or {}).get("handoff_targets") or []):
            return AgentToolResult(tool="delegate_agent", status="failed", error=f"{parent_agent_id} cannot delegate to {target_id}")
        target = available.get(target_id)
        if not target:
            return AgentToolResult(tool="delegate_agent", status="failed", error=f"subagent {target_id} is not available")

        subagent_stack = list(context.metadata.get("subagent_stack") or [])
        if len(subagent_stack) >= 2:
            return AgentToolResult(tool="delegate_agent", status="failed", error="subagent depth limit reached")
        subgoal = str(arguments.get("task") or context.goal).strip() or context.goal

        metadata = dict(project.get("metadata") or {})
        metadata["active_agent_id"] = target_id
        repository.update_project(project["id"], metadata=metadata)
        repository.add_event(
            project["id"],
            task.get("id"),
            "subagent_started",
            target_id,
            f"子 Agent {target_id} 开始处理委派任务",
            {"parent_agent_id": parent_agent_id, "task": subgoal},
        )
        try:
            output = await self.execute(
                target_id,
                RuntimeExecutionContext(
                    workflow_id=context.workflow_id,
                    goal=subgoal,
                    project_path=context.project_path,
                    project_context=context.project_context,
                    chat_context=context.chat_context,
                    memory_context=context.memory_context,
                    artifact_context=context.artifact_context,
                    context_pack=context.context_pack,
                    context_sources=context.context_sources,
                    provider=context.provider,
                    model=context.model,
                    metadata={**context.metadata, "subagent_stack": [*subagent_stack, target_id]},
                ),
                {
                    "agent": target,
                    "step": {"step_key": f"subagent_{target_id}", "title": target.get("name", target_id)},
                    "previous_outputs": [],
                },
            )
            metadata = dict(project.get("metadata") or {})
            metadata["active_agent_id"] = parent_agent_id
            metadata["subagent_runs"] = [
                *(metadata.get("subagent_runs") or []),
                {
                    "agent_id": target_id,
                    "parent_agent_id": parent_agent_id,
                    "task": subgoal,
                    "status": "completed",
                    "summary": output.summary,
                },
            ]
            repository.update_project(project["id"], metadata=metadata)
            repository.add_event(
                project["id"],
                task.get("id"),
                "subagent_completed",
                target_id,
                f"子 Agent {target_id} 已返回结果",
                {"task": subgoal, "summary": output.summary},
            )
            return AgentToolResult(
                tool="delegate_agent",
                status="completed",
                summary=f"子 Agent {target_id} 已完成委派任务",
                payload={"agent_id": target_id, "task": subgoal, "output": output.model_dump()},
                permission_decision="allow",
            )
        except Exception as exc:
            metadata = dict(project.get("metadata") or {})
            metadata["active_agent_id"] = parent_agent_id
            repository.update_project(project["id"], metadata=metadata)
            repository.add_event(
                project["id"],
                task.get("id"),
                "subagent_failed",
                target_id,
                f"子 Agent {target_id} 执行失败：{exc}",
                {"task": subgoal},
            )
            return AgentToolResult(tool="delegate_agent", status="failed", error=str(exc), summary="子 Agent 执行失败")

    async def repair_after_action_failure(self, project: dict[str, Any], action: dict[str, Any]) -> AgentOutput:
        context = RuntimeExecutionContext(
            workflow_id=project["id"],
            goal=project["goal"],
            project_path=project.get("project_path"),
            provider=project["provider"],
            model=project.get("model"),
        )
        provider, api_key, selected_model = self._provider_for_context(context)
        latest_execution = (action.get("executions") or [])[-1] if action.get("executions") else {}
        messages = [
            {
                "role": "system",
                "content": (
                    "你是修复失败动作的 Implementer。请基于失败输出生成新的 action artifact。"
                    "只允许输出 JSON AgentOutput；不要自动执行；需要改文件时输出 patch，"
                    "需要验证时输出 command。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "goal": project.get("goal"),
                        "failed_action": action,
                        "latest_execution": latest_execution,
                        "required_json_schema": {
                            "summary": "string",
                            "tasks": "array",
                            "risks": "array",
                            "artifacts": [ACTION_ARTIFACT_GUIDE["patch"], ACTION_ARTIFACT_GUIDE["command"]],
                            "next_action": "string",
                            "requires_approval": True,
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]
        response = await provider.chat(
            messages=messages,
            model=selected_model,
            api_key=api_key,
            temperature=0.2,
            max_tokens=2200,
        )
        return parse_agent_output(response.get("content", ""))

    def _build_messages(
        self,
        agent_id: str,
        context: RuntimeExecutionContext,
        step_input: dict[str, Any],
    ) -> list[dict[str, str]]:
        agent = step_input.get("agent") or {}
        step = step_input.get("step") or {}
        system_prompt = agent.get("system_prompt") or ""
        if system_prompt:
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
                "step_input": step_input,
                "output_requirements": agent.get("output_requirements", ""),
                "required_json_schema": {
                    "summary": "string",
                    "tasks": "array",
                    "risks": "array",
                    "artifacts": [
                        "普通产物对象",
                        ACTION_ARTIFACT_GUIDE["patch"],
                        ACTION_ARTIFACT_GUIDE["command"],
                    ],
                    "next_action": "string",
                    "requires_approval": "boolean",
                },
                "action_artifact_policy": {
                    "planner": "只输出计划、验收标准和风险，不输出 patch 或 command action。",
                    "implementer": "如果目标涉及代码或文件变更，优先输出 patch action；如果需要验证，输出 command action。",
                    "reviewer": "可以输出 command action 用于建议测试或检查，不输出 patch action。",
                    "safety": "所有 action 只是建议，系统会等待用户审批后才执行。不要建议删除文件、不要建议 workspace 外路径、不要建议非白名单命令。",
                },
            }
            role_instruction = self._action_role_instruction(agent_id)
            return [
                {"role": "system", "content": f"{system_prompt}\n\n{role_instruction}"},
                {
                    "role": "user",
                    "content": (
                        "请严格输出 JSON 对象，不要输出 Markdown。\n"
                        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
                    ),
                },
            ]
        if agent_id == "planner":
            return ceo_prompt(context.goal, context.project_path, context.project_context)
        if agent_id == "implementer":
            return developer_prompt(
                context.goal,
                step_input.get("ceo_output", {}),
                context.project_path,
                context.project_context,
            )
        if agent_id == "reviewer":
            return reviewer_prompt(context.goal, step_input.get("developer_output", {}))
        raise RuntimeError(f"Unknown agent id: {agent_id}")

    def _action_role_instruction(self, agent_id: str) -> str:
        if agent_id == "planner":
            return (
                "动作协议：你是规划阶段，不要输出 type=patch 或 type=command 的 artifacts。"
                "请只输出任务拆解、验收标准、风险和下一步审批建议。"
            )
        if agent_id == "implementer":
            return (
                "动作协议：如果用户目标需要改文件，请在 artifacts 中输出 type=patch。"
                "patch payload.files 必须是数组，每项包含 path 和 content，path 必须是 project_path 内相对路径。"
                "如果需要验证，请额外输出 type=command，command 必须使用数组形式，例如 [\"npm\",\"run\",\"typecheck\"]、"
                "[\"npm\",\"test\"]、[\"python\",\"-m\",\"pytest\"] 或 [\"python\",\"-m\",\"py_compile\"]。"
                "不要输出 Markdown，严格输出 JSON。"
            )
        if agent_id == "reviewer":
            return (
                "动作协议：你可以在 artifacts 中输出 type=command 作为审查或测试建议，"
                "但不要输出 type=patch。不要建议非白名单命令。严格输出 JSON。"
            )
        return "动作协议：仅当当前 Agent 职责明确需要时才输出 patch 或 command action；否则输出普通 artifacts。"
