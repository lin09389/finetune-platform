from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from tool_platform.taxonomy import ToolKind, ToolRisk

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


class FewShotStep(BaseModel):
    type: Literal["assistant", "tool_call", "tool_result"]
    content: str = ""
    tool: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: str = ""


class FewShotExample(BaseModel):
    name: str = ""
    user: str
    assistant: str = ""
    context: str = ""
    steps: list[FewShotStep] = Field(default_factory=list)


class TrajectoryPolicy(BaseModel):
    enabled: bool = False
    require_read_before_write: bool = False
    require_context_before_create: bool = False
    validate_after_write: bool = False
    rollback_on_validation_failure: bool = False
    require_verification_after_write: bool = False
    max_auto_corrections: int = Field(default=0, ge=0, le=10)


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
    allowed_explicit: bool = False
    kinds: list[ToolKind] = Field(default_factory=list)
    denied: list[str] = Field(default_factory=list)
    risk_ceiling: ToolRisk | None = None
    notes: str = ""

    def model_post_init(self, __context: Any) -> None:
        """Retain whether ``allowed`` appeared without changing legacy tools."""
        self.allowed_explicit = "allowed" in self.model_fields_set

    @field_validator("kinds", mode="before")
    @classmethod
    def _validate_kinds(cls, value: Any) -> Any:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("tools.kinds must be a list of canonical tool kinds")
        valid = ", ".join(kind.value for kind in ToolKind)
        for item in value:
            if isinstance(item, ToolKind):
                continue
            if not isinstance(item, str) or item not in ToolKind._value2member_map_:
                raise ValueError(f"Unknown tool kind {item!r}. Expected one of: {valid}")
        return value

    @field_validator("risk_ceiling", mode="before")
    @classmethod
    def _validate_risk_ceiling(cls, value: Any) -> Any:
        if value is None or isinstance(value, ToolRisk):
            return value
        valid = ", ".join(risk.value for risk in ToolRisk)
        if not isinstance(value, str) or value not in ToolRisk._value2member_map_:
            raise ValueError(f"Unknown tool risk ceiling {value!r}. Expected one of: {valid}")
        return value

    def stable_dump(self) -> dict[str, Any]:
        return {
            "allowed": list(self.allowed),
            "allowed_explicit": self.allowed_explicit,
            "kinds": [kind.value for kind in self.kinds],
            "denied": list(self.denied),
            "risk_ceiling": self.risk_ceiling.value if self.risk_ceiling else None,
            "notes": self.notes,
        }


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
    trajectory_policy: TrajectoryPolicy = Field(default_factory=TrajectoryPolicy)
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
    trajectory_policy: dict[str, Any] = Field(default_factory=dict)
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
    "FewShotStep",
    "OutputSchemaDefinition",
    "ReflectionRules",
    "RuntimeExecutionContext",
    "SystemPromptDefinition",
    "TrajectoryPolicy",
]
