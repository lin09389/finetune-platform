"""Workflow template API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core.db_manager import run_sync
from agent_runtime_legacy.service import AgentRuntimeService
from workflow_templates.models import WorkflowTemplateCreate, WorkflowTemplateResponse, WorkflowTemplateUpdate
from workflow_templates.service import WorkflowTemplateService

router = APIRouter(tags=["Workflows"])

_service: WorkflowTemplateService | None = None
_runtime_service: AgentRuntimeService | None = None


def get_workflow_template_service() -> WorkflowTemplateService:
    global _service
    if _service is None:
        _service = WorkflowTemplateService()
    return _service


def get_agent_runtime_service() -> AgentRuntimeService:
    """Compatibility provider used by legacy tests and overrides."""
    global _runtime_service
    if _runtime_service is None:
        _runtime_service = AgentRuntimeService()
    return _runtime_service


@router.get("/workflows/templates", response_model=list[WorkflowTemplateResponse])
async def list_workflow_templates(service: WorkflowTemplateService = Depends(get_workflow_template_service)):
    return await run_sync(service.list_templates)


@router.post("/workflows/templates", response_model=WorkflowTemplateResponse)
async def create_workflow_template(
    request: WorkflowTemplateCreate,
    service: WorkflowTemplateService = Depends(get_workflow_template_service),
):
    return await run_sync(service.create_template, request)


@router.get("/workflows/templates/{template_id}", response_model=WorkflowTemplateResponse)
async def get_workflow_template(
    template_id: str,
    service: WorkflowTemplateService = Depends(get_workflow_template_service),
):
    return await run_sync(service.get_template, template_id)


@router.put("/workflows/templates/{template_id}", response_model=WorkflowTemplateResponse)
async def update_workflow_template(
    template_id: str,
    request: WorkflowTemplateUpdate,
    service: WorkflowTemplateService = Depends(get_workflow_template_service),
):
    return await run_sync(service.update_template, template_id, request)


@router.delete("/workflows/templates/{template_id}")
async def delete_workflow_template(
    template_id: str,
    service: WorkflowTemplateService = Depends(get_workflow_template_service),
):
    return await run_sync(service.delete_template, template_id)
