from __future__ import annotations

from dataclasses import dataclass

from .agent_registry import AgentRegistry
from .execution_context import AgentDefinition

ASYNC_SUBAGENT_TOOL_NAMES = frozenset(
    {
        "start_async_task",
        "check_async_task",
        "list_async_tasks",
        "update_async_task",
        "cancel_async_task",
    }
)


@dataclass(frozen=True)
class AsyncSubagentTarget:
    id: str
    name: str
    description: str


@dataclass(frozen=True)
class AsyncSubagentManifest:
    parent_id: str
    targets: tuple[AsyncSubagentTarget, ...]

    @property
    def enabled(self) -> bool:
        return bool(self.targets)

    @property
    def target_ids(self) -> tuple[str, ...]:
        return tuple(target.id for target in self.targets)

    def available_label(self) -> str:
        return ", ".join(self.target_ids)

    def resolve(self, requested: str) -> str:
        normalized = requested.strip()
        if not normalized:
            raise ValueError(f"Unknown async subagent type '{requested}'. Available types: {self.available_label()}")
        by_id = {target.id: target.id for target in self.targets}
        by_lower_id = {target.id.lower(): target.id for target in self.targets}
        if normalized in by_id:
            return by_id[normalized]
        lowered = normalized.lower()
        if lowered in by_lower_id:
            return by_lower_id[lowered]
        raise ValueError(f"Unknown async subagent type '{requested}'. Available types: {self.available_label()}")


def async_subagent_manifest_for_agent(
    agent_registry: AgentRegistry,
    agent_or_id: AgentDefinition | str | None,
) -> AsyncSubagentManifest:
    agent = agent_or_id if isinstance(agent_or_id, AgentDefinition) else agent_registry.get(str(agent_or_id or ""))
    if not agent or not agent.can_delegate or not agent.async_subagent_targets:
        parent_id = agent.id if agent else str(agent_or_id or "")
        return AsyncSubagentManifest(parent_id=parent_id, targets=())

    targets: list[AsyncSubagentTarget] = []
    for target_id in agent.async_subagent_targets:
        target = agent_registry.get(target_id)
        if target is None:
            raise ValueError(f"Unknown async subagent target '{target_id}' for agent '{agent.id}'")
        if not target.can_be_handoff_target:
            raise ValueError(f"Async subagent target '{target_id}' for agent '{agent.id}' cannot be used as a subagent")
        targets.append(
            AsyncSubagentTarget(
                id=target.id,
                name=target.name,
                description=target.description or target.name,
            )
        )
    return AsyncSubagentManifest(parent_id=agent.id, targets=tuple(targets))


def resolve_async_subagent_target(
    agent_registry: AgentRegistry,
    parent_agent_id: str,
    subagent_type: str,
) -> AgentDefinition:
    parent = agent_registry.get(parent_agent_id)
    if not parent or not parent.can_delegate:
        raise ValueError(f"Agent '{parent_agent_id}' cannot start async subagents")
    manifest = async_subagent_manifest_for_agent(agent_registry, parent)
    target_id = manifest.resolve(subagent_type)
    target = agent_registry.get(target_id)
    if target is None or not target.can_be_handoff_target:
        raise ValueError(f"Async target '{subagent_type}' is not a subagent")
    return target


__all__ = [
    "ASYNC_SUBAGENT_TOOL_NAMES",
    "AsyncSubagentManifest",
    "AsyncSubagentTarget",
    "async_subagent_manifest_for_agent",
    "resolve_async_subagent_target",
]
