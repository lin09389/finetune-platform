from fastapi import APIRouter

from workspace.project_manager import get_project_manager
from workspace.task_manager import get_task_manager

router = APIRouter(tags=["Compatibility"])

@router.get("/workspace/projects")
async def list_workspace_projects():
    manager = get_project_manager()
    return [project.model_dump() for project in manager.list_projects()]

@router.get("/workspace/tasks")
async def list_workspace_tasks():
    manager = get_task_manager()
    return [task.model_dump() for task in manager.list_tasks()]
