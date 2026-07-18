from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from tool_platform.registry import ToolProjectionContext
from tool_platform.taxonomy import ToolKind, ToolRisk

from .execution_context import AgentDefinition, AgentManifestV2


class AgentRegistry:
    YAML_SUFFIXES = {".yaml", ".yml"}

    def __init__(self, agents_dir: Path | None = None):
        default_agents_dir = Path(__file__).resolve().parent / "agents"
        self.agents_dir = agents_dir or default_agents_dir
        self._agents: dict[str, AgentDefinition] = {}
        self.reload()

    def reload(self) -> None:
        self._agents = {}
        if not self.agents_dir.exists():
            return
        for path in self._iter_agent_files():
            agent = self._load_agent(path)
            if agent.id in self._agents:
                raise ValueError(f"Duplicate agent id '{agent.id}' in {path}")
            self._agents[agent.id] = agent
        self._validate_handoff_graph()

    def list_agents(self, include_hidden: bool = False) -> list[AgentDefinition]:
        agents = list(self._agents.values())
        if include_hidden:
            return agents
        return [agent for agent in agents if not agent.hidden]

    def list_primary_agents(self) -> list[AgentDefinition]:
        return [agent for agent in self.list_agents() if agent.can_start_directly]

    def get(self, agent_id: str) -> AgentDefinition | None:
        return self._agents.get(agent_id)

    def require(self, agent_id: str) -> AgentDefinition:
        agent = self.get(agent_id)
        if agent is None:
            raise KeyError(f"Unknown agent id: {agent_id}")
        return agent

    def validate_tool_selectors(
        self,
        *,
        known_tool_names: Iterable[str] | None = None,
        known_tool_kinds: Iterable[ToolKind] | None = None,
    ) -> None:
        """Optionally validate selectors after a typed tool registry exists."""
        names = None if known_tool_names is None else {str(name) for name in known_tool_names}
        kinds = set(ToolKind) if known_tool_kinds is None else set(known_tool_kinds)
        for agent in self._agents.values():
            policy = agent.tool_policy
            if names is not None:
                for selector_name in (*policy["allowed"], *policy["denied"]):
                    if selector_name not in names:
                        selector_type = "allowed" if selector_name in policy["allowed"] else "denied"
                        known = ", ".join(sorted(names)) or "(none)"
                        raise ValueError(
                            f"Unknown {selector_type} tool selector {selector_name!r} for agent "
                            f"{agent.id!r}. Known canonical names/aliases: {known}"
                        )
            for kind_value in policy["kinds"]:
                kind = ToolKind(kind_value)
                if kind not in kinds:
                    known = ", ".join(sorted(item.value for item in kinds)) or "(none)"
                    raise ValueError(
                        f"Unknown tool kind selector {kind.value!r} for agent {agent.id!r}. "
                        f"Known tool kinds: {known}"
                    )

    def tool_projection_context(
        self,
        agent_id: str,
        *,
        runtime_kind: str | None = None,
        enabled_capabilities: frozenset[str] | None = None,
        provider_facts: dict[str, Any] | None = None,
        model_facts: dict[str, Any] | None = None,
        platform_facts: dict[str, Any] | None = None,
    ) -> ToolProjectionContext:
        """Compile manifest selectors into immutable registry projection data.

        The legacy runtime remains the authority for DeepAgents tools and HITL.
        """
        policy = self.require(agent_id).tool_policy
        allowed_names = frozenset(policy["allowed"]) if policy.get("allowed_explicit") else None
        allowed_kinds = (
            frozenset(ToolKind(value) for value in policy["kinds"])
            if policy["kinds"]
            else None
        )
        risk_value = policy.get("risk_ceiling")
        return ToolProjectionContext(
            agent_id=agent_id,
            allowed_names=allowed_names,
            denied_names=frozenset(policy["denied"]),
            allowed_kinds=allowed_kinds,
            risk_ceiling=ToolRisk(risk_value) if risk_value else None,
            runtime_kind=runtime_kind,
            enabled_capabilities=enabled_capabilities,
            provider_facts=provider_facts or {},
            model_facts=model_facts or {},
            platform_facts=platform_facts or {},
        )

    def _iter_agent_files(self) -> list[Path]:
        legacy_files = sorted(path for path in self.agents_dir.glob("*.md") if path.is_file())
        if legacy_files:
            names = ", ".join(path.name for path in legacy_files)
            raise ValueError(f"Legacy markdown agent definitions are no longer supported: {names}. Use .agent.yaml manifests.")
        yaml_files = [
            path
            for path in self.agents_dir.iterdir()
            if path.is_file() and path.suffix.lower() in self.YAML_SUFFIXES
        ]
        return sorted(yaml_files)

    def _load_agent(self, path: Path) -> AgentDefinition:
        return self._load_yaml_agent(path)

    def _load_yaml_agent(self, path: Path) -> AgentDefinition:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ValueError(f"Agent manifest {path} contains invalid YAML: {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError(f"Agent manifest {path} must contain a YAML mapping")
        raw = self._normalize_manifest_keys(raw)
        if str(raw.get("schema_version", "2")) not in {"2", "agent.manifest.v2"}:
            raise ValueError(f"Agent manifest {path} has unsupported schema_version: {raw.get('schema_version')}")
        raw.setdefault("id", path.stem.removesuffix(".agent"))
        raw.setdefault("name", raw["id"])
        manifest = AgentManifestV2(**raw)
        return self._compile_manifest(manifest)

    def _normalize_manifest_keys(self, raw: dict[str, Any]) -> dict[str, Any]:
        aliases = {
            "SystemPrompt": "system_prompt",
            "OutputSchema": "output_schema",
            "FewShotExamples": "few_shot_examples",
            "TrajectoryPolicy": "trajectory_policy",
            "ReflectionRules": "reflection_rules",
            "Runtime": "runtime",
            "Tools": "tools",
            "Handoff": "handoff",
            "Metadata": "metadata",
        }
        normalized: dict[str, Any] = {}
        for key, value in raw.items():
            normalized[aliases.get(str(key), str(key))] = value
        if isinstance(normalized.get("tools"), list):
            normalized["tools"] = {"allowed": normalized["tools"]}
        if "handoff_targets" in normalized or "async_subagent_targets" in normalized:
            handoff = dict(normalized.get("handoff") or {})
            handoff.setdefault("targets", normalized.pop("handoff_targets", []))
            handoff.setdefault("async_targets", normalized.pop("async_subagent_targets", []))
            normalized["handoff"] = handoff
        if isinstance(normalized.get("handoff"), dict):
            handoff = dict(normalized["handoff"])
            handoff["targets"] = self._clean_list(handoff.get("targets"))
            handoff["async_targets"] = self._clean_list(handoff.get("async_targets"))
            normalized["handoff"] = handoff
        if "default_provider" in normalized or "default_model" in normalized or "max_iterations" in normalized:
            runtime = dict(normalized.get("runtime") or {})
            for key in ("default_provider", "default_model", "max_iterations"):
                if key in normalized:
                    runtime.setdefault(key, normalized.pop(key))
            normalized["runtime"] = runtime
        return normalized

    def _compile_manifest(self, manifest: AgentManifestV2) -> AgentDefinition:
        system_prompt = self._compile_system_prompt(manifest)
        output_requirements = self._compile_output_requirements(manifest)
        metadata = dict(manifest.metadata)
        metadata["agent_manifest"] = {
            "schema_version": manifest.schema_version,
            "definition_format": "agent_manifest_v2",
        }
        return AgentDefinition(
            id=manifest.id,
            name=manifest.name or manifest.id,
            description=manifest.description,
            mode=manifest.mode,
            system_prompt=system_prompt,
            output_requirements=output_requirements,
            default_provider=manifest.runtime.default_provider,
            default_model=manifest.runtime.default_model,
            max_iterations=manifest.runtime.max_iterations,
            tools=self._clean_list(manifest.tools.allowed),
            handoff_targets=self._clean_list(manifest.handoff.targets),
            async_subagent_targets=self._clean_list(manifest.handoff.async_targets),
            hidden=manifest.hidden,
            schema_version=manifest.schema_version,
            definition_format="agent_manifest_v2",
            system_prompt_definition=manifest.system_prompt.model_dump(),
            output_schema=manifest.output_schema.model_dump(by_alias=True),
            few_shot_examples=[example.model_dump() for example in manifest.few_shot_examples],
            trajectory_policy=manifest.trajectory_policy.model_dump(),
            reflection_rules=manifest.reflection_rules.model_dump(),
            tool_policy={
                **manifest.tools.stable_dump(),
                "enforcement_status": "legacy_runtime",
            },
            handoff_policy=manifest.handoff.model_dump(),
            metadata=metadata,
        )

    def _compile_system_prompt(self, manifest: AgentManifestV2) -> str:
        prompt = manifest.system_prompt
        sections: list[str] = []
        for title, body in (
            ("身份", prompt.identity),
            ("角色", prompt.role),
            ("语气", prompt.tone),
        ):
            if body.strip():
                sections.append(f"## {title}\n{body.strip()}")
        sections.extend(
            self._compile_list_section("职责", prompt.responsibilities),
        )
        sections.extend(
            self._compile_list_section("约束", prompt.constraints),
        )
        if prompt.workflow:
            sections.append(f"## 工作流\n{self._format_yaml_block(prompt.workflow)}")
        for title, body in prompt.sections.items():
            rendered = self._format_section_body(body)
            if rendered:
                sections.append(f"## {title}\n{rendered}")
        if manifest.few_shot_examples:
            examples = []
            for index, example in enumerate(manifest.few_shot_examples, start=1):
                label = example.name or f"example_{index}"
                parts = [f"### {label}"]
                if example.context.strip():
                    parts.append(f"Context: {example.context.strip()}")
                parts.append(f"User: {example.user.strip()}")
                if example.steps:
                    parts.append("Trajectory:")
                    parts.extend(self._compile_few_shot_steps(example.steps))
                elif example.assistant.strip():
                    parts.append(f"Assistant: {example.assistant.strip()}")
                examples.append("\n".join(parts))
            sections.append("## Few-shot Examples\n" + "\n\n".join(examples))
        reflection = self._compile_reflection_rules(manifest)
        if reflection:
            sections.append(reflection)
        return "\n\n".join(section for section in sections if section.strip()).strip()

    @staticmethod
    def _compile_few_shot_steps(steps: list[Any]) -> list[str]:
        rendered: list[str] = []
        for index, step in enumerate(steps, start=1):
            if step.type == "assistant":
                detail = step.content.strip()
            elif step.type == "tool_call":
                arguments = yaml.safe_dump(
                    step.arguments,
                    allow_unicode=True,
                    sort_keys=False,
                    default_flow_style=True,
                ).strip()
                detail = f"{step.tool} {arguments}"
            else:
                detail = f"{step.tool}: {(step.result or step.content).strip()}"
            rendered.append(f"{index}. {step.type}: {detail}")
        return rendered

    def _compile_output_requirements(self, manifest: AgentManifestV2) -> str:
        schema = manifest.output_schema
        sections: list[str] = []
        if schema.format:
            sections.append(f"- format: {schema.format}")
        if schema.instructions.strip():
            sections.append(schema.instructions.strip())
        if schema.required_sections:
            sections.append("Required sections:\n" + "\n".join(f"- {item}" for item in schema.required_sections))
        if schema.required_fields:
            sections.append("Required fields:\n" + "\n".join(f"- {item}" for item in schema.required_fields))
        if schema.json_schema:
            sections.append("Schema:\n" + self._format_yaml_block(schema.json_schema))
        return "\n\n".join(sections).strip()

    def _compile_reflection_rules(self, manifest: AgentManifestV2) -> str:
        reflection = manifest.reflection_rules
        sections: list[str] = []
        for title, rules in (
            ("Before tool use", reflection.before_tool_use),
            ("Before edit", reflection.before_edit),
            ("Before final", reflection.before_final),
            ("On error", reflection.on_error),
            ("General rules", reflection.rules),
        ):
            sections.extend(self._compile_list_section(title, rules, heading_level=3))
        for title, body in reflection.sections.items():
            rendered = self._format_section_body(body)
            if rendered:
                sections.append(f"### {title}\n{rendered}")
        return "## Reflection Rules\n" + "\n\n".join(sections) if sections else ""

    def _compile_list_section(self, title: str, items: list[Any], *, heading_level: int = 2) -> list[str]:
        values = [self._format_section_body(item) for item in items]
        values = [value for value in values if value]
        if not values:
            return []
        heading = "#" * heading_level
        return [f"{heading} {title}\n" + "\n".join(f"- {value}" for value in values)]

    def _format_section_body(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float, bool)):
            return str(value)
        return self._format_yaml_block(value)

    def _format_yaml_block(self, value: Any) -> str:
        return yaml.safe_dump(value, allow_unicode=True, sort_keys=False).strip()

    def _clean_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, tuple):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("[") and stripped.endswith("]"):
                body = stripped[1:-1].strip()
                if not body:
                    return []
                return [
                    item.strip().strip("'\"")
                    for item in body.split(",")
                    if item.strip()
                ]
            return [stripped]
        raise ValueError(f"Expected list-compatible manifest value, got {type(value).__name__}")

    def _validate_handoff_graph(self) -> None:
        for agent in self._agents.values():
            if agent.handoff_targets and not agent.can_delegate:
                raise ValueError(f"Agent '{agent.id}' cannot declare handoff_targets in mode '{agent.mode}'")
            for target_id in agent.handoff_targets:
                target = self._agents.get(target_id)
                if target is None:
                    raise ValueError(f"Unknown handoff target '{target_id}' for agent '{agent.id}'")
                if not target.can_be_handoff_target:
                    raise ValueError(
                        f"Handoff target '{target_id}' for agent '{agent.id}' cannot be used as a subagent in mode '{target.mode}'"
                    )
            for target_id in agent.async_subagent_targets:
                if target_id not in agent.handoff_targets:
                    raise ValueError(
                        f"Async subagent target '{target_id}' for agent '{agent.id}' must also be declared in handoff_targets"
                    )
                target = self._agents.get(target_id)
                if target is None:
                    raise ValueError(f"Unknown async subagent target '{target_id}' for agent '{agent.id}'")
                if not target.can_be_handoff_target:
                    raise ValueError(
                        f"Async subagent target '{target_id}' for agent '{agent.id}' cannot be used as a subagent in mode '{target.mode}'"
                    )

__all__ = ["AgentRegistry"]
