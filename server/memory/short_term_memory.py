"""
短期记忆管理器
管理当前会话的对话上下文和活跃实体
"""
import logging
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ConversationMessage:
    """对话消息"""
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    entities: list[str] = field(default_factory=list)
    importance: float = 0.5
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            'role': self.role,
            'content': self.content,
            'timestamp': self.timestamp.isoformat(),
            'entities': self.entities,
            'importance': self.importance,
            'summary': self.summary
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ConversationMessage':
        return cls(
            role=data['role'],
            content=data['content'],
            timestamp=datetime.fromisoformat(data['timestamp']) if isinstance(data.get('timestamp'), str) else data.get('timestamp', datetime.now()),
            entities=data.get('entities', []),
            importance=data.get('importance', 0.5),
            summary=data.get('summary', '')
        )


class ShortTermMemory:
    """短期记忆管理器"""

    IMPORTANCE_KEYWORDS = {
        'high': ['重要', '记住', '别忘了', '关键', '必须', 'important', 'remember', 'critical', 'must'],
        'medium': ['注意', '提醒', '记得', 'note', 'notice', 'remind'],
        'low': ['顺便', '对了', 'by the way']
    }

    TOPIC_KEYWORDS = {
        '技术': ['代码', '开发', '编程', '项目', '功能', 'bug', 'API', '框架'],
        '工作': ['任务', '会议', '报告', '计划', '进度', '团队'],
        '学习': ['学习', '教程', '文档', '理解', '知识', '概念'],
        '生活': ['生活', '家庭', '朋友', '爱好', '习惯']
    }

    def __init__(
        self,
        max_turns: int = 20,
        decay_rate: float = 0.9,
        max_context_tokens: int = 4000
    ):
        self.max_turns = max_turns
        self.decay_rate = decay_rate
        self.max_context_tokens = max_context_tokens

        self.conversation_buffer: deque = deque(maxlen=max_turns)
        self.session_start: datetime = datetime.now()
        self.last_activity: datetime = datetime.now()

        self.active_entities: dict[str, float] = {}
        self.active_topics: dict[str, float] = {}
        self.key_facts: list[dict[str, Any]] = []

        self._message_count = 0
        self._total_importance = 0.0

        logger.info(f"短期记忆初始化: max_turns={max_turns}, decay_rate={decay_rate}")

    def add_message(
        self,
        role: str,
        content: str,
        entities: list[str] = None,
        force_importance: float = None
    ) -> ConversationMessage:
        """
        添加消息到短期记忆
        
        Args:
            role: 角色 (user/assistant)
            content: 消息内容
            entities: 相关实体ID列表
            force_importance: 强制重要性分数
            
        Returns:
            添加的消息对象
        """
        importance = force_importance if force_importance is not None else self._calculate_importance(content)

        message = ConversationMessage(
            role=role,
            content=content,
            timestamp=datetime.now(),
            entities=entities or [],
            importance=importance
        )

        self.conversation_buffer.append(message)
        self.last_activity = datetime.now()

        self._message_count += 1
        self._total_importance += importance

        for entity_id in entities or []:
            self._update_entity_attention(entity_id)

        self._update_topics(content)

        if importance >= 0.8:
            self._add_key_fact(content, entities)

        logger.debug(f"添加消息: role={role}, importance={importance:.2f}, entities={len(entities or [])}")

        return message

    def get_context(
        self,
        max_tokens: int = None,
        include_importance: bool = True,
        include_timestamp: bool = False
    ) -> str:
        """
        获取上下文（带衰减和重要性加权）
        
        Args:
            max_tokens: 最大token数
            include_importance: 是否包含重要性标记
            include_timestamp: 是否包含时间戳
            
        Returns:
            格式化的上下文字符串
        """
        max_tokens = max_tokens or self.max_context_tokens
        context_parts = []
        total_tokens = 0

        sorted_messages = sorted(
            self.conversation_buffer,
            key=lambda m: m.importance,
            reverse=True
        )

        included_ids = set()

        for msg in sorted_messages:
            if msg.importance >= 0.7:
                formatted = self._format_message(msg, include_importance, include_timestamp)
                msg_tokens = len(formatted.split())

                if total_tokens + msg_tokens <= max_tokens * 0.5:
                    context_parts.append((msg.timestamp, formatted))
                    included_ids.add(id(msg))
                    total_tokens += msg_tokens

        for i, msg in enumerate(reversed(self.conversation_buffer)):
            if id(msg) in included_ids:
                continue

            decay = self.decay_rate ** i
            if decay < 0.3:
                continue

            formatted = self._format_message(msg, include_importance, include_timestamp, decay)
            msg_tokens = len(formatted.split())

            if total_tokens + msg_tokens > max_tokens:
                break

            context_parts.append((msg.timestamp, formatted))
            total_tokens += msg_tokens

        context_parts.sort(key=lambda x: x[0])

        return "\n".join(part[1] for part in context_parts)

    def get_recent_messages(self, n: int = 5) -> list[ConversationMessage]:
        """获取最近N条消息"""
        return list(self.conversation_buffer)[-n:]

    def get_active_entities(self, threshold: float = 0.3) -> list[str]:
        """获取活跃实体"""
        self._apply_decay()

        sorted_entities = sorted(
            self.active_entities.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return [entity_id for entity_id, weight in sorted_entities if weight > threshold]

    def get_active_topics(self, threshold: float = 0.2) -> list[str]:
        """获取活跃话题"""
        self._apply_topic_decay()

        sorted_topics = sorted(
            self.active_topics.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return [topic for topic, weight in sorted_topics if weight > threshold]

    def get_key_facts(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取关键事实"""
        return self.key_facts[-limit:]

    def summarize(self) -> dict[str, Any]:
        """总结短期记忆状态"""
        return {
            'session_duration': (datetime.now() - self.session_start).total_seconds(),
            'message_count': len(self.conversation_buffer),
            'active_entities': self.get_active_entities(),
            'active_topics': self.get_active_topics(),
            'key_facts_count': len(self.key_facts),
            'average_importance': self._total_importance / max(1, self._message_count),
            'last_activity': self.last_activity.isoformat()
        }

    def get_conversation_summary(self) -> str:
        """生成对话摘要"""
        if not self.conversation_buffer:
            return "暂无对话记录"

        user_messages = [m for m in self.conversation_buffer if m.role == 'user']
        assistant_messages = [m for m in self.conversation_buffer if m.role == 'assistant']

        topics = self.get_active_topics()
        entities = self.get_active_entities()

        summary_parts = [
            f"对话轮数: {len(user_messages)} 轮",
            f"活跃话题: {', '.join(topics) if topics else '无'}",
            f"关键实体: {len(entities)} 个",
            f"重要事实: {len(self.key_facts)} 条"
        ]

        return "\n".join(summary_parts)

    def find_relevant_messages(self, query: str, top_k: int = 5) -> list[ConversationMessage]:
        """查找与查询相关的消息"""
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored_messages = []

        for msg in self.conversation_buffer:
            content_lower = msg.content.lower()
            content_words = set(content_lower.split())

            common_words = query_words & content_words
            word_score = len(common_words) / max(1, len(query_words))

            importance_score = msg.importance * 0.3

            recency_score = 0.2 * (self.decay_rate ** list(self.conversation_buffer).index(msg))

            total_score = word_score + importance_score + recency_score

            if total_score > 0:
                scored_messages.append((total_score, msg))

        scored_messages.sort(key=lambda x: x[0], reverse=True)

        return [msg for score, msg in scored_messages[:top_k]]

    def clear(self):
        """清空短期记忆"""
        self.conversation_buffer.clear()
        self.session_start = datetime.now()
        self.last_activity = datetime.now()
        self.active_entities.clear()
        self.active_topics.clear()
        self.key_facts.clear()
        self._message_count = 0
        self._total_importance = 0.0
        logger.info("短期记忆已清空")

    def export_state(self) -> dict[str, Any]:
        """导出状态"""
        return {
            'messages': [m.to_dict() for m in self.conversation_buffer],
            'active_entities': self.active_entities,
            'active_topics': self.active_topics,
            'key_facts': self.key_facts,
            'session_start': self.session_start.isoformat(),
            'stats': {
                'message_count': self._message_count,
                'total_importance': self._total_importance
            }
        }

    def import_state(self, state: dict[str, Any]):
        """导入状态"""
        self.clear()

        for msg_data in state.get('messages', []):
            msg = ConversationMessage.from_dict(msg_data)
            self.conversation_buffer.append(msg)

        self.active_entities = state.get('active_entities', {})
        self.active_topics = state.get('active_topics', {})
        self.key_facts = state.get('key_facts', [])

        if 'session_start' in state:
            self.session_start = datetime.fromisoformat(state['session_start'])

        stats = state.get('stats', {})
        self._message_count = stats.get('message_count', len(self.conversation_buffer))
        self._total_importance = stats.get('total_importance', 0.0)

        logger.info(f"导入短期记忆状态: {len(self.conversation_buffer)} 条消息")

    def _calculate_importance(self, content: str) -> float:
        """计算消息重要性"""
        content_lower = content.lower()

        for keyword in self.IMPORTANCE_KEYWORDS['high']:
            if keyword in content_lower:
                return 0.9

        for keyword in self.IMPORTANCE_KEYWORDS['medium']:
            if keyword in content_lower:
                return 0.7

        for keyword in self.IMPORTANCE_KEYWORDS['low']:
            if keyword in content_lower:
                return 0.4

        length_factor = min(0.2, len(content) / 500)

        question_factor = 0.1 if '?' in content or '？' in content else 0

        return 0.5 + length_factor + question_factor

    def _update_entity_attention(self, entity_id: str):
        """更新实体注意力权重"""
        current = self.active_entities.get(entity_id, 0)
        self.active_entities[entity_id] = min(1.0, current + 0.3)

    def _update_topics(self, content: str):
        """更新话题权重"""
        for topic, keywords in self.TOPIC_KEYWORDS.items():
            for keyword in keywords:
                if keyword in content:
                    current = self.active_topics.get(topic, 0)
                    self.active_topics[topic] = min(1.0, current + 0.2)
                    break

    def _apply_decay(self):
        """应用注意力衰减"""
        for entity_id in self.active_entities:
            self.active_entities[entity_id] *= self.decay_rate

        self.active_entities = {
            k: v for k, v in self.active_entities.items()
            if v > 0.1
        }

    def _apply_topic_decay(self):
        """应用话题衰减"""
        for topic in self.active_topics:
            self.active_topics[topic] *= self.decay_rate

        self.active_topics = {
            k: v for k, v in self.active_topics.items()
            if v > 0.1
        }

    def _add_key_fact(self, content: str, entities: list[str] = None):
        """添加关键事实"""
        fact = {
            'content': content[:200],
            'entities': entities or [],
            'timestamp': datetime.now().isoformat()
        }

        self.key_facts.append(fact)

        if len(self.key_facts) > 20:
            self.key_facts = self.key_facts[-20:]

    def _format_message(
        self,
        msg: ConversationMessage,
        include_importance: bool,
        include_timestamp: bool,
        decay: float = 1.0
    ) -> str:
        """格式化消息"""
        parts = []

        if include_timestamp:
            parts.append(f"[{msg.timestamp.strftime('%H:%M')}]")

        role_label = "用户" if msg.role == "user" else "助手"
        parts.append(f"{role_label}:")

        content = msg.content
        if decay < 1.0:
            content = self._summarize_content(content, decay)

        parts.append(content)

        if include_importance and msg.importance >= 0.7:
            parts.append("[重要]")

        return " ".join(parts)

    def _summarize_content(self, content: str, decay: float) -> str:
        """根据衰减程度简化内容"""
        if decay > 0.7:
            return content

        sentences = re.split(r'[。！？!?]', content)
        if len(sentences) <= 1:
            return content

        if decay > 0.5:
            return sentences[0] + "..."

        words = content.split()
        if len(words) <= 10:
            return content

        return " ".join(words[:10]) + "..."


class ShortTermMemoryManager:
    """短期记忆管理器（支持多会话）"""

    def __init__(self, max_sessions: int = 10):
        self.max_sessions = max_sessions
        self.sessions: dict[str, ShortTermMemory] = {}
        self._default_session_id = "default"

    def get_session(self, session_id: str = None) -> ShortTermMemory:
        """获取或创建会话"""
        session_id = session_id or self._default_session_id

        if session_id not in self.sessions:
            if len(self.sessions) >= self.max_sessions:
                self._evict_oldest_session()

            self.sessions[session_id] = ShortTermMemory()
            logger.info(f"创建新会话: {session_id}")

        return self.sessions[session_id]

    def add_message(
        self,
        role: str,
        content: str,
        session_id: str = None,
        entities: list[str] = None
    ) -> ConversationMessage:
        """添加消息到指定会话"""
        session = self.get_session(session_id)
        return session.add_message(role, content, entities)

    def get_context(self, session_id: str = None, max_tokens: int = None) -> str:
        """获取会话上下文"""
        session = self.get_session(session_id)
        return session.get_context(max_tokens)

    def clear_session(self, session_id: str = None):
        """清空指定会话"""
        session_id = session_id or self._default_session_id
        if session_id in self.sessions:
            self.sessions[session_id].clear()

    def remove_session(self, session_id: str):
        """删除会话"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"删除会话: {session_id}")

    def get_all_sessions(self) -> list[str]:
        """获取所有会话ID"""
        return list(self.sessions.keys())

    def _evict_oldest_session(self):
        """淘汰最旧的会话"""
        if not self.sessions:
            return

        oldest_id = min(
            self.sessions.keys(),
            key=lambda sid: self.sessions[sid].last_activity
        )

        self.remove_session(oldest_id)
        logger.info(f"淘汰最旧会话: {oldest_id}")


_stm_manager: ShortTermMemoryManager | None = None


def get_short_term_memory(session_id: str = None) -> ShortTermMemory:
    """获取短期记忆实例"""
    global _stm_manager
    if _stm_manager is None:
        _stm_manager = ShortTermMemoryManager()
    return _stm_manager.get_session(session_id)


def get_stm_manager() -> ShortTermMemoryManager:
    """获取短期记忆管理器"""
    global _stm_manager
    if _stm_manager is None:
        _stm_manager = ShortTermMemoryManager()
    return _stm_manager
