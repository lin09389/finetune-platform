"""
上下文感知模块
结合对话历史和会话状态进行意图检测
"""
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    """对话上下文"""
    session_id: str
    recent_messages: List[Dict[str, Any]] = field(default_factory=list)
    recent_intents: List[str] = field(default_factory=list)
    mentioned_files: List[str] = field(default_factory=list)
    mentioned_apps: List[str] = field(default_factory=list)
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    current_task: Optional[str] = None
    expecting_action: Optional[str] = None


class ContextManager:
    """上下文管理器"""
    
    def __init__(self, max_history: int = 10):
        self.max_history = max_history
        self.sessions: Dict[str, ConversationContext] = {}
    
    def get_or_create_session(self, session_id: str) -> ConversationContext:
        """获取或创建会话上下文"""
        if session_id not in self.sessions:
            self.sessions[session_id] = ConversationContext(session_id=session_id)
        return self.sessions[session_id]
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        intent: Optional[str] = None,
        entities: Optional[Dict[str, Any]] = None
    ):
        """添加消息到上下文"""
        ctx = self.get_or_create_session(session_id)
        
        ctx.recent_messages.append({
            "role": role,
            "content": content,
            "intent": intent,
            "entities": entities
        })
        
        if len(ctx.recent_messages) > self.max_history:
            ctx.recent_messages = ctx.recent_messages[-self.max_history:]
        
        if intent:
            ctx.recent_intents.append(intent)
            if len(ctx.recent_intents) > self.max_history:
                ctx.recent_intents = ctx.recent_intents[-self.max_history:]
        
        if entities:
            if "files" in entities:
                ctx.mentioned_files.extend(entities["files"])
            if "apps" in entities:
                ctx.mentioned_apps.extend(entities["apps"])
    
    def get_recent_intents(self, session_id: str, n: int = 5) -> List[str]:
        """获取最近的意图"""
        ctx = self.get_or_create_session(session_id)
        return ctx.recent_intents[-n:]
    
    def get_last_intent(self, session_id: str) -> Optional[str]:
        """获取最后一个意图"""
        ctx = self.get_or_create_session(session_id)
        return ctx.recent_intents[-1] if ctx.recent_intents else None
    
    def resolve_reference(self, session_id: str, reference: str) -> Optional[str]:
        """解析引用"""
        ctx = self.get_or_create_session(session_id)
        
        reference_map = {
            "它": "file",
            "这个": "file",
            "那个": "file",
            "刚才": "last_action"
        }
        
        ref_type = reference_map.get(reference)
        if ref_type == "file" and ctx.mentioned_files:
            return ctx.mentioned_files[-1]
        elif ref_type == "last_action" and ctx.recent_intents:
            return ctx.recent_intents[-1]
        
        return None
    
    def clear_session(self, session_id: str):
        """清除会话"""
        if session_id in self.sessions:
            del self.sessions[session_id]


class SessionStateTracker:
    """会话状态追踪器"""
    
    def __init__(self):
        self.states: Dict[str, Dict[str, Any]] = defaultdict(dict)
    
    def set_state(self, session_id: str, key: str, value: Any):
        """设置状态"""
        self.states[session_id][key] = value
    
    def get_state(self, session_id: str, key: str, default: Any = None) -> Any:
        """获取状态"""
        return self.states[session_id].get(key, default)
    
    def get_all_states(self, session_id: str) -> Dict[str, Any]:
        """获取所有状态"""
        return dict(self.states[session_id])
    
    def clear_state(self, session_id: str, key: Optional[str] = None):
        """清除状态"""
        if key:
            self.states[session_id].pop(key, None)
        else:
            self.states[session_id].clear()


class ContextAwareDetector:
    """上下文感知检测器"""
    
    INTENT_CHAINS = {
        "file_create": ["file_write"],
        "file_read": ["file_write", "file_delete"],
        "file_list": ["file_read", "file_create"],
        "app_open": ["url_open"],
    }
    
    def __init__(self, context_manager: Optional[ContextManager] = None):
        self.context_manager = context_manager or ContextManager()
    
    def detect_with_context(
        self,
        message: str,
        session_id: str,
        base_intent: Optional[str] = None,
        base_params: Optional[Dict[str, Any]] = None
    ) -> Tuple[Optional[str], Dict[str, Any], float]:
        """结合上下文检测意图"""
        params = base_params or {}
        confidence_boost = 0.0
        
        ctx = self.context_manager.get_or_create_session(session_id)
        
        if "它" in message or "这个" in message or "那个" in message:
            resolved = self.context_manager.resolve_reference(session_id, "它")
            if resolved and "file_path" not in params:
                params["file_path"] = resolved
                confidence_boost += 0.15
        
        if "继续" in message or "重复" in message:
            last_intent = self.context_manager.get_last_intent(session_id)
            if last_intent:
                base_intent = last_intent
                confidence_boost += 0.2
        
        if base_intent and ctx.expecting_action:
            if base_intent == ctx.expecting_action:
                confidence_boost += 0.25
        
        predicted_next = self._predict_next_intent(ctx)
        if predicted_next and base_intent == predicted_next:
            confidence_boost += 0.1
        
        return base_intent, params, min(confidence_boost, 0.3)
    
    def _predict_next_intent(self, ctx: ConversationContext) -> Optional[str]:
        """预测下一个意图"""
        if not ctx.recent_intents:
            return None
        
        last_intent = ctx.recent_intents[-1]
        return self.INTENT_CHAINS.get(last_intent, [None])[0]
    
    def update_after_action(
        self,
        session_id: str,
        intent: str,
        params: Dict[str, Any],
        success: bool
    ):
        """动作执行后更新上下文"""
        self.context_manager.add_message(
            session_id=session_id,
            role="assistant",
            content="",
            intent=intent,
            entities=params
        )


def create_context_manager(max_history: int = 10) -> ContextManager:
    """创建上下文管理器"""
    return ContextManager(max_history=max_history)


def create_context_aware_detector(context_manager: Optional[ContextManager] = None) -> ContextAwareDetector:
    """创建上下文感知检测器"""
    return ContextAwareDetector(context_manager=context_manager)


def create_session_state_tracker() -> SessionStateTracker:
    """创建会话状态追踪器"""
    return SessionStateTracker()
