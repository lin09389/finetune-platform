from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Query, Depends

from agent_session.agent_registry import AgentRegistry
from agent_session.models import AgentSkillRegistryResponse
from agent_session.runtime import describe_skill_registry
from api.agent_sessions import get_agent_session_user
from security.jwt_auth import TokenPayload
from core.db_manager import run_sync

router = APIRouter(prefix="/agents", tags=["Agents"])
_registry: AgentRegistry | None = None


@router.get("", response_model=list[dict[str, Any]])
async def list_agents(current_user: TokenPayload = Depends(get_agent_session_user)):
    try:
        return [agent.model_dump() for agent in _get_registry().list_agents()]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/primary", response_model=list[dict[str, Any]])
async def list_primary_agents(current_user: TokenPayload = Depends(get_agent_session_user)):
    try:
        return [agent.model_dump() for agent in _get_registry().list_primary_agents()]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/skills", response_model=AgentSkillRegistryResponse)
async def list_agent_skills(
    project_path: str | None = Query(default=None),
    agent_id: str = Query(default="build"),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        result = await run_sync(describe_skill_registry, project_path or ".", agent_id=agent_id)
        return AgentSkillRegistryResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{agent_id}", response_model=dict[str, Any])
async def get_agent(agent_id: str, current_user: TokenPayload = Depends(get_agent_session_user)):
    try:
        agent = _get_registry().get(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent.model_dump()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _get_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry
