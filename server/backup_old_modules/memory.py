"""
记忆管理 API
提供记忆的提取、检索、管理接口
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import logging

from memory.memory_service import get_memory_service

logger = logging.getLogger(__name__)

router = APIRouter()


class ExtractRequest(BaseModel):
    """提取请求"""
    message: str = Field(..., description="消息内容")
    role: str = Field(default="user", description="角色")
    user_id: str = Field(default="default", description="用户 ID")


class RecallRequest(BaseModel):
    """回忆请求"""
    query: str = Field(..., description="查询文本")
    user_id: str = Field(default="default", description="用户 ID")
    top_k: int = Field(default=5, description="返回数量")
    memory_type: Optional[str] = Field(default=None, description="记忆类型")


class MemoryResponse(BaseModel):
    """记忆响应"""
    id: str
    content: str
    type: str
    importance: float
    created_at: str
    access_count: int = 0
    relevance: Optional[float] = None


@router.post("/extract")
async def extract_memory(request: ExtractRequest):
    """
    从消息中提取记忆

    自动识别用户消息中的重要信息并存储
    """
    try:
        service = get_memory_service()
        memories = service.extract_and_store(
            message=request.message,
            role=request.role,
            user_id=request.user_id
        )

        logger.info(f"提取记忆: {len(memories)} 条")

        return {
            "success": True,
            "extracted": len(memories),
            "memories": memories
        }
    except Exception as e:
        logger.error(f"提取记忆失败: {e}")
        raise HTTPException(500, f"提取失败: {str(e)}")


@router.post("/recall")
async def recall_memory(request: RecallRequest):
    """
    检索相关记忆
    根据查询文本返回相关的记忆
    """
    try:
        service = get_memory_service()
        memories = service.recall(
            query=request.query,
            user_id=request.user_id,
            top_k=request.top_k,
            memory_type=request.memory_type
        )

        return {
            "success": True,
            "memories": memories,
            "count": len(memories)
        }
    except Exception as e:
        logger.error(f"检索记忆失败: {e}")
        raise HTTPException(500, f"检索失败: {str(e)}")


@router.get("/list")
async def list_memories(
    user_id: str = Query(default="default"),
    memory_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50)
):
    """
    列出所有记忆
    支持按类型过滤
    """
    try:
        service = get_memory_service()
        memories = service.list_memories(
            user_id=user_id,
            memory_type=memory_type,
            limit=limit
        )

        return {
            "success": True,
            "count": len(memories),
            "memories": memories
        }
    except Exception as e:
        logger.error(f"列出记忆失败: {e}")
        raise HTTPException(500, f"获取失败: {str(e)}")


@router.delete("/{memory_id}")
async def forget_memory(
    memory_id: str,
    user_id: str = Query(default="default")
):
    """
    删除记忆

    用户主动遗忘某条记忆
    """
    try:
        service = get_memory_service()
        success = service.forget(user_id, memory_id)

        if success:
            return {"success": True, "message": "记忆已删除"}
        else:
            raise HTTPException(404, "记忆不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除记忆失败: {e}")
        raise HTTPException(500, f"删除失败: {str(e)}")


@router.delete("/clear/all")
async def clear_all_memories(
    user_id: str = Query(default="default")
):
    """
    清除所有记忆
    谨慎使用！
    """
    try:
        service = get_memory_service()
        success = service.clear_all(user_id)

        if success:
            return {"success": True, "message": "所有记忆已清除"}
        else:
            raise HTTPException(500, "清除失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"清除记忆失败: {e}")
        raise HTTPException(500, f"清除失败: {str(e)}")


@router.get("/summary")
async def get_summary(user_id: str = Query(default="default")):
    """
    获取用户记忆摘要

    返回记忆统计和分类信息
    """
    try:
        service = get_memory_service()
        summary = service.get_user_summary(user_id)

        return {
            "success": True,
            "summary": summary
        }
    except Exception as e:
        logger.error(f"获取摘要失败: {e}")
        raise HTTPException(500, f"获取摘要失败: {str(e)}")


@router.get("/context")
async def get_context(
    query: str = Query(..., description="查询文本"),
    user_id: str = Query(default="default"),
    max_memories: int = Query(default=5)
):
    """
    获取带记忆的上下文
    用于注入到聊天提示中
    """
    try:
        service = get_memory_service()
        context = service.get_context_with_memory(
            query=query,
            user_id=user_id,
            max_memories=max_memories
        )

        return {
            "success": True,
            "context": context
        }
    except Exception as e:
        logger.error(f"获取上下文失败: {e}")
        raise HTTPException(500, f"获取上下文失败: {str(e)}")


@router.get("/stats")
async def get_stats(user_id: str = Query(default="default")):
    """
    获取记忆统计信息
    """
    try:
        service = get_memory_service()
        stats = service.get_stats(user_id)

        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        raise HTTPException(500, f"获取统计失败: {str(e)}")
