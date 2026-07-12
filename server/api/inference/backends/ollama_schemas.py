from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class OllamaOptions(BaseModel):
    num_predict: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    repeat_penalty: Optional[float] = None
    stop: Optional[list[str]] = None
    num_ctx: Optional[int] = None
    num_batch: Optional[int] = None
    num_thread: Optional[int] = None
    num_gpu: Optional[int] = None
    use_mmap: Optional[bool] = None
    use_mlock: Optional[bool] = None


class OllamaPullRequest(BaseModel):
    name: str
    stream: bool = Field(default=False, description="Strictly enforce stream behavior for pull")


class OllamaGenerateRequest(BaseModel):
    model: str
    prompt: str
    stream: bool = Field(default=False, description="Generate stream behavior")
    options: Optional[OllamaOptions] = None
    keep_alive: Optional[str] = None
    think: Optional[bool] = None


class OllamaMessage(BaseModel):
    """Ollama chat message; content may be empty when tool_calls are present."""

    model_config = ConfigDict(extra="allow")

    role: str
    content: Optional[str] = ""
    tool_calls: Optional[list[dict[str, Any]]] = None
    tool_name: Optional[str] = None
    tool_call_id: Optional[str] = None


class OllamaChatRequest(BaseModel):
    model: str
    messages: list[OllamaMessage]
    stream: bool = Field(default=False, description="Chat stream behavior")
    format: Optional[str | dict] = None
    options: Optional[OllamaOptions] = None
    keep_alive: Optional[str] = None
    think: Optional[bool] = None
    tools: Optional[list[dict[str, Any]]] = None
    tool_choice: Optional[str | dict[str, Any]] = None
