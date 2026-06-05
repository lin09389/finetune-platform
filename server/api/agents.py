from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from agent_session.agent_registry import AgentRegistry
from agent_session.models import AgentSkillRegistryResponse
from agent_session.runtime import describe_skill_registry

router = APIRouter(prefix="/agents", tags=["Agents"])
_registry: AgentRegistry | None = None


@router.get("")
async def list_agents():
    return [agent.model_dump() for agent in _get_registry().list_agents()]


@router.get("/primary")
async def list_primary_agents():
    return [agent.model_dump() for agent in _get_registry().list_primary_agents()]


@router.get("/skills", response_model=AgentSkillRegistryResponse)
async def list_agent_skills(
    project_path: str | None = Query(default=None),
    agent_id: str = Query(default="build"),
):
    return AgentSkillRegistryResponse(**describe_skill_registry(project_path or ".", agent_id=agent_id))


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    agent = _get_registry().get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent.model_dump()


def _get_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry
