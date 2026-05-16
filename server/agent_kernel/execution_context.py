from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentDefinition(BaseModel):
    id: str
    name: str
    description: str = ""
    mode: str = "all"
    system_prompt: str = ""
    output_requirements: str = ""
    default_provider: str = "minimax"
    default_model: str | None = None
    max_iterations: int = 6
    tools: list[str] = Field(default_factory=list)
    permission_rules: list[dict[str, Any]] = Field(default_factory=list)
    handoff_targets: list[str] = Field(default_factory=list)
    hidden: bool = False


class RuntimeExecutionContext(BaseModel):
    workflow_id: str
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
