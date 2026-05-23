from __future__ import annotations

from .intent import ChatAgentIntentClassifier
from .models import ChatAgentIntentRequest, ChatAgentIntentResponse


class ChatAgentService:
    def __init__(self, classifier: ChatAgentIntentClassifier | None = None):
        self.classifier = classifier or ChatAgentIntentClassifier()

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
        return ChatAgentIntentResponse(**decision)
