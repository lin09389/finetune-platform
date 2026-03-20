"""
对话上下文管�?API

提供对话上下文管理的 HTTP 接口�?- 上下文窗口配�?- 消息添加与管�?- 对话压缩
- 统计信息
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from context.manager import (
    get_context_manager,
    remove_context_manager,
    list_context_managers,
    ContextManager,
    MessageRole,
    MessagePriority
)
from context.compressor import get_dialog_compressor, CompressionResult

logger = logging.getLogger(__name__)

router = APIRouter(tags=["对话上下文管�?])


class AddMessageRequest(BaseModel):
    """添加消息请求"""
    session_id: str = Field(default="default", description="会话 ID")
    role: str = Field(..., description="消息角色: user/assistant/system")
    content: str = Field(..., description="消息内容")
    priority: str = Field(default="normal", description="优先�? critical/high/normal/low")
    importance: Optional[float] = Field(None, ge=0, le=1, description="重要性分�?)
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数�?)


class MessageResponse(BaseModel):
    """消息响应"""
    id: str
    role: str
    content: str
    timestamp: str
    priority: str
    token_count: int
    importance: float
    metadata: Dict[str, Any]


class SetSystemMessageRequest(BaseModel):
    """设置系统消息请求"""
    session_id: str = Field(default="default", description="会话 ID")
    content: str = Field(..., description="系统消息内容")


class SetMaxTokensRequest(BaseModel):
    """设置最�?Token 数请�?""
    session_id: str = Field(default="default", description="会话 ID")
    max_tokens: int = Field(..., ge=256, le=128000, description="最�?Token �?)


class CompressRequest(BaseModel):
    """压缩请求"""
    session_id: str = Field(default="default", description="会话 ID")
    strategy: str = Field(default="summary", description="压缩策略: summary/sliding_window/semantic/importance")
    target_ratio: float = Field(default=0.5, ge=0.1, le=0.9, description="目标压缩比例")


class CompressResponse(BaseModel):
    """压缩响应"""
    success: bool
    result: Optional[Dict[str, Any]] = None
    message: str = ""


class GetContextRequest(BaseModel):
    """获取上下文请�?""
    session_id: str = Field(default="default", description="会话 ID")
    include_system: bool = Field(default=True, description="是否包含系统消息")
    max_messages: Optional[int] = Field(None, ge=1, description="最大消息数")


class GetContextStringRequest(BaseModel):
    """获取上下文字符串请求"""
    session_id: str = Field(default="default", description="会话 ID")
    format_type: str = Field(default="default", description="格式类型: default/markdown/openai")
    max_messages: Optional[int] = Field(None, ge=1, description="最大消息数")


class ClearContextRequest(BaseModel):
    """清空上下文请�?""
    session_id: str = Field(default="default", description="会话 ID")
    keep_system: bool = Field(default=True, description="是否保留系统消息")


class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    session_id: str = Field(..., description="会话 ID")
    max_tokens: int = Field(default=4096, description="最�?Token �?)
    reserved_tokens: int = Field(default=512, description="保留 Token �?)
    compression_threshold: float = Field(default=0.8, ge=0.5, le=1.0, description="压缩阈�?)
    target_utilization: float = Field(default=0.6, ge=0.3, le=0.9, description="目标利用�?)


@router.post("/message", response_model=MessageResponse)
async def add_message(request: AddMessageRequest):
    """
    添加消息到上下文
    
    - 自动计算 Token �?    - 自动评估重要�?    - 超过阈值自动触发压�?    """
    try:
        manager = get_context_manager(request.session_id)
        
        role = MessageRole(request.role)
        
        priority_map = {
            "critical": MessagePriority.CRITICAL,
            "high": MessagePriority.HIGH,
            "normal": MessagePriority.NORMAL,
            "low": MessagePriority.LOW
        }
        priority = priority_map.get(request.priority, MessagePriority.NORMAL)
        
        message = manager.add_message(
            role=role,
            content=request.content,
            priority=priority,
            importance=request.importance,
            metadata=request.metadata
        )
        
        return MessageResponse(
            id=message.id,
            role=message.role.value,
            content=message.content,
            timestamp=message.timestamp.isoformat(),
            priority=message.priority.value,
            token_count=message.token_count,
            importance=message.importance,
            metadata=message.metadata
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"参数错误: {str(e)}")
    except Exception as e:
        logger.error(f"添加消息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"添加失败: {str(e)}")


@router.post("/system-message")
async def set_system_message(request: SetSystemMessageRequest):
    """
    设置系统消息
    
    - 系统消息具有最高优先级
    - 不会被压缩删�?    """
    try:
        manager = get_context_manager(request.session_id)
        
        message = manager.add_message(
            role=MessageRole.SYSTEM,
            content=request.content
        )
        
        return {
            "success": True,
            "message": "系统消息已设�?,
            "token_count": message.token_count
        }
    except Exception as e:
        logger.error(f"设置系统消息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"设置失败: {str(e)}")


@router.post("/compress", response_model=CompressResponse)
async def compress_context(request: CompressRequest):
    """
    手动压缩上下�?    
    支持多种压缩策略�?    - summary: 生成摘要替换旧消�?    - sliding_window: 滑动窗口保留首尾
    - semantic: 语义重要性压�?    - importance: 基于重要性分数压�?    """
    try:
        manager = get_context_manager(request.session_id)
        compressor = get_dialog_compressor()
        
        compressed, result = compressor.compress(
            messages=manager.messages,
            strategy=request.strategy,
            target_ratio=request.target_ratio
        )
        
        manager.messages = compressed
        manager.window.current_tokens = sum(m.token_count for m in compressed)
        
        return CompressResponse(
            success=True,
            result=result.to_dict(),
            message=f"压缩完成: {result.original_count} -> {result.compressed_count} 条消�?
        )
    except Exception as e:
        logger.error(f"压缩失败: {e}", exc_info=True)
        return CompressResponse(
            success=False,
            message=f"压缩失败: {str(e)}"
        )


@router.post("/context")
async def get_context(request: GetContextRequest):
    """
    获取上下文消息列�?    
    返回格式化的消息列表，可用于构建 LLM 输入
    """
    try:
        manager = get_context_manager(request.session_id)
        
        context = manager.get_context(
            include_system=request.include_system,
            max_messages=request.max_messages
        )
        
        return {
            "success": True,
            "session_id": request.session_id,
            "messages": context,
            "stats": manager.get_stats()
        }
    except Exception as e:
        logger.error(f"获取上下文失�? {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.post("/context/string")
async def get_context_string(request: GetContextStringRequest):
    """
    获取上下文字符串
    
    支持多种格式�?    - default: [Role]: content 格式
    - markdown: ## Role 格式
    - openai: OpenAI 消息格式
    """
    try:
        manager = get_context_manager(request.session_id)
        
        context_string = manager.get_context_string(
            format_type=request.format_type,
            max_messages=request.max_messages
        )
        
        return {
            "success": True,
            "session_id": request.session_id,
            "context": context_string,
            "stats": manager.get_stats()
        }
    except Exception as e:
        logger.error(f"获取上下文字符串失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.post("/clear")
async def clear_context(request: ClearContextRequest):
    """
    清空上下�?    
    可选择是否保留系统消息
    """
    try:
        manager = get_context_manager(request.session_id)
        manager.clear(keep_system=request.keep_system)
        
        return {
            "success": True,
            "message": "上下文已清空",
            "keep_system": request.keep_system
        }
    except Exception as e:
        logger.error(f"清空失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"清空失败: {str(e)}")


@router.get("/stats/{session_id}")
async def get_stats(session_id: str = "default"):
    """
    获取上下文统计信�?    
    包括�?    - 消息数量
    - Token 使用情况
    - 利用�?    - 各角色消息分�?    """
    try:
        manager = get_context_manager(session_id)
        stats = manager.get_stats()
        
        return {
            "success": True,
            "session_id": session_id,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"获取统计失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.post("/max-tokens")
async def set_max_tokens(request: SetMaxTokensRequest):
    """
    动态调整上下文窗口大小
    
    调整后如超过阈值会自动触发压缩
    """
    try:
        manager = get_context_manager(request.session_id)
        manager.set_max_tokens(request.max_tokens)
        
        return {
            "success": True,
            "message": f"上下文窗口已调整�?{request.max_tokens} tokens",
            "stats": manager.get_stats()
        }
    except Exception as e:
        logger.error(f"调整失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"调整失败: {str(e)}")


@router.post("/session")
async def create_session(request: CreateSessionRequest):
    """
    创建新的上下文会�?    
    可自定义各项参数
    """
    try:
        manager = get_context_manager(
            session_id=request.session_id,
            max_tokens=request.max_tokens,
            reserved_tokens=request.reserved_tokens,
            compression_threshold=request.compression_threshold,
            target_utilization=request.target_utilization
        )
        
        return {
            "success": True,
            "session_id": request.session_id,
            "message": "会话已创�?,
            "config": {
                "max_tokens": request.max_tokens,
                "reserved_tokens": request.reserved_tokens,
                "compression_threshold": request.compression_threshold,
                "target_utilization": request.target_utilization
            }
        }
    except Exception as e:
        logger.error(f"创建会话失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """
    删除上下文会�?    
    释放相关资源
    """
    try:
        success = remove_context_manager(session_id)
        
        if success:
            return {
                "success": True,
                "message": f"会话 {session_id} 已删�?
            }
        else:
            return {
                "success": False,
                "message": f"会话 {session_id} 不存�?
            }
    except Exception as e:
        logger.error(f"删除会话失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.get("/sessions")
async def list_sessions():
    """
    列出所有上下文会话
    """
    try:
        sessions = list_context_managers()
        
        session_stats = []
        for session_id in sessions:
            manager = get_context_manager(session_id)
            session_stats.append({
                "session_id": session_id,
                "stats": manager.get_stats()
            })
        
        return {
            "success": True,
            "total": len(sessions),
            "sessions": session_stats
        }
    except Exception as e:
        logger.error(f"列出会话失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.get("/messages/{session_id}")
async def get_messages(
    session_id: str,
    role: Optional[str] = None,
    recent: Optional[int] = None,
    keyword: Optional[str] = None
):
    """
    查询消息
    
    支持按角色、数量、关键词过滤
    """
    try:
        manager = get_context_manager(session_id)
        
        if keyword:
            messages = manager.find_messages(keyword)
        elif role:
            messages = manager.get_messages_by_role(MessageRole(role))
        elif recent:
            messages = manager.get_recent_messages(recent)
        else:
            messages = manager.messages
        
        return {
            "success": True,
            "session_id": session_id,
            "count": len(messages),
            "messages": [m.to_dict() for m in messages]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"参数错误: {str(e)}")
    except Exception as e:
        logger.error(f"查询消息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")
