"""
对话模块路由 - 整合会话管理、历史记录、上下文管理
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from api.types import (
    SessionInfo, CreateSessionRequest, UpdateSessionRequest,
    SessionMessage, KnowledgeSource
)
from api.errors import SessionNotFoundError, InvalidInputError
from api.chat.session import get_session_store, SessionStatus
from api.chat.context import get_context_manager, MessagePriority

logger = logging.getLogger(__name__)

router = APIRouter()


class AddMessageRequest(BaseModel):
    """添加消息请求"""
    role: str = Field(..., description="消息角色: user/assistant/system")
    content: str = Field(..., description="消息内容")
    priority: str = Field(default="normal", description="优先�? critical/high/normal/low")
    importance: Optional[float] = Field(None, ge=0, le=1, description="重要性分�?)
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数�?)


class MessageBatchRequest(BaseModel):
    """批量消息请求"""
    messages: List[Dict[str, Any]] = Field(..., description="消息列表")


class CompressRequest(BaseModel):
    """压缩请求"""
    strategy: str = Field(default="summary", description="压缩策略: summary/sliding_window/semantic/importance")
    target_ratio: float = Field(default=0.5, ge=0.1, le=0.9, description="目标压缩比例")


class SearchRequest(BaseModel):
    """搜索请求"""
    query: Optional[str] = Field(None, description="搜索关键�?)
    tags: Optional[List[str]] = Field(None, description="标签过滤")
    status: Optional[str] = Field(None, description="状态过�?)
    starred: Optional[bool] = Field(None, description="星标过滤")
    pinned: Optional[bool] = Field(None, description="置顶过滤")
    model_id: Optional[str] = Field(None, description="模型 ID 过滤")
    start_date: Optional[str] = Field(None, description="开始日�?)
    end_date: Optional[str] = Field(None, description="结束日期")
    limit: int = Field(default=50, ge=1, le=200, description="返回数量限制")
    offset: int = Field(default=0, ge=0, description="偏移�?)


class SessionListResponse(BaseModel):
    """会话列表响应"""
    sessions: List[SessionInfo]
    total: int
    limit: int
    offset: int


class MessageResponse(BaseModel):
    """消息响应"""
    id: str
    session_id: str
    role: str
    content: str
    timestamp: str
    token_count: int = 0
    importance: float = 0.5
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SessionDetailResponse(BaseModel):
    """会话详情响应"""
    id: str
    title: Optional[str]
    description: str = ""
    model_id: str = ""
    tags: List[str] = Field(default_factory=list)
    status: str = "active"
    starred: bool = False
    pinned: bool = False
    custom_data: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    message_count: int = 0
    total_tokens: int = 0
    messages: List[Dict[str, Any]] = Field(default_factory=list)


class ContextStatsResponse(BaseModel):
    """上下文统计响�?""
    session_id: str
    message_count: int
    total_tokens: int
    max_tokens: int
    utilization: float
    roles: Dict[str, int]


class CompressResponse(BaseModel):
    """压缩响应"""
    success: bool
    result: Optional[Dict[str, Any]] = None
    message: str = ""


@router.post("", response_model=SessionInfo)
async def create_session(data: CreateSessionRequest):
    """创建新会�?""
    store = get_session_store()
    session = store.create_session(
        title=data.title,
        model_id=data.metadata.get("model_id", ""),
        description=data.metadata.get("description", ""),
        tags=data.metadata.get("tags", []),
        custom_data=data.metadata
    )
    logger.info(f"创建会话: {session.id}")
    return SessionInfo(
        id=session.id,
        title=session.metadata.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=0,
        metadata=session.metadata.custom_data
    )


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    query: Optional[str] = Query(None, description="搜索关键�?),
    tags: Optional[str] = Query(None, description="标签过滤（逗号分隔�?),
    status: Optional[str] = Query(None, description="状态过�?),
    starred: Optional[bool] = Query(None, description="星标过滤"),
    pinned: Optional[bool] = Query(None, description="置顶过滤"),
    model_id: Optional[str] = Query(None, description="模型 ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """获取会话列表"""
    store = get_session_store()
    
    tag_list = tags.split(",") if tags else None
    status_enum = SessionStatus(status) if status else None
    
    sessions, total = store.search_sessions(
        query=query,
        tags=tag_list,
        status=status_enum,
        starred=starred,
        pinned=pinned,
        model_id=model_id,
        limit=limit,
        offset=offset
    )
    
    return SessionListResponse(
        sessions=[
            SessionInfo(
                id=s.id,
                title=s.metadata.title,
                created_at=s.created_at,
                updated_at=s.updated_at,
                message_count=s.message_count,
                metadata=s.metadata.custom_data,
                tags=s.metadata.tags,
                starred=s.metadata.starred,
                pinned=s.metadata.pinned
            )
            for s in sessions
        ],
        total=total,
        limit=limit,
        offset=offset
    )


@router.post("/search", response_model=SessionListResponse)
async def search_sessions(data: SearchRequest):
    """搜索会话（POST 方式�?""
    store = get_session_store()
    
    status_enum = SessionStatus(data.status) if data.status else None
    
    sessions, total = store.search_sessions(
        query=data.query,
        tags=data.tags,
        status=status_enum,
        starred=data.starred,
        pinned=data.pinned,
        model_id=data.model_id,
        start_date=data.start_date,
        end_date=data.end_date,
        limit=data.limit,
        offset=data.offset
    )
    
    return SessionListResponse(
        sessions=[
            SessionInfo(
                id=s.id,
                title=s.metadata.title,
                created_at=s.created_at,
                updated_at=s.updated_at,
                message_count=s.message_count,
                metadata=s.metadata.custom_data,
                tags=s.metadata.tags,
                starred=s.metadata.starred,
                pinned=s.metadata.pinned
            )
            for s in sessions
        ],
        total=total,
        limit=data.limit,
        offset=data.offset
    )


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(session_id: str):
    """获取会话详情"""
    store = get_session_store()
    session = store.get_session(session_id, include_messages=True)
    
    if not session:
        raise SessionNotFoundError(session_id)
    
    return SessionDetailResponse(
        id=session.id,
        title=session.metadata.title,
        description=session.metadata.description,
        model_id=session.metadata.model_id,
        tags=session.metadata.tags,
        status=session.metadata.status.value if hasattr(session.metadata.status, 'value') else session.metadata.status,
        starred=session.metadata.starred,
        pinned=session.metadata.pinned,
        custom_data=session.metadata.custom_data,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=session.message_count,
        total_tokens=session.total_tokens,
        messages=[msg.to_dict() for msg in session.messages]
    )


