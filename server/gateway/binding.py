"""
Gateway binding router and manager.
"""
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .models import AgentInfo, BindingRule

logger = logging.getLogger(__name__)


class BindingType(str, Enum):
    PEER = "peer"
    GUILD = "guild"
    CHANNEL = "channel"
    TEAM = "team"
    ACCOUNT = "account"


@dataclass
class Binding:
    binding_id: str
    binding_type: BindingType
    target_id: str
    agent_id: str
    priority: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class BindingMatch:
    binding: Binding
    match_score: float = 1.0
    match_details: dict[str, Any] = field(default_factory=dict)


class BindingRouter:
    PRIORITY_ORDER = [
        BindingType.PEER,
        BindingType.CHANNEL,
        BindingType.GUILD,
        BindingType.TEAM,
        BindingType.ACCOUNT,
    ]

    def __init__(self):
        self._bindings: dict[str, Binding] = {}
        self._bindings_by_agent: dict[str, list[str]] = {}
        self._bindings_by_target: dict[str, list[str]] = {}

    def add_binding(self, binding: Binding) -> None:
        self._bindings[binding.binding_id] = binding

        self._bindings_by_agent.setdefault(binding.agent_id, []).append(binding.binding_id)

        target_key = f"{binding.binding_type.value}:{binding.target_id}"
        self._bindings_by_target.setdefault(target_key, []).append(binding.binding_id)

        logger.info("Added binding %s -> %s", binding.binding_id, binding.agent_id)

    def remove_binding(self, binding_id: str) -> bool:
        binding = self._bindings.get(binding_id)
        if not binding:
            return False

        del self._bindings[binding_id]

        if binding.agent_id in self._bindings_by_agent:
            self._bindings_by_agent[binding.agent_id] = [
                x for x in self._bindings_by_agent[binding.agent_id] if x != binding_id
            ]

        target_key = f"{binding.binding_type.value}:{binding.target_id}"
        if target_key in self._bindings_by_target:
            self._bindings_by_target[target_key] = [
                x for x in self._bindings_by_target[target_key] if x != binding_id
            ]

        return True

    def route(
        self,
        peer_id: str | None = None,
        guild_id: str | None = None,
        channel_id: str | None = None,
        team_id: str | None = None,
        account_id: str | None = None,
    ) -> BindingMatch | None:
        matches: list[BindingMatch] = []

        if peer_id:
            match = self._find_binding(BindingType.PEER, peer_id)
            if match:
                matches.append(match)

        if channel_id:
            match = self._find_binding(BindingType.CHANNEL, channel_id)
            if match:
                matches.append(match)

        if guild_id:
            match = self._find_binding(BindingType.GUILD, guild_id)
            if match:
                matches.append(match)

        if team_id:
            match = self._find_binding(BindingType.TEAM, team_id)
            if match:
                matches.append(match)

        if account_id:
            match = self._find_binding(BindingType.ACCOUNT, account_id)
            if match:
                matches.append(match)

        if not matches:
            return None

        matches.sort(
            key=lambda m: (
                self.PRIORITY_ORDER.index(m.binding.binding_type),
                -m.binding.priority,
                -m.match_score,
            )
        )

        return matches[0]

    def _find_binding(self, binding_type: BindingType, target_id: str) -> BindingMatch | None:
        target_key = f"{binding_type.value}:{target_id}"
        binding_ids = self._bindings_by_target.get(target_key, [])

        enabled_bindings = [
            self._bindings[bid]
            for bid in binding_ids
            if bid in self._bindings and self._bindings[bid].enabled
        ]
        if not enabled_bindings:
            return None

        enabled_bindings.sort(key=lambda b: -b.priority)
        return BindingMatch(
            binding=enabled_bindings[0],
            match_score=1.0,
            match_details={"type": binding_type.value, "target": target_id},
        )


