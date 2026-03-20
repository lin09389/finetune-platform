"""
Heartbeat API 路由

提供 Heartbeat 模块�?REST API 皯点
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from heartbeat import (
    HeartbeatScheduler,
    HeartbeatTask,
    HeartbeatConfig,
    get_heartbeat_scheduler,
)
from heartbeat.task_executor import (
    TaskExecutor,
    TaskType,
    TaskStatus,
    ProactiveTask,
    TaskResult,
    get_task_executor,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/heartbeat", tags=["Heartbeat"])


class TaskCreateRequest(BaseModel):
    """任务创建请求"""
    name: str
    description: str = ""
    schedule: str
    task_type: str = "check"
    enabled: bool = True
    config: Dict[str, Any] = Field(default_factory=dict)


class TaskResponse(BaseModel):
    """任务响应"""
    id: str
    name: str
    description: str
    schedule: str
    task_type: str
    enabled: bool
    config: Dict[str, Any]
    status: Optional[str] = None
    last_run: Optional[datetime] = None


@router.get("/status")
async def get_heartbeat_status():
    """获取 Heartbeat 状�?""
    scheduler = get_heartbeat_scheduler()
    executor = get_task_executor()
    
    return {
        "scheduler": scheduler.get_stats(),
        "executor": executor.get_stats(),
    }


@router.get("/tasks")
async def list_tasks():
    """列出所有任�?""
    scheduler = get_heartbeat_scheduler()
    
    tasks = []
    for task_id, task in scheduler._tasks.items():
        tasks.append({
            "id": task.id,
            "name": task.name,
            "description": task.description,
            "schedule": task.schedule,
            "enabled": task.enabled,
        })
    
    return {"tasks": tasks, "total": len(tasks)}


@router.post("/tasks")
async def create_task(request: TaskCreateRequest):
    """创建新任�?""
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
    
    return {"success": True, "task_id": task.id}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """获取任务详情"""
    scheduler = get_heartbeat_scheduler()
    
    task = scheduler._tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {
        "id": task.id,
        "name": task.name,
        "description": task.description,
        "schedule": task.schedule,
        "enabled": task.enabled,
    }


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """删除任务"""
    scheduler = get_heartbeat_scheduler()
    
    scheduler.remove_task(task_id)
    
    return {"success": True, "task_id": task_id}


@router.post("/tasks/{task_id}/enable")
async def enable_task(task_id: str):
    """启用任务"""
    scheduler = get_heartbeat_scheduler()
    
    scheduler.enable_task(task_id)
    
    return {"success": True, "task_id": task_id}


@router.post("/tasks/{task_id}/disable")
async def disable_task(task_id: str):
    """禁用任务"""
    scheduler = get_heartbeat_scheduler()
    
    scheduler.disable_task(task_id)
    
    return {"success": True, "task_id": task_id}


@router.get("/results")
async def list_results(
    task_id: Optional[str] = None,
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
    """启动 Heartbeat 调度�?""
    scheduler = get_heartbeat_scheduler()
    
    if scheduler._running:
        return {"success": False, "message": "Heartbeat scheduler already running"}
    
    await scheduler.start()
    
    return {"success": True, "message": "Heartbeat scheduler started"}


@router.post("/stop")
async def stop_heartbeat():
    """停止 Heartbeat 调度�?""
    scheduler = get_heartbeat_scheduler()
    
    if not scheduler._running:
        return {"success": False, "message": "Heartbeat scheduler not running"}
    
    await scheduler.stop()
    
    return {"success": True, "message": "Heartbeat scheduler stopped"}
