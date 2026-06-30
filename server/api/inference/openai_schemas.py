"""Pydantic models for the supported OpenAI Chat Completions surface."""

from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OpenAIModel(BaseModel):
    """Reject silently ignored request fields while allowing response extensions."""

    model_config = ConfigDict(extra="forbid")


class ChatCompletionMessage(OpenAIModel):
    role: Literal["developer", "system", "user", "assistant", "tool", "function"]
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class StreamOptions(OpenAIModel):
    include_usage: bool = False


class ChatCompletionRequest(OpenAIModel):
    model: str = Field(min_length=1)
    messages: list[ChatCompletionMessage] = Field(min_length=1)
    temperature: float | None = Field(default=0.7, ge=0, le=2)
    top_p: float | None = Field(default=0.9, ge=0, le=1)
    stream: bool = False
    stream_options: StreamOptions | None = None
    max_tokens: int | None = Field(default=None, ge=1, le=8192)
    max_completion_tokens: int | None = Field(default=None, ge=1, le=8192)
    stop: list[str] | str | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    parallel_tool_calls: bool | None = None
    presence_penalty: float = Field(default=0.0, ge=-2, le=2)
    frequency_penalty: float = Field(default=0.0, ge=-2, le=2)
    repetition_penalty: float = Field(default=1.0, ge=0.1, le=2)
    seed: int | None = None
    n: int = Field(default=1, ge=1)
    response_format: dict[str, Any] | None = None
    logit_bias: dict[str, float] | None = None
    user: str | None = None

    @model_validator(mode="after")
    def validate_token_limit_aliases(self) -> ChatCompletionRequest:
        if self.max_tokens is not None and self.max_completion_tokens is not None:
            raise ValueError("Use either max_tokens or max_completion_tokens, not both")
        return self

    @property
    def resolved_max_tokens(self) -> int:
        return self.max_completion_tokens or self.max_tokens or 1024


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class Choice(BaseModel):
    index: int
    message: ChatCompletionMessage
    finish_reason: str | None = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[Choice]
    usage: Usage | None = None


class DeltaMessage(BaseModel):
    role: Literal["assistant"] | None = None
    content: str | None = None


class StreamChoice(BaseModel):
    index: int
    delta: DeltaMessage
    finish_reason: str | None = None


class ChatCompletionStreamResponse(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[StreamChoice]
    usage: Usage | None = None


class ModelCard(BaseModel):
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "finetune-platform"
    backend: str
    canonical_id: str
    source: str = "local"


class ModelListResponse(BaseModel):
    object: str = "list"
    data: list[ModelCard]
