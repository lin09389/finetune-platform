"""
任务追踪 API 端点
提供任务�?CRUD、分配、通知和进度追踪接�?"""
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from typing import List, Optional
import json
import asyncio

from workspace.models import (
    Task,
    TaskCreate,
    TaskUpdate,
    TaskStatus,
    TaskPriority,
    TaskNotification,
    TaskProgress,
    TaskStatistics,
)
from workspace.task_manager import get_task_manager
from core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/", response_model=Task, summary="创建任务")
async def create_task(
    data: TaskCreate,
    created_by: Optional[str] = Query(None, description="创建�?),
):
    """
    创建新任�?    
    - **title**: 任务标题（必填）
    - **description**: 任务描述
    - **project_id**: 所属项目ID
    - **priority**: 任务优先级（low/normal/high/urgent�?    - **due_date**: 截止日期（ISO格式�?    - **assignee**: 负责�?    - **tags**: 任务标签列表
    - **subtasks**: 子任务列�?    """
    try:
        manager = get_task_manager()
        task = manager.create_task(data, created_by=created_by)
        logger.info(f"任务已创建：{task.id}")
        return task
    except Exception as e:
        logger.error(f"创建任务失败：{e}")
        raise HTTPException(status_code=500, detail=f"创建任务失败：{str(e)}")


@router.get("/", response_model=List[Task], summary="获取任务列表")
async def list_tasks(
    project_id: Optional[str] = Query(None, description="项目ID筛�?),
    status: Optional[TaskStatus] = Query(None, description="状态筛�?),
    priority: Optional[TaskPriority] = Query(None, description="优先级筛�?),
    assignee: Optional[str] = Query(None, description="负责人筛�?),
    tags: Optional[str] = Query(None, description="标签筛选（逗号分隔�?),
    search: Optional[str] = Query(None, description="搜索关键�?),
    overdue: Optional[bool] = Query(None, description="是否逾期"),
):
    """
    获取任务列表
    
    支持多种筛选条件：
    - 按项目、状态、优先级、负责人筛�?    - 按标签筛选（多个标签用逗号分隔�?    - 搜索标题或描�?    - 筛选逾期任务
    """
    try:
        manager = get_task_manager()
        
        tag_list = tags.split(",") if tags else None
        
        tasks = manager.list_tasks(
            project_id=project_id,
            status=status,
            priority=priority,
            assignee=assignee,
            tags=tag_list,
            search=search,
            overdue=overdue,
        )
        
        return tasks
    except Exception as e:
        logger.error(f"获取任务列表失败：{e}")
        raise HTTPException(status_code=500, detail=f"获取任务列表失败：{str(e)}")


@router.get("/statistics", response_model=TaskStatistics, summary="获取任务统计")
async def get_task_statistics(
    project_id: Optional[str] = Query(None, description="项目ID筛�?),
):
    """
    获取任务统计信息
    
    返回�?    - 任务总数
    - 各状态任务数�?    - 逾期任务�?    - 高优先级任务�?    - 完成�?    """
    try:
        manager = get_task_manager()
        stats = manager.get_statistics(project_id=project_id)
        return stats
    except Exception as e:
        logger.error(f"获取任务统计失败：{e}")
        raise HTTPException(status_code=500, detail=f"获取任务统计失败：{str(e)}")


@router.get("/{task_id}", response_model=Task, summary="获取任务详情")
async def get_task(task_id: str):
    """
    获取指定任务的详细信�?    """
    try:
        manager = get_task_manager()
        task = manager.get_task(task_id)
        
        if not task:
            raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
        
        return task
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务详情失败：{e}")
        raise HTTPException(status_code=500, detail=f"获取任务详情失败：{str(e)}")


@router.put("/{task_id}", response_model=Task, summary="更新任务")
async def update_task(
    task_id: str,
    data: TaskUpdate,
):
    """
    更新任务信息
    
    可更新：
    - 标题、描�?    - 状态、优先级
    - 截止日期、负责人
    - 标签、子任务
    - 进度百分�?    """
    try:
        manager = get_task_manager()
        task = manager.update_task(task_id, data)
        
        if not task:
            raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
        
        logger.info(f"任务已更新：{task_id}")
        return task
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新任务失败：{e}")
        raise HTTPException(status_code=500, detail=f"更新任务失败：{str(e)}")


@router.delete("/{task_id}", summary="删除任务")
async def delete_task(
    task_id: str,
    hard: bool = Query(False, description="是否硬删除（物理删除�?),
):
    """
    删除任务
    
    - **hard=false**: 软删除（标记为已取消�?    - **hard=true**: 硬删除（物理删除�?    """
    try:
        manager = get_task_manager()
        success = manager.delete_task(task_id, hard=hard)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
        
        logger.info(f"任务已删除：{task_id}, 硬删除：{hard}")
        return {"message": "任务已删�?, "task_id": task_id, "hard_delete": hard}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除任务失败：{e}")
        raise HTTPException(status_code=500, detail=f"删除任务失败：{str(e)}")


@router.post("/{task_id}/assign", response_model=Task, summary="分配任务")
async def assign_task(
    task_id: str,
    assignee: str = Query(..., description="负责�?),
):
    """
    将任务分配给指定负责�?    
    会自动发送通知给负责人
    """
    try:
        manager = get_task_manager()
        task = manager.assign_task(task_id, assignee)
        
        if not task:
            raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
        
        logger.info(f"任务已分配：{task_id} -> {assignee}")
        return task
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"分配任务失败：{e}")
        raise HTTPException(status_code=500, detail=f"分配任务失败：{str(e)}")


@router.post("/{task_id}/progress", response_model=TaskProgress, summary="更新任务进度")
async def update_task_progress(
    task_id: str,
    progress: int = Query(..., ge=0, le=100, description="进度百分�?),
    message: Optional[str] = Query(None, description="进度消息"),
):
    """
    更新任务进度
    
    - **progress**: 进度百分比（0-100�?    - **message**: 进度消息（可选，会发送通知�?    
    当进度达�?00%时，自动将任务标记为完成
    """
    try:
        manager = get_task_manager()
        task_progress = manager.update_progress(task_id, progress, message)
        
        if not task_progress:
            raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
        
        logger.info(f"任务进度已更新：{task_id}, 进度：{progress}%")
        return task_progress
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新任务进度失败：{e}")
        raise HTTPException(status_code=500, detail=f"更新任务进度失败：{str(e)}")


@router.put("/{task_id}/subtasks/{subtask_id}", response_model=Task, summary="更新子任务状�?)
async def update_subtask(
    task_id: str,
    subtask_id: str,
    completed: bool = Query(..., description="是否完成"),
):
    """
    更新子任务完成状�?    
    会自动计算并更新父任务的进度百分�?    """
    try:
        manager = get_task_manager()
        task = manager.update_subtask(task_id, subtask_id, completed)
        
        if not task:
            raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
        
        logger.info(f"子任务已更新：{subtask_id}, 任务：{task_id}")
        return task
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新子任务失败：{e}")
        raise HTTPException(status_code=500, detail=f"更新子任务失败：{str(e)}")


@router.post("/{task_id}/start", response_model=Task, summary="开始任�?)
async def start_task(task_id: str):
    """
    将任务状态改�?进行�?
    
    会自动记录开始时间并发送通知
    """
    try:
        manager = get_task_manager()
        task = manager.update_task(task_id, TaskUpdate(status=TaskStatus.IN_PROGRESS))
        
        if not task:
            raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
        
        logger.info(f"任务已开始：{task_id}")
        return task
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"开始任务失败：{e}")
        raise HTTPException(status_code=500, detail=f"开始任务失败：{str(e)}")


@router.post("/{task_id}/complete", response_model=Task, summary="完成任务")
async def complete_task(task_id: str):
    """
    将任务状态改�?已完�?
    
    会自动记录完成时间、设置进度为100%并发送通知
    """
    try:
        manager = get_task_manager()
        task = manager.update_task(task_id, TaskUpdate(status=TaskStatus.COMPLETED))
        
        if not task:
            raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
        
        logger.info(f"任务已完成：{task_id}")
        return task
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"完成任务失败：{e}")
        raise HTTPException(status_code=500, detail=f"完成任务失败：{str(e)}")


@router.post("/{task_id}/cancel", response_model=Task, summary="取消任务")
async def cancel_task(task_id: str):
    """
    将任务状态改�?已取�?
    
    会发送通知给负责人
    """
    try:
        manager = get_task_manager()
        task = manager.update_task(task_id, TaskUpdate(status=TaskStatus.CANCELLED))
        
        if not task:
            raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
        
        logger.info(f"任务已取消：{task_id}")
        return task
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"取消任务失败：{e}")
        raise HTTPException(status_code=500, detail=f"取消任务失败：{str(e)}")


@router.get("/notifications/", response_model=List[TaskNotification], summary="获取通知列表")
async def get_notifications(
    recipient: Optional[str] = Query(None, description="接收者筛�?),
    unread_only: bool = Query(False, description="仅未读通知"),
    limit: int = Query(50, ge=1, le=200, description="返回数量限制"),
):
    """
    获取任务通知列表
    
    - **recipient**: 按接收者筛�?    - **unread_only**: 仅返回未读通知
    - **limit**: 返回数量限制（默�?0，最�?00�?    """
    try:
        manager = get_task_manager()
        notifications = manager.get_notifications(recipient, unread_only, limit)
        return notifications
    except Exception as e:
        logger.error(f"获取通知列表失败：{e}")
        raise HTTPException(status_code=500, detail=f"获取通知列表失败：{str(e)}")


@router.post("/notifications/{notification_id}/read", summary="标记通知为已�?)
async def mark_notification_read(notification_id: str):
    """
    标记指定通知为已�?    """
    try:
        manager = get_task_manager()
        success = manager.mark_notification_read(notification_id)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"通知不存在：{notification_id}")
        
        return {"message": "通知已标记为已读", "notification_id": notification_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"标记通知失败：{e}")
        raise HTTPException(status_code=500, detail=f"标记通知失败：{str(e)}")


@router.post("/notifications/read-all", summary="标记所有通知为已�?)
async def mark_all_notifications_read(
    recipient: Optional[str] = Query(None, description="接收�?),
):
    """
    标记所有通知为已�?    
    可指定接收者，不指定则标记所有通知
    """
    try:
        manager = get_task_manager()
        count = manager.mark_all_notifications_read(recipient)
        
        return {
            "message": f"已标�?{count} 条通知为已�?,
            "count": count,
            "recipient": recipient,
        }
    except Exception as e:
        logger.error(f"标记所有通知失败：{e}")
        raise HTTPException(status_code=500, detail=f"标记所有通知失败：{str(e)}")


@router.get("/notifications/stream", summary="实时通知�?)
async def notification_stream(
    recipient: Optional[str] = Query(None, description="接收�?),
):
    """
    实时通知流（Server-Sent Events�?    
    客户端可通过 EventSource 连接此端点接收实时通知
    """
    async def event_generator():
        manager = get_task_manager()
        notification_queue = asyncio.Queue()
        
        def on_notification(notification):
            asyncio.create_task(notification_queue.put(notification))
        
        manager.subscribe_notifications(recipient or 'all', on_notification)
        
        try:
            while True:
                notification = await asyncio.wait_for(
                    notification_queue.get(),
                    timeout=30.0
                )
                yield f"data: {notification.model_dump_json()}\n\n"
        except asyncio.TimeoutError:
            yield f": heartbeat\n\n"
        except Exception as e:
            logger.error(f"通知流错误：{e}")
            yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"
        finally:
            manager.unsubscribe_notifications(recipient or 'all', on_notification)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
