"""Workflow API routes backed by the multi-agent runtime."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from agent_runtime.models import (
    WorkflowApprovalRequest,
    WorkflowActionResponse,
    WorkflowContextProfile,
    WorkflowContextProfileUpdate,
    WorkflowContextSnapshotResponse,
    WorkflowCreate,
    WorkflowMemoryEntryResponse,
    WorkflowObservabilityResponse,
    WorkflowResponse,
    WorkflowStepLogResponse,
    WorkflowTemplateCreate,
    WorkflowTemplateResponse,
    WorkflowTemplateUpdate,
    WorkflowToolCallResponse,
)
from agent_runtime.service import AgentRuntimeService
from core.db_manager import run_sync

router = APIRouter(tags=["Workflows"])

_service: AgentRuntimeService | None = None


def get_agent_runtime_service() -> AgentRuntimeService:
    global _service
    if _service is None:
        _service = AgentRuntimeService()
    return _service


@router.get("/workflows/templates", response_model=list[WorkflowTemplateResponse])
async def list_workflow_templates(service: AgentRuntimeService = Depends(get_agent_runtime_service)):
    return await run_sync(service.list_templates)


@router.post("/workflows/templates", response_model=WorkflowTemplateResponse)
async def create_workflow_template(
    request: WorkflowTemplateCreate,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await run_sync(service.create_template, request)


@router.get("/workflows/templates/{template_id}", response_model=WorkflowTemplateResponse)
async def get_workflow_template(
    template_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await run_sync(service.get_template, template_id)


@router.put("/workflows/templates/{template_id}", response_model=WorkflowTemplateResponse)
async def update_workflow_template(
    template_id: str,
    request: WorkflowTemplateUpdate,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await run_sync(service.update_template, template_id, request)


@router.delete("/workflows/templates/{template_id}")
async def delete_workflow_template(
    template_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await run_sync(service.delete_template, template_id)


@router.post("/workflows", response_model=WorkflowResponse)
async def create_workflow(
    request: WorkflowCreate,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await run_sync(service.create_workflow, request)


@router.get("/workflows", response_model=list[WorkflowResponse])
async def list_workflows(service: AgentRuntimeService = Depends(get_agent_runtime_service)):
    return await run_sync(service.list_workflows)


@router.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await run_sync(service.get_workflow, workflow_id)


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
    return {"events": await run_sync(service.list_timeline, workflow_id)}


@router.get("/workflows/{workflow_id}/artifacts")
async def get_workflow_artifacts(
    workflow_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return {"artifacts": await run_sync(service.list_artifacts, workflow_id)}


@router.get("/workflows/{workflow_id}/observability", response_model=WorkflowObservabilityResponse)
async def get_workflow_observability(
    workflow_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await run_sync(service.get_observability, workflow_id)


@router.get("/workflows/{workflow_id}/step-logs", response_model=list[WorkflowStepLogResponse])
async def get_workflow_step_logs(
    workflow_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await run_sync(service.list_step_logs, workflow_id)


@router.get("/workflows/{workflow_id}/tool-calls", response_model=list[WorkflowToolCallResponse])
async def get_workflow_tool_calls(
    workflow_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await run_sync(service.list_tool_calls, workflow_id)


@router.get("/workflows/{workflow_id}/actions", response_model=list[WorkflowActionResponse])
async def get_workflow_actions(
    workflow_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await run_sync(service.list_actions, workflow_id)


@router.post("/workflow-actions/{action_id}/approve", response_model=WorkflowActionResponse)
async def approve_workflow_action(
    action_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await service.approve_action(action_id)


@router.post("/workflow-actions/{action_id}/reject", response_model=WorkflowActionResponse)
async def reject_workflow_action(
    action_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await run_sync(service.reject_action, action_id)


@router.post("/workflow-actions/{action_id}/execute", response_model=WorkflowActionResponse)
async def execute_workflow_action(
    action_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await run_sync(service.execute_action, action_id)


@router.get("/workflows/{workflow_id}/events/stream")
async def stream_workflow_events(
    workflow_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    async def event_stream():
        seen: set[str] = set()
        for _ in range(30):
            events = await run_sync(service.list_timeline, workflow_id)
            for event in events:
                event_id = event.get("id")
                if event_id in seen:
                    continue
                seen.add(event_id)
                yield f"event: workflow_event\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/workflows/{workflow_id}/context", response_model=WorkflowContextProfile)
async def get_workflow_context(
    workflow_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await run_sync(service.get_context_profile, workflow_id)


@router.put("/workflows/{workflow_id}/context", response_model=WorkflowContextProfile)
async def update_workflow_context(
    workflow_id: str,
    request: WorkflowContextProfileUpdate,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await run_sync(service.update_context_profile, workflow_id, request)


@router.get("/workflows/{workflow_id}/context/snapshots", response_model=list[WorkflowContextSnapshotResponse])
async def get_workflow_context_snapshots(
    workflow_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await run_sync(service.list_context_snapshots, workflow_id)


@router.get("/workflows/{workflow_id}/memory", response_model=list[WorkflowMemoryEntryResponse])
async def get_workflow_memory(
    workflow_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await run_sync(service.list_memory_entries, workflow_id)


@router.post("/workflow-memory/{memory_id}/revert", response_model=WorkflowMemoryEntryResponse)
async def revert_workflow_memory(
    memory_id: str,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
):
    return await run_sync(service.revert_memory_entry, memory_id)
