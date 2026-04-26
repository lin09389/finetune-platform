"""Generic runtime runner for provider resolution, prompt building and parsing."""

from __future__ import annotations

import json
from typing import Any

from ai.gateway import AnthropicMessagesProvider, OpenAICompatibleProvider, get_provider
from digital_team.models import AgentOutput
from digital_team.prompts import ceo_prompt, developer_prompt, reviewer_prompt
from security.encryption import secure_storage

from .definitions import RuntimeExecutionContext


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
    async def execute(
        self,
        agent_id: str,
        context: RuntimeExecutionContext,
        step_input: dict[str, Any] | None = None,
    ) -> AgentOutput:
        key_data = secure_storage.get(f"cloud_{context.provider}_key") or {}
        api_key = key_data.get("api_key", "")
        if not api_key:
            raise RuntimeError(f"未配置 {context.provider} 的 API Key")

        provider = resolve_saved_provider(context.provider, key_data)
        if provider is None:
            raise RuntimeError(f"不支持的云端服务商: {context.provider}")

        messages = self._build_messages(agent_id, context, step_input or {})
        selected_model = context.model or key_data.get("default_model") or provider.get_default_model()
        response = await provider.chat(
            messages=messages,
            model=selected_model,
            api_key=api_key,
            temperature=0.3,
            max_tokens=3000,
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
                    "artifacts": "array",
                    "next_action": "string",
                    "requires_approval": "boolean",
                },
            }
            return [
                {"role": "system", "content": system_prompt},
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
