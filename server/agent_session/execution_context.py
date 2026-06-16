from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AgentMode = Literal["primary", "subagent", "all"]
AgentDefinitionFormat = Literal["agent_manifest_v2", "runtime"]


class SystemPromptDefinition(BaseModel):
    identity: str = ""
    role: str = ""
    tone: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    workflow: list[Any] = Field(default_factory=list)
    sections: dict[str, Any] = Field(default_factory=dict)


class OutputSchemaDefinition(BaseModel):
    format: str = "plain_text"
    instructions: str = ""
    required_sections: list[str] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list)
    json_schema: dict[str, Any] = Field(default_factory=dict, alias="schema")


class FewShotExample(BaseModel):
    name: str = ""
    user: str
    assistant: str
    context: str = ""


class ReflectionRules(BaseModel):
    before_tool_use: list[str] = Field(default_factory=list)
    before_edit: list[str] = Field(default_factory=list)
    before_final: list[str] = Field(default_factory=list)
    on_error: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    sections: dict[str, Any] = Field(default_factory=dict)


class AgentRuntimeDefaults(BaseModel):
    default_provider: str = "openai"
    default_model: str | None = None
    max_iterations: int = 6


class AgentToolPolicy(BaseModel):
    allowed: list[str] = Field(default_factory=list)
    denied: list[str] = Field(default_factory=list)
    notes: str = ""


class AgentHandoffPolicy(BaseModel):
    targets: list[str] = Field(default_factory=list)
    async_targets: list[str] = Field(default_factory=list)
    notes: str = ""


class AgentManifestV2(BaseModel):
    schema_version: int | str = 2
    id: str
    name: str | None = None
    description: str = ""
    mode: AgentMode = "all"
    hidden: bool = False
    system_prompt: SystemPromptDefinition
    output_schema: OutputSchemaDefinition = Field(default_factory=OutputSchemaDefinition)
    few_shot_examples: list[FewShotExample] = Field(default_factory=list)
    reflection_rules: ReflectionRules = Field(default_factory=ReflectionRules)
    runtime: AgentRuntimeDefaults = Field(default_factory=AgentRuntimeDefaults)
    tools: AgentToolPolicy = Field(default_factory=AgentToolPolicy)
    handoff: AgentHandoffPolicy = Field(default_factory=AgentHandoffPolicy)
    metadata: dict[str, Any] = Field(default_factory=dict)


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
    schema_version: int | str = 1
    definition_format: AgentDefinitionFormat = "runtime"
    system_prompt_definition: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    few_shot_examples: list[dict[str, Any]] = Field(default_factory=list)
    reflection_rules: dict[str, Any] = Field(default_factory=dict)
    tool_policy: dict[str, Any] = Field(default_factory=dict)
    handoff_policy: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

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


__all__ = [
    "AgentDefinition",
    "AgentHandoffPolicy",
    "AgentManifestV2",
    "AgentRuntimeDefaults",
    "AgentToolPolicy",
    "FewShotExample",
    "OutputSchemaDefinition",
    "ReflectionRules",
    "RuntimeExecutionContext",
    "SystemPromptDefinition",
]
