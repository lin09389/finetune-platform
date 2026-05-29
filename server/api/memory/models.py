"""DeepAgents-style file memory API models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

MemoryScopeLiteral = Literal["user", "agent", "org"]


class MemoryFileResponse(BaseModel):
    id: str
    path: str
    relative_path: str
    scope: MemoryScopeLiteral
    namespace: str
    content: str
    writable: bool
    version: int
    updated_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryFileUpdateRequest(BaseModel):
    content: str = Field(..., description="Markdown memory file content")
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    scope: MemoryScopeLiteral | None = None
    namespace: str | None = None
    user_id: str = "default"
    top_k: int = Field(default=5, ge=1, le=50)


class MemorySearchResultResponse(BaseModel):
    file_id: str
    path: str
    scope: MemoryScopeLiteral
    namespace: str
    snippet: str
    score: float
    updated_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryConsolidateRequest(BaseModel):
    user_id: str = "default"
    session_id: str | None = None


class MemoryMigrateRequest(BaseModel):
    user_id: str = "default"
