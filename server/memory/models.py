"""File-backed long-term memory models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MemoryScope(str, Enum):
    USER = "user"
    AGENT = "agent"
    ORG = "org"


class MemoryType(str, Enum):
    PERSONAL = "personal"
    PREFERENCE = "preference"
    PROJECT = "project"
    SKILL = "skill"
    HABIT = "habit"
    HISTORY = "history"
    KNOWLEDGE = "knowledge"


MEMORY_IMPORTANCE = {
    MemoryType.PERSONAL: 0.9,
    MemoryType.PREFERENCE: 0.8,
    MemoryType.PROJECT: 0.7,
    MemoryType.SKILL: 0.6,
    MemoryType.HABIT: 0.5,
    MemoryType.HISTORY: 0.4,
    MemoryType.KNOWLEDGE: 0.3,
}


MEMORY_TYPE_LABELS = {
    MemoryType.PERSONAL: "个人信息",
    MemoryType.PREFERENCE: "偏好",
    MemoryType.PROJECT: "项目",
    MemoryType.SKILL: "技能",
    MemoryType.HABIT: "习惯",
    MemoryType.HISTORY: "历史",
    MemoryType.KNOWLEDGE: "知识",
}


@dataclass(frozen=True)
class MemoryFileMeta:
    scope: MemoryScope
    namespace: str
    path: str
    writable: bool
    updated_at: str
    version: int = 1
    checksum: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryFile:
    id: str
    path: str
    scope: MemoryScope
    namespace: str
    content: str
    writable: bool
    version: int
    updated_at: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemorySearchResult:
    file_id: str
    path: str
    scope: MemoryScope
    namespace: str
    snippet: str
    score: float
    updated_at: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EpisodeEvent:
    session_id: str
    role: str
    content: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)


# Compatibility shape used by older internal callers and tests.
@dataclass
class Memory:
    id: str
    content: str
    memory_type: MemoryType
    importance: float
    source: str
    created_at: datetime
    last_accessed: datetime
    access_count: int = 0
    embedding: list[float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "type": self.memory_type.value,
            "importance": self.importance,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Memory":
        return cls(
            id=data["id"],
            content=data["content"],
            memory_type=MemoryType(data["type"]),
            importance=data.get("importance", 0.5),
            source=data.get("source", "unknown"),
            created_at=datetime.fromisoformat(data["created_at"]) if isinstance(data.get("created_at"), str) else data.get("created_at", datetime.now()),
            last_accessed=datetime.fromisoformat(data["last_accessed"]) if isinstance(data.get("last_accessed"), str) else data.get("last_accessed", datetime.now()),
            access_count=data.get("access_count", 0),
            embedding=data.get("embedding"),
        )
