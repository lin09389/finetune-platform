"""Workflow API routes backed by the multi-agent runtime."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from agent_runtime.models import (
    WorkflowApprovalRequest,
    WorkflowCreate,
    WorkflowResponse,
    WorkflowTemplateResponse,
)
from agent_runtime.service import AgentRuntimeService

router = APIRouter(tags=["Workflows"])

_service: AgentRuntimeService | None = None


def get_agent_runtime_service() -> AgentRuntimeService:
    global _service
    if _service is None:
        _service = AgentRuntimeService()
    return _service


@router.get("/workflows/templates", response_model=list[WorkflowTemplateResponse])
async def list_workflow_templates(service: AgentRuntimeService = Depends(get_agent_runtime_service)):
    return service.list_templates()


@router.post("/workflows", response_model=WorkflowResponse)
async def create_workflow(
    request: WorkflowCreate,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return service.create_workflow(request)


@router.get("/workflows", response_model=list[WorkflowResponse])
async def list_workflows(service: AgentRuntimeService = Depends(get_agent_runtime_service)):
    return service.list_workflows()


@router.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return service.get_workflow(workflow_id)


@router.post("/workflows/{workflow_id}/run", response_model=WorkflowResponse)
async def run_workflow(
    workflow_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await service.run_workflow(workflow_id)


@router.post("/workflow-steps/{step_id}/approve", response_model=WorkflowResponse)
async def approve_workflow_step(
    step_id: str,
    request: WorkflowApprovalRequest,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await service.approve_step(step_id, approved=request.approved, comment=request.comment)


@router.post("/workflow-steps/{step_id}/retry", response_model=WorkflowResponse)
async def retry_workflow_step(
    step_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await service.retry_step(step_id)


@router.get("/workflows/{workflow_id}/timeline")
async def get_workflow_timeline(
    workflow_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return {"events": service.list_timeline(workflow_id)}


@router.get("/workflows/{workflow_id}/artifacts")
async def get_workflow_artifacts(
    workflow_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return {"artifacts": service.list_artifacts(workflow_id)}
