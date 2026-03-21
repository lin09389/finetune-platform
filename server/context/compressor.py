"""
对话压缩器
功能：
- 对话摘要生成
- 基于重要性的消息压缩
- 语义保留的对话精简
- 多种压缩策略
"""
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
import logging
import re

from .manager import ChatMessage, MessageRole, MessagePriority

logger = logging.getLogger(__name__)


@dataclass
class CompressionResult:
    """压缩结果"""
    original_count: int
    compressed_count: int
    original_tokens: int
    compressed_tokens: int
    summary: Optional[str] = None
    removed_messages: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.removed_messages is None:
            self.removed_messages = []
    
    @property
    def compression_ratio(self) -> float:
        if self.original_tokens == 0:
            return 0.0
        return 1.0 - (self.compressed_tokens / self.original_tokens)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_count": self.original_count,
            "compressed_count": self.compressed_count,
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
            "compression_ratio": round(self.compression_ratio, 2),
            "summary": self.summary,
            "removed_count": len(self.removed_messages)
        }


class DialogCompressor:
    """对话压缩器"""
    
    def __init__(
        self,
        min_messages_to_compress: int = 6,
        keep_recent_count: int = 3,
        summary_max_length: int = 500
    ):
        self.min_messages_to_compress = min_messages_to_compress
        self.keep_recent_count = keep_recent_count
        self.summary_max_length = summary_max_length
        
        self._summary_templates = {
            "conversation": "之前的对话中，用户{user_actions}。助手{assistant_actions}。",
            "qa": "用户询问了关于{topics}的问题，助手提供了{answer_types}的回答。",
            "coding": "用户请求了{task_types}相关的帮助，助手提供了{solution_types}的解决方案。"
        }
        
        logger.info("对话压缩器已初始化")
    
    def compress(
        self,
        messages: List[ChatMessage],
        strategy: str = "summary",
        target_ratio: float = 0.5
    ) -> Tuple[List[ChatMessage], CompressionResult]:
        if len(messages) < self.min_messages_to_compress:
            return messages, CompressionResult(
                original_count=len(messages),
                compressed_count=len(messages),
                original_tokens=sum(m.token_count for m in messages),
                compressed_tokens=sum(m.token_count for m in messages)
            )
        
        original_tokens = sum(m.token_count for m in messages)
        
        if strategy == "summary":
            compressed, result = self._compress_with_summary(messages, target_ratio)
        elif strategy == "sliding_window":
            compressed, result = self._compress_sliding_window(messages, target_ratio)
        elif strategy == "semantic":
            compressed, result = self._compress_semantic(messages, target_ratio)
        else:
            compressed, result = self._compress_importance(messages, target_ratio)
        
        return compressed, result
    
    def _compress_with_summary(
        self,
        messages: List[ChatMessage],
        target_ratio: float
    ) -> Tuple[List[ChatMessage], CompressionResult]:
        original_tokens = sum(m.token_count for m in messages)
        
        recent_messages = messages[-self.keep_recent_count:]
        old_messages = messages[:-self.keep_recent_count]
        
        if not old_messages:
            return messages, CompressionResult(
                original_count=len(messages),
                compressed_count=len(messages),
                original_tokens=original_tokens,
                compressed_tokens=original_tokens
            )
        
        summary = self._generate_summary(old_messages)
        
        summary_message = ChatMessage(
            id="summary_" + datetime.now().strftime("%H%M%S"),
            role=MessageRole.SYSTEM,
            content=f"[对话摘要] {summary}",
            priority=MessagePriority.HIGH,
            token_count=self._estimate_tokens(summary) + 10,
            importance=0.9,
            metadata={"type": "summary", "original_count": len(old_messages)}
        )
        
        compressed = [summary_message] + recent_messages
        compressed_tokens = sum(m.token_count for m in compressed)
        
        result = CompressionResult(
            original_count=len(messages),
            compressed_count=len(compressed),
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            summary=summary,
            removed_messages=[m.to_dict() for m in old_messages]
        )
        
        logger.info(f"摘要压缩完成: {len(messages)} -> {len(compressed)} 条消息")
        
        return compressed, result
    
    def _compress_sliding_window(
        self,
        messages: List[ChatMessage],
        target_ratio: float
    ) -> Tuple[List[ChatMessage], CompressionResult]:
        original_tokens = sum(m.token_count for m in messages)
        target_tokens = int(original_tokens * target_ratio)
        
        if len(messages) <= 4:
            return messages, CompressionResult(
                original_count=len(messages),
                compressed_count=len(messages),
                original_tokens=original_tokens,
                compressed_tokens=original_tokens
            )
        
        keep_first = 2
        keep_last = 2
        
        first_messages = messages[:keep_first]
        last_messages = messages[-keep_last:]
        middle_messages = messages[keep_first:-keep_last]
        
        compressed_middle = []
        current_tokens = sum(m.token_count for m in first_messages + last_messages)
        
        for msg in middle_messages:
            if current_tokens + msg.token_count <= target_tokens:
                compressed_middle.append(msg)
                current_tokens += msg.token_count
        
        compressed = first_messages + compressed_middle + last_messages
        compressed_tokens = sum(m.token_count for m in compressed)
        
        removed = [m for m in middle_messages if m not in compressed_middle]
        
        result = CompressionResult(
            original_count=len(messages),
            compressed_count=len(compressed),
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            removed_messages=[m.to_dict() for m in removed]
        )
        
        return compressed, result
    
    def _compress_semantic(
        self,
        messages: List[ChatMessage],
        target_ratio: float
    ) -> Tuple[List[ChatMessage], CompressionResult]:
        original_tokens = sum(m.token_count for m in messages)
        target_tokens = int(original_tokens * target_ratio)
        
        scored_messages = []
        for i, msg in enumerate(messages):
            score = self._calculate_semantic_score(msg, i, len(messages))
            scored_messages.append((score, i, msg))
        
        scored_messages.sort(key=lambda x: (-x[0], x[1]))
        
        selected_indices = set()
        current_tokens = 0
        
        for score, idx, msg in scored_messages:
            if current_tokens + msg.token_count <= target_tokens:
                selected_indices.add(idx)
                current_tokens += msg.token_count
        
        compressed = [msg for i, msg in enumerate(messages) if i in selected_indices]
        compressed_tokens = sum(m.token_count for m in compressed)
        
        removed = [msg for i, msg in enumerate(messages) if i not in selected_indices]
        
        result = CompressionResult(
            original_count=len(messages),
            compressed_count=len(compressed),
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            removed_messages=[m.to_dict() for m in removed]
        )
        
        return compressed, result
    
    def _compress_importance(
        self,
        messages: List[ChatMessage],
        target_ratio: float
    ) -> Tuple[List[ChatMessage], CompressionResult]:
        original_tokens = sum(m.token_count for m in messages)
        target_tokens = int(original_tokens * target_ratio)
        
        scored_messages = []
        for i, msg in enumerate(messages):
            score = msg.importance + (msg.priority == MessagePriority.CRITICAL) * 2 + (msg.priority == MessagePriority.HIGH) * 1
            scored_messages.append((score, i, msg))
        
        scored_messages.sort(key=lambda x: (-x[0], x[1]))
        
        selected_indices = set()
        current_tokens = 0
        
        for score, idx, msg in scored_messages:
            if current_tokens + msg.token_count <= target_tokens:
                selected_indices.add(idx)
                current_tokens += msg.token_count
        
        compressed = [msg for i, msg in enumerate(messages) if i in selected_indices]
        compressed_tokens = sum(m.token_count for m in compressed)
        
        removed = [msg for i, msg in enumerate(messages) if i not in selected_indices]
        
        result = CompressionResult(
            original_count=len(messages),
            compressed_count=len(compressed),
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            removed_messages=[m.to_dict() for m in removed]
        )
        
        return compressed, result
    
    def _generate_summary(self, messages: List[ChatMessage]) -> str:
        user_messages = [m for m in messages if m.role == MessageRole.USER]
        assistant_messages = [m for m in messages if m.role == MessageRole.ASSISTANT]
        
        topics = self._extract_topics(user_messages)
        actions = self._extract_actions(assistant_messages)
        
        summary_parts = []
        
        if topics:
            topics_str = "、".join(topics[:5])
            summary_parts.append(f"用户讨论了{topics_str}等话题")
        
        if actions:
            actions_str = "、".join(actions[:5])
            summary_parts.append(f"助手{actions_str}")
        
        if not summary_parts:
            summary_parts.append(f"共进行了{len(user_messages)}轮对话")
        
        summary = "。".join(summary_parts) + "。"
        
        if len(summary) > self.summary_max_length:
            summary = summary[:self.summary_max_length - 3] + "..."
        
        return summary
    
    def _extract_topics(self, messages: List[ChatMessage]) -> List[str]:
        topics = []
        
        keywords_patterns = [
            r'(?:关于|请问|如何|怎么|为什么|怎样)\s*([^\?\。\,\！]+)',
            r'([^\?\。\,\！]{2,10})(?:的问题|的功能|的实现|的方法)'
        ]
        
        for msg in messages:
            content = msg.content
            for pattern in keywords_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    topic = match.strip()
                    if len(topic) >= 2 and len(topic) <= 20:
                        if topic not in topics:
                            topics.append(topic)
        
        return topics
    
    def _extract_actions(self, messages: List[ChatMessage]) -> List[str]:
        actions = []
        
        action_patterns = [
            r'(?:提供了|给出了|解释了|说明了|实现了|创建了)\s*([^\。\,\！]+)',
            r'(?:建议|推荐)([^\。\,\！]+)'
        ]
        
        for msg in messages:
            content = msg.content
            for pattern in action_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    action = match.strip()
                    if len(action) >= 2 and len(action) <= 30:
                        if action not in actions:
                            actions.append(action)
        
        if not actions:
            if any('代码' in m.content or '```' in m.content for m in messages):
                actions.append("提供了代码示例")
            if any('解释' in m.content for m in messages):
                actions.append("进行了解释")
            if any('建议' in m.content for m in messages):
                actions.append("给出了建议")
        
        return actions
    
    def _calculate_semantic_score(
        self,
        message: ChatMessage,
        index: int,
        total: int
    ) -> float:
        score = message.importance
        
        position_weight = 1.0 - (index / total) if index < 3 else 0.5
        score += position_weight * 0.3
        
        recency_weight = index / total
        score += recency_weight * 0.2
        
        role_weight = {
            MessageRole.USER: 0.8,
            MessageRole.ASSISTANT: 0.6,
            MessageRole.SYSTEM: 1.0,
            MessageRole.FUNCTION: 0.4
        }.get(message.role, 0.5)
        score += role_weight * 0.2
        
        content_features = self._extract_content_features(message.content)
        score += content_features * 0.3
        
        return score
    
    def _extract_content_features(self, content: str) -> float:
        features = 0.0
        
        if re.search(r'\?\?|？', content):
            features += 0.2
        
        if re.search(r'```|def |class |function', content):
            features += 0.3
        
        if re.search(r'错误|error|bug|问题', content, re.IGNORECASE):
            features += 0.2
        
        if re.search(r'重要|关键|核心|必须', content):
            features += 0.2
        
        return min(1.0, features)
    
    def _estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        other_chars = len(text) - chinese_chars - sum(len(w) for w in re.findall(r'[a-zA-Z]+', text))
        return int(chinese_chars * 1.5 + english_words * 1.3 + other_chars * 0.5) + 1


_dialog_compressor: Optional[DialogCompressor] = None


def get_dialog_compressor(**kwargs) -> DialogCompressor:
    global _dialog_compressor
    if _dialog_compressor is None:
        _dialog_compressor = DialogCompressor(**kwargs)
    return _dialog_compressor
