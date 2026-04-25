"""Digital Team API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from digital_team.models import ApprovalRequest, ProjectCreate, ProjectResponse, TeamTemplate
from digital_team.service import DigitalTeamService

router = APIRouter(prefix="/digital-team", tags=["Digital Team"])

_service: DigitalTeamService | None = None


def get_digital_team_service() -> DigitalTeamService:
    global _service
    if _service is None:
        _service = DigitalTeamService()
    return _service


@router.get("/templates", response_model=list[TeamTemplate])
async def list_templates(service: DigitalTeamService = Depends(get_digital_team_service)):
    return service.list_templates()


@router.post("/projects", response_model=ProjectResponse)
async def create_project(
    request: ProjectCreate,
    service: DigitalTeamService = Depends(get_digital_team_service),
):
    return service.create_project(request)


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(service: DigitalTeamService = Depends(get_digital_team_service)):
    return service.list_projects()


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    service: DigitalTeamService = Depends(get_digital_team_service),
):
    return service.get_project(project_id)


@router.post("/projects/{project_id}/run", response_model=ProjectResponse)
async def run_project(
    project_id: str,
    service: DigitalTeamService = Depends(get_digital_team_service),
):
    return await service.run_project(project_id)


@router.post("/tasks/{task_id}/approve", response_model=ProjectResponse)
async def approve_task(
    task_id: str,
    request: ApprovalRequest,
    service: DigitalTeamService = Depends(get_digital_team_service),
):
    return await service.approve_task(task_id, approved=request.approved, comment=request.comment)


@router.post("/tasks/{task_id}/retry", response_model=ProjectResponse)
async def retry_task(
    task_id: str,
    service: DigitalTeamService = Depends(get_digital_team_service),
):
    return await service.retry_task(task_id)


@router.get("/projects/{project_id}/timeline")
async def get_timeline(
    project_id: str,
    service: DigitalTeamService = Depends(get_digital_team_service),
):
    return {"events": service.list_timeline(project_id)}


@router.get("/projects/{project_id}/artifacts")
async def get_artifacts(
    project_id: str,
    service: DigitalTeamService = Depends(get_digital_team_service),
):
    return {"artifacts": service.list_artifacts(project_id)}

