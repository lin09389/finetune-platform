"""
项目上下文理解模�?
功能�?- 项目扫描：检测技术栈、分析结构、解析依�?- 代码索引：提取符号、向量化存储
- 上下文检索：语义搜索相关文件
- 对话上下文管理：窗口动态调整、消息压�?- 会话存储：持久化会话管理
"""
from .project_scanner import ProjectScanner
from .models import ProjectInfo, FileInfo, SymbolInfo
from .manager import (
    ContextManager,
    ChatMessage,
    MessageRole,
    MessagePriority,
    ContextWindow,
    get_context_manager,
    remove_context_manager,
    list_context_managers
)
from .compressor import (
    DialogCompressor,
    CompressionResult,
    get_dialog_compressor
)
from .session_store import (
    SessionStore,
    SessionStatus,
    SessionMetadata,
    SessionMessage,
    ChatSession,
    get_session_store,
    init_session_store
)

__all__ = [
    "ProjectScanner",
    "ProjectInfo",
    "FileInfo",
    "SymbolInfo",
    "ContextManager",
    "ChatMessage",
    "MessageRole",
    "MessagePriority",
    "ContextWindow",
    "get_context_manager",
    "remove_context_manager",
    "list_context_managers",
    "DialogCompressor",
    "CompressionResult",
    "get_dialog_compressor",
    "SessionStore",
    "SessionStatus",
    "SessionMetadata",
    "SessionMessage",
    "ChatSession",
    "get_session_store",
    "init_session_store",
]
