from fastapi import APIRouter, Query

from api.inference.performance import (
    get_optimization_suggestions,
    get_performance_stats,
    reset_metrics,
)
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


@router.get("/inference/performance")
async def inference_performance_root(period: str = Query(default="1h")):
    return await get_performance_stats(period=period)


@router.get("/inference/performance/recommendations")
async def inference_performance_recommendations():
    return await get_optimization_suggestions()


@router.post("/inference/performance/clear")
async def inference_performance_clear():
    return await reset_metrics()
