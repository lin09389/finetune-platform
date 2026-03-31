"""
记忆 API 数据模型
"""
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """记忆类型"""
    PERSONAL = "personal"
    PREFERENCE = "preference"
    PROJECT = "project"
    SKILL = "skill"
    HABIT = "habit"
    HISTORY = "history"
    KNOWLEDGE = "knowledge"


class MemoryItem(BaseModel):
    """记忆项"""
    id: str = Field(..., description="记忆ID")
    content: str = Field(..., description="记忆内容")
    type: MemoryType = Field(default=MemoryType.KNOWLEDGE, description="记忆类型")
    importance: float = Field(default=0.5, ge=0, le=1, description="重要性")
    source: str = Field(default="api", description="来源")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    access_count: int = Field(default=0, description="访问次数")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")


class MemoryCreateRequest(BaseModel):
    """创建记忆请求"""
    content: str = Field(..., description="记忆内容")
    memory_type: MemoryType = Field(default=MemoryType.KNOWLEDGE, description="记忆类型")
    importance: float = Field(default=0.5, ge=0, le=1, description="重要性")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")


class MemoryUpdateRequest(BaseModel):
    """更新记忆请求"""
    content: str | None = Field(default=None, description="记忆内容")
    importance: float | None = Field(default=None, ge=0, le=1, description="重要性")
    metadata: dict[str, Any] | None = Field(default=None, description="元数据")


class MemorySearchRequest(BaseModel):
    """搜索记忆请求"""
    query: str = Field(..., description="查询文本")
    top_k: int = Field(default=5, ge=1, le=20, description="返回数量")
    memory_type: MemoryType | None = Field(default=None, description="记忆类型过滤")


class MemorySearchResult(BaseModel):
    """搜索结果"""
    id: str
    content: str
    type: MemoryType
    importance: float
    relevance: float = Field(default=0.0, description="相关性分数")
    created_at: datetime
