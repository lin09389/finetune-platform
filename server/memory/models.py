"""
记忆数据模型
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from enum import Enum


class MemoryType(str, Enum):
    """记忆类型"""
    PERSONAL = "personal"       # 个人信息（名字、职业、住址�?    PREFERENCE = "preference"   # 用户偏好（喜�?讨厌�?    PROJECT = "project"         # 项目信息（在做什么）
    SKILL = "skill"             # 技能知识（会什么）
    HABIT = "habit"             # 工作习惯（编码风格）
    HISTORY = "history"         # 历史事件（过去发生的事）
    KNOWLEDGE = "knowledge"     # 知识积累（学到的知识�?

# 记忆类型重要性映�?MEMORY_IMPORTANCE = {
    MemoryType.PERSONAL: 0.9,       # 个人信息最重要
    MemoryType.PREFERENCE: 0.8,     # 偏好很重�?    MemoryType.PROJECT: 0.7,        # 项目信息重要
    MemoryType.SKILL: 0.6,          # 技能中�?    MemoryType.HABIT: 0.5,          # 习惯一�?    MemoryType.HISTORY: 0.4,        # 历史较不重要
    MemoryType.KNOWLEDGE: 0.3,      # 知识最不重�?}

# 类型中文标签
MEMORY_TYPE_LABELS = {
    MemoryType.PERSONAL: "个人信息",
    MemoryType.PREFERENCE: "偏好",
    MemoryType.PROJECT: "项目",
    MemoryType.SKILL: "技�?,
    MemoryType.HABIT: "习惯",
    MemoryType.HISTORY: "历史",
    MemoryType.KNOWLEDGE: "知识",
}


@dataclass
class Memory:
    """记忆数据结构"""
    id: str
    content: str                                    # 记忆内容
    memory_type: MemoryType                         # 记忆类型
    importance: float                               # 重要程度 (0-1)
    source: str                                     # 来源（rule/llm/manual�?    created_at: datetime                            # 创建时间
    last_accessed: datetime                         # 最后访问时�?    access_count: int = 0                           # 访问次数
    embedding: Optional[List[float]] = None         # 向量嵌入

    def to_dict(self) -> dict:
        """转换为字�?""
        return {
            'id': self.id,
            'content': self.content,
            'type': self.memory_type.value,
            'importance': self.importance,
            'source': self.source,
            'created_at': self.created_at.isoformat(),
            'last_accessed': self.last_accessed.isoformat(),
            'access_count': self.access_count
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Memory':
        """从字典创�?""
        return cls(
            id=data['id'],
            content=data['content'],
            memory_type=MemoryType(data['type']),
            importance=data.get('importance', 0.5),
            source=data.get('source', 'unknown'),
            created_at=datetime.fromisoformat(data['created_at']) if isinstance(data.get('created_at'), str) else data.get('created_at', datetime.now()),
            last_accessed=datetime.fromisoformat(data['last_accessed']) if isinstance(data.get('last_accessed'), str) else data.get('last_accessed', datetime.now()),
            access_count=data.get('access_count', 0),
            embedding=data.get('embedding')
        )
