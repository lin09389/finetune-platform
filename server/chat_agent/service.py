from __future__ import annotations

from .intent import ChatAgentIntentClassifier
from .models import ChatAgentIntentRequest, ChatAgentIntentResponse


class ChatAgentService:
    def __init__(self, classifier: ChatAgentIntentClassifier | None = None):
        self.classifier = classifier or ChatAgentIntentClassifier()

    async def classify_intent(self, request: ChatAgentIntentRequest) -> ChatAgentIntentResponse:
        decision = await self.classifier.route(
            request.content,
            routing_mode=request.routing_mode,
            provider=request.provider,
            model=request.model,
            agent_id=request.agent_id,
        )
        return ChatAgentIntentResponse(**decision)
