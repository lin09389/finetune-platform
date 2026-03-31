"""
Agent 执行器 API 路由
集成重构后的 Agent 操作处理器
"""
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from agent.core import (
    OperationContext,
    UnifiedExecutor,
    create_executor,
    get_executor,
)
from agent.core.executor import ExecutorConfig

AgentExecutorNew = UnifiedExecutor
from core.feature_flags import get_flags

router = APIRouter(prefix="/agent-executor", tags=["Agent Executor"])


class ExecuteRequest(BaseModel):
    """执行请求"""
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    workspace: str | None = None


class BatchExecuteRequest(BaseModel):
    """批量执行请求"""
    operations: list[dict[str, Any]]
    workspace: str | None = None


@router.get("/actions")
async def list_actions():
    """列出支持的操作"""
    flags = get_flags()

    if flags.use_new_agent_executor:
        executor = get_executor()
        return {
            "actions": executor.get_supported_actions(),
            "count": len(executor.get_supported_actions()),
            "executor": "refactored",
        }
    else:
        return {
            "actions": ["legacy_mode"],
            "count": 1,
            "executor": "legacy",
            "message": "Set FEATURE_NEW_AGENT=true to use refactored executor",
        }


@router.post("/execute")
async def execute_action(request: ExecuteRequest):
    """执行操作"""
    flags = get_flags()

    if not flags.use_new_agent_executor:
        raise HTTPException(
            status_code=400,
            detail="Refactored executor not enabled. Set FEATURE_NEW_AGENT=true"
        )

    executor = get_executor()

    if request.workspace:
        context = OperationContext(workspace=request.workspace)
        executor.set_context(context)

    result = await executor.execute(request.action, request.params)

    return result.to_dict()


@router.post("/execute/batch")
async def execute_batch(request: BatchExecuteRequest):
    """批量执行操作"""
    flags = get_flags()

    if not flags.use_new_agent_executor:
        raise HTTPException(
            status_code=400,
            detail="Refactored executor not enabled. Set FEATURE_NEW_AGENT=true"
        )

    executor = get_executor()

    if request.workspace:
        context = OperationContext(workspace=request.workspace)
        executor.set_context(context)

    results = await executor.execute_batch(request.operations)

    return {
        "results": [r.to_dict() for r in results],
        "total": len(results),
    }


@router.get("/handlers")
async def list_handlers():
    """列出操作处理器"""
    flags = get_flags()

    if not flags.use_new_agent_executor:
        raise HTTPException(
            status_code=400,
            detail="Refactored executor not enabled. Set FEATURE_NEW_AGENT=true"
        )

    executor = get_executor()

    handlers = []
    for handler in executor._composite_handler._handlers:
        handlers.append({
            "class": handler.__class__.__name__,
            "actions": handler.get_supported_actions(),
        })

    return {
        "handlers": handlers,
        "count": len(handlers),
    }


@router.get("/stats")
async def get_executor_stats():
    """获取执行器统计"""
    flags = get_flags()

    if not flags.use_new_agent_executor:
        return {
            "executor": "legacy",
            "enabled": False,
        }

    executor = get_executor()
    return {
        "executor": "refactored",
        "enabled": True,
        **executor.get_stats(),
    }


@router.get("/audit-log")
async def get_audit_log(limit: int = Query(default=100, ge=1, le=1000)):
    """获取审计日志"""
    flags = get_flags()

    if not flags.use_new_agent_executor:
        raise HTTPException(
            status_code=400,
            detail="Refactored executor not enabled. Set FEATURE_NEW_AGENT=true"
        )

    executor = get_executor()

    return {
        "logs": executor.get_audit_log(limit),
        "count": len(executor.get_audit_log(limit)),
    }
