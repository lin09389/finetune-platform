from __future__ import annotations

from fastapi import APIRouter, Depends

from agent_runtime.service import AgentRuntimeService
from api.workflows import get_agent_runtime_service

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("")
async def list_agents(service: AgentRuntimeService = Depends(get_agent_runtime_service)):
    return service.list_agents(primary_only=False)


@router.get("/primary")
async def list_primary_agents(service: AgentRuntimeService = Depends(get_agent_runtime_service)):
    return service.list_agents(primary_only=True)


@router.get("/{agent_id}")
async def get_agent(agent_id: str, service: AgentRuntimeService = Depends(get_agent_runtime_service)):
    return service.get_agent(agent_id)
