"""统一本地推理服务层类型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LocalInferenceRequest:
    model: str
    backend: str
    prompt: str | None = None
    messages: list[dict[str, str]] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)
    stream: bool = False
    request_id: str | None = None


@dataclass
class LocalInferenceProgress:
    request_id: str
    backend: str
    model: str
    status: str
    emitted_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LocalInferenceResponse:
    request_id: str
    backend: str
    model: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
