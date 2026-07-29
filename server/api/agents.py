from __future__ import annotations

from typing import Any

from agent_session.agent_registry import AgentRegistry
from agent_session.models import AgentSkillRegistryResponse
from agent_session.runtime import describe_skill_registry
from agent_session.runtime_policy import build_agent_definition_policy, build_agent_runtime_policy
from agent_session.service import AgentSessionService
from fastapi import APIRouter, Depends, HTTPException, Query

from api.agent_sessions import get_agent_session_service, get_agent_session_user
from core.db_manager import run_sync
from security.jwt_auth import TokenPayload

router = APIRouter(prefix="/agents", tags=["Agents"])
_registry: AgentRegistry | None = None


@router.get("", response_model=list[dict[str, Any]])
async def list_agents(current_user: TokenPayload = Depends(get_agent_session_user)):
    try:
        return [_agent_payload(agent) for agent in _get_registry().list_agents()]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/primary", response_model=list[dict[str, Any]])
async def list_primary_agents(current_user: TokenPayload = Depends(get_agent_session_user)):
    try:
        return [_agent_payload(agent) for agent in _get_registry().list_primary_agents()]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/skills", response_model=AgentSkillRegistryResponse)
async def list_agent_skills(
    project_path: str | None = Query(default=None),
    agent_id: str = Query(default="build"),
    service: AgentSessionService = Depends(get_agent_session_service),
    current_user: TokenPayload = Depends(get_agent_session_user),
):
    try:
        resolved_project_path = await run_sync(service.validate_project_path, project_path)
        result = await run_sync(describe_skill_registry, resolved_project_path, agent_id=agent_id)
        agent = _get_registry().get(agent_id)
        policy = await run_sync(
            build_agent_runtime_policy,
            agent=agent,
            agent_id=agent_id,
            project_path=resolved_project_path,
            runtime_kind="agent_session",
            agent_registry=_get_registry(),
        )
        policy_payload = policy.model_dump()
        result["runtime_policy"] = policy_payload
        result["resource_profile"] = policy_payload["resource_profile"]
        return AgentSkillRegistryResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{agent_id}", response_model=dict[str, Any])
async def get_agent(agent_id: str, current_user: TokenPayload = Depends(get_agent_session_user)):
    try:
        agent = _get_registry().get(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        return _agent_payload(agent)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _get_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry


def _agent_payload(agent: Any) -> dict[str, Any]:
    payload = agent.model_dump()
    payload["runtime_policy"] = build_agent_definition_policy(agent)
    payload["execution_plan"] = payload["runtime_policy"]["execution_plan"]
    return payload