@router.put("/{session_id}")
async def update_session(session_id: str, data: UpdateSessionRequest):
    """更新会话元数�?""
    store = get_session_store()
    
    status_enum = SessionStatus(data.status) if data.status else None
    
    success = store.update_session(
        session_id=session_id,
        title=data.title,
        description=data.metadata.get("description") if data.metadata else None,
        model_id=data.metadata.get("model_id") if data.metadata else None,
        tags=data.tags,
        status=status_enum,
        starred=data.starred,
        pinned=data.pinned,
        custom_data=data.metadata
    )
    
    if not success:
        raise SessionNotFoundError(session_id)
    
    session = store.get_session(session_id, include_messages=False)
    logger.info(f"更新会话: {session_id}")
    
    return SessionInfo(
        id=session.id,
        title=session.metadata.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=session.message_count,
        metadata=session.metadata.custom_data,
        tags=session.metadata.tags,
        starred=session.metadata.starred,
        pinned=session.metadata.pinned
    )


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    permanent: bool = Query(False, description="是否永久删除")
):
    """删除会话"""
    store = get_session_store()
    success = store.delete_session(session_id, soft_delete=not permanent)
    
    if not success:
        raise SessionNotFoundError(session_id)
    
    logger.info(f"{'永久' if permanent else '�?}删除会话: {session_id}")
    return {"message": "会话已删�?, "permanent": permanent}


@router.post("/{session_id}/restore")
async def restore_session(session_id: str):
    """恢复已删除的会话"""
    store = get_session_store()
    session = store.restore_session(session_id)
    
    if not session:
        raise SessionNotFoundError(session_id)
    
    logger.info(f"恢复会话: {session_id}")
    return SessionInfo(
        id=session.id,
        title=session.metadata.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=session.message_count,
        metadata=session.metadata.custom_data
    )


@router.post("/{session_id}/archive")
async def archive_session(session_id: str):
    """归档会话"""
    store = get_session_store()
    success = store.archive_session(session_id)
    
    if not success:
        raise SessionNotFoundError(session_id)
    
    session = store.get_session(session_id, include_messages=False)
    logger.info(f"归档会话: {session_id}")
    return {"message": "会话已归�?, "session_id": session_id}


@router.post("/{session_id}/star")
async def toggle_star(session_id: str, starred: bool = Query(..., description="是否星标")):
    """设置会话星标"""
    store = get_session_store()
    success = store.update_session(session_id, starred=starred)
    
    if not success:
        raise SessionNotFoundError(session_id)
    
    return {"message": "星标状态已更新", "starred": starred}


@router.post("/{session_id}/pin")
async def toggle_pin(session_id: str, pinned: bool = Query(..., description="是否置顶")):
    """设置会话置顶"""
    store = get_session_store()
    success = store.update_session(session_id, pinned=pinned)
    
    if not success:
        raise SessionNotFoundError(session_id)
    
    return {"message": "置顶状态已更新", "pinned": pinned}


@router.post("/{session_id}/messages", response_model=MessageResponse)
async def add_message(session_id: str, data: AddMessageRequest):
    """添加消息到会�?""
    store = get_session_store()
    
    try:
        from api.chat.context import MessageRole
        role = MessageRole(data.role)
    except ValueError:
        raise InvalidInputError("role", f"无效的消息角�? {data.role}")
    
    message = store.add_message(
        session_id=session_id,
        role=role,
        content=data.content,
        importance=data.importance or 0.5,
        metadata=data.metadata or {}
    )
    
    if not message:
        raise SessionNotFoundError(session_id)
    
    logger.debug(f"添加消息到会�?{session_id}: {message.id}")
    return MessageResponse(
        id=message.id,
        session_id=session_id,
        role=message.role.value if hasattr(message.role, 'value') else message.role,
        content=message.content,
        timestamp=message.timestamp.isoformat() if hasattr(message.timestamp, 'isoformat') else str(message.timestamp),
        importance=message.importance,
        metadata=message.metadata
    )


