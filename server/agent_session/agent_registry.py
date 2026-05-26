from __future__ import annotations

from pathlib import Path
from typing import Any

from .execution_context import AgentDefinition


class AgentRegistry:
    def __init__(self, agents_dir: Path | None = None):
        default_agents_dir = Path(__file__).resolve().parent / "agents"
        self.agents_dir = agents_dir or default_agents_dir
        self._agents: dict[str, AgentDefinition] = {}
        self.reload()

    def reload(self) -> None:
        self._agents = {}
        if not self.agents_dir.exists():
            return
        for path in sorted(self.agents_dir.glob("*.md")):
            agent = self._load_markdown_agent(path)
            self._agents[agent.id] = agent

    def list_agents(self, include_hidden: bool = False) -> list[AgentDefinition]:
        agents = list(self._agents.values())
        if include_hidden:
            return agents
        return [agent for agent in agents if not agent.hidden]

    def list_primary_agents(self) -> list[AgentDefinition]:
        return [agent for agent in self.list_agents() if agent.mode == "primary"]

    def get(self, agent_id: str) -> AgentDefinition | None:
        return self._agents.get(agent_id)

    def require(self, agent_id: str) -> AgentDefinition:
        agent = self.get(agent_id)
        if agent is None:
            raise KeyError(f"Unknown agent id: {agent_id}")
        return agent

    def _load_markdown_agent(self, path: Path) -> AgentDefinition:
        content = path.read_text(encoding="utf-8")
        if not content.startswith("---"):
            raise ValueError(f"Agent file {path} is missing YAML frontmatter")
        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"Agent file {path} has invalid frontmatter")
        raw = self._parse_frontmatter(parts[1])
        prompt = parts[2].strip()
        raw["id"] = raw.get("id") or raw.get("name") or path.stem
        raw["name"] = raw.get("name") or raw["id"]
        raw["system_prompt"] = prompt
        raw.pop("permission", None)
        raw["tools"] = list(raw.get("tools") or [])
        raw["handoff_targets"] = list(raw.get("handoff_targets") or [])
        return AgentDefinition(**raw)

    def _parse_frontmatter(self, frontmatter: str) -> dict[str, Any]:
        raw: dict[str, Any] = {}
        current_list_key: str | None = None
        current_map_key: str | None = None

        for original_line in frontmatter.splitlines():
            if not original_line.strip():
                continue

            stripped = original_line.strip()
            if stripped.startswith("#"):
                continue

            if original_line.startswith("  - ") and current_list_key:
                raw.setdefault(current_list_key, []).append(self._clean_scalar(stripped[2:].strip()))
                continue

            if original_line.startswith("  ") and current_map_key and ":" in stripped:
                key, value = stripped.split(":", 1)
                raw.setdefault(current_map_key, {})[key.strip()] = self._clean_scalar(value.strip())
                continue

            current_list_key = None
            current_map_key = None
            if ":" not in stripped:
                continue

            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not value:
                if key in {"tools", "handoff_targets"}:
                    raw[key] = []
                    current_list_key = key
                else:
                    raw[key] = {}
                    current_map_key = key
                continue

            raw[key] = self._clean_scalar(value)

        return raw

    def _clean_scalar(self, value: str) -> Any:
        if value in {"true", "True"}:
            return True
        if value in {"false", "False"}:
            return False
        if value.isdigit():
            return int(value)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            return value[1:-1]
        return value

__all__ = ["AgentRegistry"]
