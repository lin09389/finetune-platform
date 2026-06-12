from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AgentMode = Literal["primary", "subagent", "all"]


class AgentDefinition(BaseModel):
    id: str
    name: str
    description: str = ""
    mode: AgentMode = "all"
    system_prompt: str = ""
    output_requirements: str = ""
    default_provider: str = "openai"
    default_model: str | None = None
    max_iterations: int = 6
    tools: list[str] = Field(default_factory=list)
    handoff_targets: list[str] = Field(default_factory=list)
    async_subagent_targets: list[str] = Field(default_factory=list)
    hidden: bool = False

    @property
    def can_start_directly(self) -> bool:
        return self.mode in {"primary", "all"}

    @property
    def can_delegate(self) -> bool:
        return self.mode in {"primary", "all"}

    @property
    def can_be_handoff_target(self) -> bool:
        return self.mode in {"subagent", "all"}


class RuntimeExecutionContext(BaseModel):
    session_id: str
    goal: str
    project_path: str | None = None
    project_context: str = ""
    chat_context: str = ""
    memory_context: str = ""
    artifact_context: str = ""
    context_pack: dict[str, Any] = Field(default_factory=dict)
    context_sources: list[dict[str, Any]] = Field(default_factory=list)
    provider: str
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = ["AgentDefinition", "RuntimeExecutionContext"]
