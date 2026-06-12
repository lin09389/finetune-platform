from __future__ import annotations

from agent_session.agent_registry import AgentRegistry

from .intent import ChatAgentIntentClassifier
from .models import ChatAgentIntentRequest, ChatAgentIntentResponse


class ChatAgentService:
    def __init__(self, classifier: ChatAgentIntentClassifier | None = None, agent_registry: AgentRegistry | None = None):
        self.classifier = classifier or ChatAgentIntentClassifier()
        self.agent_registry = agent_registry or AgentRegistry()

    async def classify_intent(self, request: ChatAgentIntentRequest) -> ChatAgentIntentResponse:
        content = request.content
        hints: list[str] = []
        if request.active_context:
            hints.append(f"当前编辑文件：{request.active_context.get('file_path') or 'unknown'}")
        if request.explicit_context:
            labels = [
                str(item.get("label") or item.get("path") or "context")
                for item in request.explicit_context
                if isinstance(item, dict)
            ]
            if labels:
                hints.append("@上下文：" + "、".join(labels[:8]))
        if hints:
            content = f"{content}\n\n上下文信号：{'；'.join(hints)}"
        decision = await self.classifier.route(
            content,
            routing_mode=request.routing_mode,
            provider=request.provider,
            model=request.model,
            agent_id=request.agent_id,
        )
        decision = self._normalize_agent_decision(decision)
        return ChatAgentIntentResponse(**decision)

    def _normalize_agent_decision(self, decision: dict) -> dict:
        if decision.get("mode") != "agent":
            decision["suggested_agent_id"] = None
            return decision
        requested = str(decision.get("suggested_agent_id") or "build").strip() or "build"
        agent = self.agent_registry.get(requested)
        if agent and agent.can_start_directly:
            decision["suggested_agent_id"] = agent.id
            return decision
        fallback = self.agent_registry.get("build")
        if fallback and fallback.can_start_directly:
            decision["suggested_agent_id"] = fallback.id
            decision["reason"] = f"{decision.get('reason') or 'Agent intent detected'}；请求的 agent '{requested}' 不能直接启动，已回退到 build。"
            return decision
        decision["mode"] = "chat"
        decision["suggested_agent_id"] = None
        decision["confidence"] = min(float(decision.get("confidence") or 0.5), 0.5)
        decision["reason"] = f"{decision.get('reason') or 'Agent intent detected'}；没有可直接启动的 agent，已回退到普通对话。"
        return decision
