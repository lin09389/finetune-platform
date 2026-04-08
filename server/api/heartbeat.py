"""
Heartbeat API 路由

提供 Heartbeat 模块的 REST API 端点
"""
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from heartbeat import (
    HeartbeatTask,
    get_heartbeat_scheduler,
)
from heartbeat.task_executor import (
    get_task_executor,
)
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/heartbeat", tags=["Heartbeat"])


def _serialize_task(task: HeartbeatTask) -> dict[str, Any]:
    task_config = dict(task.metadata or {})
    task_type = task_config.pop("type", "check")
    return {
        "id": task.id,
        "name": task.name,
        "description": task.description,
        "schedule": task.schedule,
        "task_type": task_type,
        "enabled": task.enabled,
        "config": task_config,
        "status": task.last_result or "pending",
        "last_run": task.last_run,
        "next_run": task.next_run,
    }


class TaskCreateRequest(BaseModel):
    """任务创建请求"""
    name: str
    description: str = ""
    schedule: str
    task_type: str = "check"
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class TaskResponse(BaseModel):
    """任务响应"""
    id: str
    name: str
    description: str
    schedule: str
    task_type: str
    enabled: bool
    config: dict[str, Any]
    status: str | None = None
    last_run: datetime | None = None


@router.get("/status")
async def get_heartbeat_status():
    """获取 Heartbeat 状态"""
    scheduler = get_heartbeat_scheduler()
    executor = get_task_executor()

    return {
        "scheduler": scheduler.get_stats(),
        "executor": executor.get_stats(),
    }


@router.get("/tasks")
async def list_tasks():
    """列出所有任务"""
    scheduler = get_heartbeat_scheduler()

    tasks = []
    for task_id, task in scheduler._tasks.items():
        tasks.append(_serialize_task(task))

    return {"tasks": tasks, "total": len(tasks)}


@router.post("/tasks")
async def create_task(request: TaskCreateRequest):
    """创建新任务"""
    scheduler = get_heartbeat_scheduler()

    task = HeartbeatTask(
        id=f"task_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        name=request.name,
        description=request.description,
        schedule=request.schedule,
        enabled=request.enabled,
        metadata=request.config,
    )

    scheduler.add_task(task)

    return {"success": True, "task": _serialize_task(task)}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """获取任务详情"""
    scheduler = get_heartbeat_scheduler()

    task = scheduler._tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return _serialize_task(task)


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """删除任务"""
    scheduler = get_heartbeat_scheduler()

    if not scheduler.get_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")

    scheduler.remove_task(task_id)

    return {"success": True, "task_id": task_id, "message": "Task deleted"}


@router.post("/tasks/{task_id}/enable")
async def enable_task(task_id: str):
    """启用任务"""
    scheduler = get_heartbeat_scheduler()

    if not scheduler.get_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")

    scheduler.enable_task(task_id)

    return {
        "success": True,
        "task_id": task_id,
        "enabled": True,
        "message": "Task enabled",
    }


@router.post("/tasks/{task_id}/disable")
async def disable_task(task_id: str):
    """禁用任务"""
    scheduler = get_heartbeat_scheduler()

    if not scheduler.get_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")

    scheduler.disable_task(task_id)

    return {
        "success": True,
        "task_id": task_id,
        "enabled": False,
        "message": "Task disabled",
    }


@router.get("/results")
async def list_results(
    task_id: str | None = None,
    limit: int = Query(10, ge=10),
):
    """列出任务结果"""
    executor = get_task_executor()

    if task_id:
        result = executor.get_result(task_id)
        results = [result] if result else []
    else:
        results = executor.get_all_results()

    return {"results": results[:limit], "total": len(results)}


@router.post("/start")
async def start_heartbeat():
    """启动 Heartbeat 调度器"""
    scheduler = get_heartbeat_scheduler()

    if scheduler._is_running:
        return {"success": False, "message": "Heartbeat scheduler already running"}

    await scheduler.start()

    return {"success": True, "message": "Heartbeat scheduler started"}


@router.post("/stop")
async def stop_heartbeat():
    """停止 Heartbeat 调度器"""
    scheduler = get_heartbeat_scheduler()

    if not scheduler._is_running:
        return {"success": False, "message": "Heartbeat scheduler not running"}

    await scheduler.stop()

    return {"success": True, "message": "Heartbeat scheduler stopped"}
