"""
会话管理 API

功能：
- 会话 CRUD 操作
- 会话元数据管理（标题、标签、时间）
- 会话搜索（按时间、标签）
- 会话恢复
- 会话导出
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from context.session_store import (
    get_session_store,
    SessionStore,
    SessionStatus,
    MessageRole,
    ChatSession,
    SessionMessage
)

logger = logging.getLogger(__name__)

router = APIRouter()


class SessionCreate(BaseModel):
    """创建会话请求"""
    title: str = Field(default="", description="会话标题")
    model_id: str = Field(default="", description="模型 ID")
    description: str = Field(default="", description="会话描述")
    tags: List[str] = Field(default_factory=list, description="标签列表")
    custom_data: Dict[str, Any] = Field(default_factory=dict, description="自定义数据")


class SessionUpdate(BaseModel):
    """更新会话请求"""
    title: Optional[str] = Field(None, description="会话标题")
    model_id: Optional[str] = Field(None, description="模型 ID")
    description: Optional[str] = Field(None, description="会话描述")
    tags: Optional[List[str]] = Field(None, description="标签列表")
    status: Optional[str] = Field(None, description="会话状态: active/archived")
    starred: Optional[bool] = Field(None, description="是否星标")
    pinned: Optional[bool] = Field(None, description="是否置顶")
    custom_data: Optional[Dict[str, Any]] = Field(None, description="自定义数据")


class MessageCreate(BaseModel):
    """创建消息请求"""
    role: str = Field(..., description="消息角色: user/assistant/system/function")
    content: str = Field(..., description="消息内容")
    token_count: int = Field(default=0, description="Token 数量")
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="重要性评分")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class MessageBatchCreate(BaseModel):
    """批量创建消息请求"""
    messages: List[Dict[str, Any]] = Field(..., description="消息列表")


class SessionSearch(BaseModel):
    """会话搜索请求"""
    query: Optional[str] = Field(None, description="搜索关键词")
    tags: Optional[List[str]] = Field(None, description="标签过滤")
    status: Optional[str] = Field(None, description="状态过滤")
    starred: Optional[bool] = Field(None, description="星标过滤")
    pinned: Optional[bool] = Field(None, description="置顶过滤")
    model_id: Optional[str] = Field(None, description="模型 ID 过滤")
    start_date: Optional[str] = Field(None, description="开始日期")
    end_date: Optional[str] = Field(None, description="结束日期")
    limit: int = Field(default=50, ge=1, le=200, description="返回数量限制")
    offset: int = Field(default=0, ge=0, description="偏移量")
    order_by: str = Field(default="updated_at", description="排序字段")
    order_desc: bool = Field(default=True, description="是否降序")


class SessionResponse(BaseModel):
    """会话响应"""
    id: str
    title: str
    description: str
    model_id: str
    tags: List[str]
    status: str
    starred: bool
    pinned: bool
    custom_data: Dict[str, Any]
    created_at: str
    updated_at: str
    message_count: int
    total_tokens: int


class SessionDetailResponse(BaseModel):
    """会话详情响应"""
    id: str
    title: str
    description: str
    model_id: str
    tags: List[str]
    status: str
    starred: bool
    pinned: bool
    custom_data: Dict[str, Any]
    created_at: str
    updated_at: str
    message_count: int
    total_tokens: int
    messages: List[Dict[str, Any]]


class MessageResponse(BaseModel):
    """消息响应"""
    id: str
    session_id: str
    role: str
    content: str
    timestamp: str
    token_count: int
    importance: float
    metadata: Dict[str, Any]


class SessionListResponse(BaseModel):
    """会话列表响应"""
    sessions: List[SessionResponse]
    total: int
    limit: int
    offset: int


class StatisticsResponse(BaseModel):
    """统计信息响应"""
    total_sessions: int
    active_sessions: int
    archived_sessions: int
    deleted_sessions: int
    total_messages: int
    total_tokens: int
    active_sessions_7d: int
    active_sessions_30d: int


class TagResponse(BaseModel):
    """标签响应"""
    tag: str
    count: int


def _session_to_response(session: ChatSession) -> SessionResponse:
    """将会话对象转换为响应模型"""
    return SessionResponse(
        id=session.id,
        title=session.metadata.title,
        description=session.metadata.description,
        model_id=session.metadata.model_id,
        tags=session.metadata.tags,
        status=session.metadata.status.value if isinstance(session.metadata.status, SessionStatus) else session.metadata.status,
        starred=session.metadata.starred,
        pinned=session.metadata.pinned,
        custom_data=session.metadata.custom_data,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=session.message_count,
        total_tokens=session.total_tokens
    )


def _session_to_detail_response(session: ChatSession) -> SessionDetailResponse:
    """将会话对象转换为详情响应模型"""
    return SessionDetailResponse(
        id=session.id,
        title=session.metadata.title,
        description=session.metadata.description,
        model_id=session.metadata.model_id,
        tags=session.metadata.tags,
        status=session.metadata.status.value if isinstance(session.metadata.status, SessionStatus) else session.metadata.status,
        starred=session.metadata.starred,
        pinned=session.metadata.pinned,
        custom_data=session.metadata.custom_data,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=session.message_count,
        total_tokens=session.total_tokens,
        messages=[msg.to_dict() for msg in session.messages]
    )


@router.post("", response_model=SessionResponse)
async def create_session(data: SessionCreate):
    """创建新会话"""
    store = get_session_store()
    session = store.create_session(
        title=data.title,
        model_id=data.model_id,
        description=data.description,
        tags=data.tags,
        custom_data=data.custom_data
    )
    logger.info(f"创建会话: {session.id}")
    return _session_to_response(session)


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    query: Optional[str] = Query(None, description="搜索关键词"),
    tags: Optional[str] = Query(None, description="标签过滤（逗号分隔）"),
    status: Optional[str] = Query(None, description="状态过滤"),
    starred: Optional[bool] = Query(None, description="星标过滤"),
    pinned: Optional[bool] = Query(None, description="置顶过滤"),
    model_id: Optional[str] = Query(None, description="模型 ID"),
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
    limit: int = Query(50, ge=1, le=200, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="偏移量"),
    order_by: str = Query("updated_at", description="排序字段"),
    order_desc: bool = Query(True, description="是否降序")
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
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
        order_by=order_by,
        order_desc=order_desc
    )

    return SessionListResponse(
        sessions=[_session_to_response(s) for s in sessions],
        total=total,
        limit=limit,
        offset=offset
    )


@router.post("/search", response_model=SessionListResponse)
async def search_sessions(data: SessionSearch):
    """搜索会话（POST 方式）"""
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
        offset=data.offset,
        order_by=data.order_by,
        order_desc=data.order_desc
    )

    return SessionListResponse(
        sessions=[_session_to_response(s) for s in sessions],
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
        raise HTTPException(status_code=404, detail="会话不存在")

    return _session_to_detail_response(session)


@router.put("/{session_id}", response_model=SessionResponse)
async def update_session(session_id: str, data: SessionUpdate):
    """更新会话元数据"""
    store = get_session_store()

    status_enum = SessionStatus(data.status) if data.status else None

    success = store.update_session(
        session_id=session_id,
        title=data.title,
        description=data.description,
        model_id=data.model_id,
        tags=data.tags,
        status=status_enum,
        starred=data.starred,
        pinned=data.pinned,
        custom_data=data.custom_data
    )

    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")

    session = store.get_session(session_id, include_messages=False)
    logger.info(f"更新会话: {session_id}")
    return _session_to_response(session)


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    permanent: bool = Query(False, description="是否永久删除")
):
    """删除会话"""
    store = get_session_store()
    success = store.delete_session(session_id, soft_delete=not permanent)

    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")

    logger.info(f"{'永久' if permanent else '软'}删除会话: {session_id}")
    return {"message": "会话已删除", "permanent": permanent}


@router.post("/{session_id}/restore", response_model=SessionResponse)
async def restore_session(session_id: str):
    """恢复已删除的会话"""
    store = get_session_store()
    session = store.restore_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或无法恢复")

    logger.info(f"恢复会话: {session_id}")
    return _session_to_response(session)


@router.post("/{session_id}/archive", response_model=SessionResponse)
async def archive_session(session_id: str):
    """归档会话"""
    store = get_session_store()
    success = store.archive_session(session_id)

    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")

    session = store.get_session(session_id, include_messages=False)
    logger.info(f"归档会话: {session_id}")
    return _session_to_response(session)


@router.post("/{session_id}/star", response_model=SessionResponse)
async def toggle_star(session_id: str, starred: bool = Query(..., description="是否星标")):
    """设置会话星标"""
    store = get_session_store()
    success = store.update_session(session_id, starred=starred)

    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")

    session = store.get_session(session_id, include_messages=False)
    return _session_to_response(session)


@router.post("/{session_id}/pin", response_model=SessionResponse)
async def toggle_pin(session_id: str, pinned: bool = Query(..., description="是否置顶")):
    """设置会话置顶"""
    store = get_session_store()
    success = store.update_session(session_id, pinned=pinned)

    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")

    session = store.get_session(session_id, include_messages=False)
    return _session_to_response(session)


@router.post("/{session_id}/messages", response_model=MessageResponse)
async def add_message(session_id: str, data: MessageCreate):
    """添加消息到会话"""
    store = get_session_store()

    try:
        role = MessageRole(data.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的消息角色: {data.role}")

    message = store.add_message(
        session_id=session_id,
        role=role,
        content=data.content,
        token_count=data.token_count,
        importance=data.importance,
        metadata=data.metadata
    )

    if not message:
        raise HTTPException(status_code=404, detail="会话不存在")

    logger.debug(f"添加消息到会话 {session_id}: {message.id}")
    return MessageResponse(**message.to_dict())


@router.post("/{session_id}/messages/batch")
async def add_messages_batch(session_id: str, data: MessageBatchCreate):
    """批量添加消息到会话"""
    store = get_session_store()
    count = store.add_messages_batch(session_id, data.messages)

    if count == 0:
        raise HTTPException(status_code=404, detail="会话不存在")

    logger.debug(f"批量添加 {count} 条消息到会话 {session_id}")
    return {"message": "消息已添加", "count": count}


@router.get("/{session_id}/messages", response_model=List[MessageResponse])
async def get_messages(
    session_id: str,
    limit: Optional[int] = Query(None, ge=1, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="偏移量"),
    roles: Optional[str] = Query(None, description="角色过滤（逗号分隔）")
):
    """获取会话消息列表"""
    store = get_session_store()

    role_list = None
    if roles:
        try:
            role_list = [MessageRole(r.strip()) for r in roles.split(",")]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"无效的消息角色: {e}")

    messages = store.get_messages(
        session_id=session_id,
        limit=limit,
        offset=offset,
        roles=role_list
    )

    return [MessageResponse(**msg.to_dict()) for msg in messages]


@router.delete("/{session_id}/messages/{message_id}")
async def delete_message(session_id: str, message_id: str):
    """删除单条消息"""
    store = get_session_store()
    success = store.delete_message(session_id, message_id)

    if not success:
        raise HTTPException(status_code=404, detail="消息不存在")

    logger.debug(f"删除消息: {message_id}")
    return {"message": "消息已删除"}


@router.get("/{session_id}/export")
async def export_session(
    session_id: str,
    format: str = Query("json", description="导出格式: json/markdown")
):
    """导出会话"""
    store = get_session_store()
    exported = store.export_session(session_id, format=format)

    if not exported:
        raise HTTPException(status_code=404, detail="会话不存在")

    return {
        "session_id": session_id,
        "format": format,
        "content": exported,
        "exported_at": datetime.now().isoformat()
    }


@router.get("/tags/all", response_model=List[TagResponse])
async def get_all_tags():
    """获取所有标签"""
    store = get_session_store()
    tags = store.get_all_tags()
    return [TagResponse(**tag) for tag in tags]


@router.get("/stats/overview", response_model=StatisticsResponse)
async def get_statistics():
    """获取会话统计信息"""
    store = get_session_store()
    stats = store.get_statistics()
    return StatisticsResponse(**stats)