class BindingManager:
    def __init__(self):
        self._router = BindingRouter()
        self._agents: dict[str, AgentInfo] = {}
        self._bindings: dict[str, BindingRule] = {}
        self._default_agent_id: str | None = None

    def register_agent(self, agent: AgentInfo) -> bool:
        self._agents[agent.id] = agent
        return True

    def unregister_agent(self, agent_id: str) -> bool:
        if agent_id not in self._agents:
            return False

        del self._agents[agent_id]
        to_remove = [rid for rid, rule in self._bindings.items() if rule.agent_id == agent_id]
        for rid in to_remove:
            self.remove_binding(rid)

        if self._default_agent_id == agent_id:
            self._default_agent_id = None
        return True

    def set_default_agent(self, agent_id: str) -> bool:
        if agent_id not in self._agents:
            return False
        self._default_agent_id = agent_id
        return True

    @staticmethod
    def _to_runtime_binding(rule: BindingRule) -> Binding:
        if rule.peer_id:
            btype = BindingType.PEER
            target = rule.peer_id
        elif rule.channel_id:
            btype = BindingType.CHANNEL
            target = rule.channel_id
        elif rule.guild_id:
            btype = BindingType.GUILD
            target = rule.guild_id
        elif rule.team_id:
            btype = BindingType.TEAM
            target = rule.team_id
        else:
            btype = BindingType.ACCOUNT
            target = rule.account_id or "default"

        return Binding(
            binding_id=rule.id,
            binding_type=btype,
            target_id=target,
            agent_id=rule.agent_id,
            priority=rule.priority,
            metadata=rule.metadata,
            enabled=rule.enabled,
        )

    def add_binding(self, rule: BindingRule) -> bool:
        if rule.agent_id not in self._agents:
            return False

        self._bindings[rule.id] = rule
        self._router.add_binding(self._to_runtime_binding(rule))
        return True

    def create_binding(
        self,
        binding_type: BindingType,
        target_id: str,
        agent_id: str,
        priority: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> Binding:
        if agent_id not in self._agents:
            self._agents[agent_id] = AgentInfo(id=agent_id, name=agent_id, workspace_path=".")

        rule = BindingRule(
            id=f"binding_{uuid.uuid4().hex[:8]}",
            agent_id=agent_id,
            peer_id=target_id if binding_type == BindingType.PEER else None,
            guild_id=target_id if binding_type == BindingType.GUILD else None,
            channel_id=target_id if binding_type == BindingType.CHANNEL else None,
            team_id=target_id if binding_type == BindingType.TEAM else None,
            account_id=target_id if binding_type == BindingType.ACCOUNT else None,
            priority=priority,
            metadata=metadata or {},
            enabled=True,
        )
        self.add_binding(rule)
        return self._to_runtime_binding(rule)

    def remove_binding(self, rule_id: str) -> bool:
        self._bindings.pop(rule_id, None)
        return self._router.remove_binding(rule_id)

    def delete_binding(self, binding_id: str) -> bool:
        return self.remove_binding(binding_id)

    def get_all_bindings(self) -> list[BindingRule]:
        return list(self._bindings.values())

    def get_agent_bindings(self, agent_id: str) -> list[BindingRule]:
        return [rule for rule in self._bindings.values() if rule.agent_id == agent_id]

    def find_agent(
        self,
        peer_id: str | None = None,
        guild_id: str | None = None,
        channel_id: str | None = None,
        team_id: str | None = None,
        account_id: str | None = None,
    ) -> str | None:
        match = self._router.route(
            peer_id=peer_id,
            guild_id=guild_id,
            channel_id=channel_id,
            team_id=team_id,
            account_id=account_id,
        )
        if match:
            return match.binding.agent_id
        return self._default_agent_id

    def route_message(
        self,
        peer_id: str | None = None,
        guild_id: str | None = None,
        channel_id: str | None = None,
        team_id: str | None = None,
        account_id: str | None = None,
    ) -> str | None:
        return self.find_agent(
            peer_id=peer_id,
            guild_id=guild_id,
            channel_id=channel_id,
            team_id=team_id,
            account_id=account_id,
        )

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_agents": len(self._agents),
            "total_bindings": len(self._bindings),
            "enabled_bindings": sum(1 for x in self._bindings.values() if x.enabled),
            "default_agent": self._default_agent_id,
        }

    def get_router(self) -> BindingRouter:
        return self._router


_binding_manager: BindingManager | None = None


def get_binding_manager() -> BindingManager:
    global _binding_manager
    if _binding_manager is None:
        _binding_manager = BindingManager()
    return _binding_manager
