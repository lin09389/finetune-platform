# -*- coding: utf-8 -*-
"""
对话模块 - 统一会话管理、历史记录、上下文管理
整合原有 chat、conversation、dialog 功能
"""
from .routes import router
from .session import SessionManager, get_session_manager, Session, Message
from .context import ContextManager, get_context_manager, ConversationContext

__all__ = [
    "router",
    "SessionManager",
    "get_session_manager",
    "Session",
    "Message",
    "ContextManager",
    "get_context_manager",
    "ConversationContext",
]