@router.post("/{session_id}/messages/batch")
async def add_messages_batch(session_id: str, data: MessageBatchRequest):
    """批量添加消息到会�?""
    store = get_session_store()
    count = store.add_messages_batch(session_id, data.messages)
    
    if count == 0:
        raise SessionNotFoundError(session_id)
    
    logger.debug(f"批量添加 {count} 条消息到会话 {session_id}")
    return {"message": "消息已添�?, "count": count}


@router.post("/{session_id}/message")
async def add_message_legacy(session_id: str, data: MessageBatchRequest):
    """兼容旧版 API：批量添加消息到会话

    这是为了兼容前端�?/chat/session/{sessionId}/message 调用
    """
    store = get_session_store()
    count = store.add_messages_batch(session_id, data.messages)
    
    if count == 0:
        raise SessionNotFoundError(session_id)
    
    logger.debug(f"兼容 API：批量添�?{count} 条消息到会话 {session_id}")
    return {"message": "消息已添�?, "count": count}


@router.get("/{session_id}/messages", response_model=List[MessageResponse])
async def get_messages(
    session_id: str,
    limit: Optional[int] = Query(None, ge=1, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="偏移�?),
    roles: Optional[str] = Query(None, description="角色过滤（逗号分隔�?)
):
    """获取会话消息列表"""
    store = get_session_store()
    
    role_list = None
    if roles:
        try:
            from api.chat.context import MessageRole
            role_list = [MessageRole(r.strip()) for r in roles.split(",")]
        except ValueError as e:
            raise InvalidInputError("roles", f"无效的消息角�? {e}")
    
    messages = store.get_messages(
        session_id=session_id,
        limit=limit,
        offset=offset,
        roles=role_list
    )
    
    return [
        MessageResponse(
            id=msg.id,
            session_id=session_id,
            role=msg.role.value if hasattr(msg.role, 'value') else msg.role,
            content=msg.content,
            timestamp=msg.timestamp.isoformat() if hasattr(msg.timestamp, 'isoformat') else str(msg.timestamp),
            importance=msg.importance,
            metadata=msg.metadata
        )
        for msg in messages
    ]


@router.delete("/{session_id}/messages/{message_id}")
async def delete_message(session_id: str, message_id: str):
    """删除单条消息"""
    store = get_session_store()
    success = store.delete_message(session_id, message_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="消息不存�?)
    
    logger.debug(f"删除消息: {message_id}")
    return {"message": "消息已删�?}


@router.get("/{session_id}/export")
async def export_session(
    session_id: str,
    format: str = Query("json", description="导出格式: json/markdown")
):
    """导出会话"""
    store = get_session_store()
    exported = store.export_session(session_id, format=format)
    
    if not exported:
        raise SessionNotFoundError(session_id)
    
    return {
        "session_id": session_id,
        "format": format,
        "content": exported,
        "exported_at": datetime.now().isoformat()
    }


@router.get("/{session_id}/context/stats", response_model=ContextStatsResponse)
async def get_context_stats(session_id: str):
    """获取上下文统计信�?""
    manager = get_context_manager(session_id)
    stats = manager.get_stats()
    
    return ContextStatsResponse(
        session_id=session_id,
        message_count=stats.get("message_count", 0),
        total_tokens=stats.get("total_tokens", 0),
        max_tokens=stats.get("max_tokens", 4096),
        utilization=stats.get("utilization", 0),
        roles=stats.get("roles", {})
    )


@router.post("/{session_id}/context/compress", response_model=CompressResponse)
async def compress_context(session_id: str, data: CompressRequest):
    """手动压缩上下�?""
    try:
        manager = get_context_manager(session_id)
        
        from context.compressor import get_dialog_compressor
        compressor = get_dialog_compressor()
        
        compressed, result = compressor.compress(
            messages=manager.messages,
            strategy=data.strategy,
            target_ratio=data.target_ratio
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


@router.post("/{session_id}/context/clear")
async def clear_context(
    session_id: str,
    keep_system: bool = Query(True, description="是否保留系统消息")
):
    """清空上下�?""
    manager = get_context_manager(session_id)
    manager.clear(keep_system=keep_system)
    
    return {
        "message": "上下文已清空",
        "keep_system": keep_system
    }


@router.get("/tags/all")
async def get_all_tags():
    """获取所有标�?""
    store = get_session_store()
    tags = store.get_all_tags()
    return [{"tag": tag["tag"], "count": tag["count"]} for tag in tags]


@router.get("/stats/overview")
async def get_statistics():
    """获取会话统计信息"""
    store = get_session_store()
    stats = store.get_statistics()
    return stats
