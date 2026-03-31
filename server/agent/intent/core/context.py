"""
意图检测核心组件 - 统一上下文管理器

整合所有上下文管理逻辑，消除重复代码
"""
import threading
from datetime import datetime
from typing import Any

from ..models import ConversationContext


class ContextManager:
    """统一上下文管理器"""

    MAX_SESSIONS = 100
    MAX_HISTORY_LENGTH = 20
    MAX_RECENT_INTENTS = 10
    SESSION_TIMEOUT_SECONDS = 3600

    def __init__(self):
        self._sessions: dict[str, ConversationContext] = {}
        self._lock = threading.Lock()

    def get_or_create(self, session_id: str) -> ConversationContext:
        with self._lock:
            if session_id not in self._sessions:
                self._cleanup_old_sessions()
                self._sessions[session_id] = ConversationContext(session_id=session_id)
            return self._sessions[session_id]

    def get(self, session_id: str) -> ConversationContext | None:
        with self._lock:
            return self._sessions.get(session_id)

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        intent: str | None = None,
        entities: dict[str, Any] | None = None
    ):
        context = self.get_or_create(session_id)
        context.add_message(role, content, intent, entities)

    def resolve_reference(
        self,
        session_id: str,
        reference: str
    ) -> str | None:
        context = self.get(session_id)
        if context:
            return context.resolve_reference(reference)
        return None

    def get_recent_intents(
        self,
        session_id: str,
        n: int = 5
    ) -> list[str]:
        context = self.get(session_id)
        if context:
            return context.get_recent_intents(n)
        return []

    def get_mentioned_entities(
        self,
        session_id: str
    ) -> dict[str, list[str]]:
        context = self.get(session_id)
        if context:
            return context.mentioned_entities
        return {}

    def set_current_task(
        self,
        session_id: str,
        task: str
    ):
        context = self.get_or_create(session_id)
        context.current_task = task
        context.last_updated = datetime.now()

    def get_current_task(
        self,
        session_id: str
    ) -> str | None:
        context = self.get(session_id)
        if context:
            return context.current_task
        return None

    def set_expecting_action(
        self,
        session_id: str,
        action: str
    ):
        context = self.get_or_create(session_id)
        context.expecting_action = action
        context.last_updated = datetime.now()

    def get_expecting_action(
        self,
        session_id: str
    ) -> str | None:
        context = self.get(session_id)
        if context:
            return context.expecting_action
        return None

    def clear_expecting_action(
        self,
        session_id: str
    ):
        context = self.get(session_id)
        if context:
            context.expecting_action = None
            context.last_updated = datetime.now()

    def update_last_intent(
        self,
        session_id: str,
        intent_type: str,
        params: dict[str, Any]
    ):
        context = self.get_or_create(session_id)
        context.last_intent = intent_type
        context.last_params = params
        context.last_updated = datetime.now()

    def set_generated_content(
        self,
        session_id: str,
        content: str,
        content_type: str = "text"
    ):
        context = self.get_or_create(session_id)
        context.set_generated_content(content, content_type)

    def get_generated_content(
        self,
        session_id: str
    ) -> tuple[str | None, str | None]:
        context = self.get(session_id)
        if context:
            return context.last_generated_content, context.last_generated_type
        return None, None

    def delete_session(self, session_id: str):
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]

    def clear_all(self):
        with self._lock:
            self._sessions.clear()

    def get_active_sessions(self) -> list[str]:
        with self._lock:
            return list(self._sessions.keys())

    def _cleanup_old_sessions(self):
        if len(self._sessions) >= self.MAX_SESSIONS:
            now = datetime.now()
            sorted_sessions = sorted(
                self._sessions.items(),
                key=lambda x: x[1].last_updated
            )
            for session_id, context in sorted_sessions[:len(self._sessions) // 2]:
                age_seconds = (now - context.last_updated).total_seconds()
                if age_seconds > self.SESSION_TIMEOUT_SECONDS:
                    del self._sessions[session_id]

    def get_context_summary(
        self,
        session_id: str
    ) -> dict[str, Any]:
        context = self.get(session_id)
        if context:
            return context.to_dict()
        return {
            "session_id": session_id,
            "history_count": 0,
            "recent_intents": [],
            "mentioned_entities": {},
            "last_intent": None,
            "last_params": {},
            "current_task": None,
            "expecting_action": None
        }


context_manager = ContextManager()
