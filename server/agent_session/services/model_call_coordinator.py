from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from agent_session.goal_planner import (
    _planner_system_prompt,
    _planner_user_prompt,
    _repair_user_prompt,
)

if TYPE_CHECKING:
    from agent_session.runtime_policy import AgentRuntimePolicy
    from agent_session.service import AgentSessionService


# Goal planning is an optional preflight enhancement.  It must never leave a
# prompt-start request waiting indefinitely for a provider or local model.
GOAL_PLANNER_CALL_TIMEOUT_SECONDS = 20.0


class ModelCallCoordinatorService:
    def __init__(self, service: AgentSessionService) -> None:
        self.service = service

    def _sync_async_service_model_call(self) -> None:
        self.service.async_subagent_service.set_model_call(self.service.model_call)
        self.service.deepagents_runner.model_call = self.service.model_call

    async def _complete_planner_messages(
        self,
        messages: list[dict[str, str]],
        *,
        policy: AgentRuntimePolicy,
        session: dict[str, Any] | None,
    ) -> str:
        model_call = self.service.model_call
        if model_call is not None:
            return str(await model_call(messages))

        if not policy.provider or not policy.model:
            raise RuntimeError("Goal planner requires a configured model_call hook or provider/model")

        from langchain_core.messages import HumanMessage, SystemMessage

        from agent_session.execution_context import RuntimeExecutionContext
        from agent_session.model_adapter import ProviderAdapterError, get_chat_model

        session_payload = dict(session or {})
        context = RuntimeExecutionContext(
            session_id=str(session_payload.get("id") or ""),
            goal=str(session_payload.get("current_goal") or session_payload.get("goal") or ""),
            project_path=session_payload.get("project_path"),
            provider=str(policy.provider or ""),
            model=policy.model,
            metadata=dict(session_payload.get("metadata") or {}),
        )
        try:
            model = get_chat_model(context)
        except ProviderAdapterError as exc:
            raise RuntimeError(str(exc)) from exc

        converted: list[Any] = []
        for message in messages:
            role = str(message.get("role") or "user")
            content = str(message.get("content") or "")
            if role == "system":
                converted.append(SystemMessage(content=content))
            else:
                converted.append(HumanMessage(content=content))
        result = await model.ainvoke(converted)
        content = result.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content)
        return str(content)

    async def invoke_bounded_goal_planner_call(
        self,
        *,
        user_goal: str,
        policy: AgentRuntimePolicy,
        session: dict[str, Any] | None = None,
        repair: bool = False,
        prior_error: str | None = None,
        invalid_payload: str | None = None,
    ) -> str:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": _planner_system_prompt()},
            {"role": "user", "content": _planner_user_prompt(user_goal=user_goal, policy=policy)},
        ]
        if repair:
            messages.append(
                {
                    "role": "user",
                    "content": _repair_user_prompt(
                        prior_error=str(prior_error or "invalid goal plan"),
                        invalid_payload=str(invalid_payload or ""),
                    ),
                }
            )
        return await asyncio.wait_for(
            self._complete_planner_messages(messages, policy=policy, session=session),
            timeout=GOAL_PLANNER_CALL_TIMEOUT_SECONDS,
        )
