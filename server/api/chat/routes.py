"""
对话模块路由 - 整合会话管理、历史记录、上下文管理
"""
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .context import get_context_manager
from .session import get_session_manager

router = APIRouter(prefix="/chat", tags=["Chat"])


class SendMessageRequest(BaseModel):
    """发送消息请求"""
    content: str = Field(..., description="消息内容")
    role: str = Field(default="user", description="角色")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")


class MessageResponse(BaseModel):
    """消息响应"""
    id: str
    session_id: str
    role: str
    content: str
    created_at: str


class SessionResponse(BaseModel):
    """会话响应"""
    id: str
    title: str
    message_count: int
    created_at: str
    updated_at: str


@router.post("/sessions")
async def create_session(title: str = "新对话"):
    """创建新会话"""
    manager = get_session_manager()
    session = manager.create_session(title=title)
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at.isoformat()
    }


@router.get("/sessions")
async def list_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0)
):
    """列出会话"""
    manager = get_session_manager()
    sessions = manager.list_sessions(limit=limit, offset=offset)

    return {
        "sessions": [
            {
                "id": s.id,
                "title": s.title,
                "message_count": s.message_count,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat()
            }
            for s in sessions
        ],
        "total": manager.get_session_count()
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """获取会话详情"""
    manager = get_session_manager()
    session = manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "id": session.id,
        "title": session.title,
        "message_count": session.message_count,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "metadata": session.metadata
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    manager = get_session_manager()
    success = manager.delete_session(session_id)

    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"success": True, "session_id": session_id}


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, request: SendMessageRequest):
    """发送消息"""
    session_manager = get_session_manager()
    context_manager = get_context_manager()

    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    message = session.add_message(
        role=request.role,
        content=request.content,
        metadata=request.metadata
    )

    context_manager.add_message(
        session_id=session_id,
        role=request.role,
        content=request.content,
        metadata=request.metadata
    )

    return {
        "id": message.id,
        "session_id": session_id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat()
    }


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=200)
):
    """获取会话消息"""
    manager = get_session_manager()
    session = manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = session.get_messages(limit=limit)

    return {
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat()
            }
            for m in messages
        ],
        "total": len(messages)
    }


@router.delete("/sessions/{session_id}/messages")
async def clear_messages(session_id: str):
    """清空会话消息"""
    session_manager = get_session_manager()
    context_manager = get_context_manager()

    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.clear_messages()
    context_manager.clear_context(session_id)

    return {"success": True, "session_id": session_id}


@router.put("/sessions/{session_id}/title")
async def update_session_title(session_id: str, title: str):
    """更新会话标题"""
    manager = get_session_manager()
    success = manager.update_session_title(session_id, title)

    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"success": True, "session_id": session_id, "title": title}


@router.get("/sessions/{session_id}/context")
async def get_context(session_id: str):
    """获取会话上下文"""
    manager = get_context_manager()
    context = manager.get_context(session_id)

    return {
        "session_id": session_id,
        "message_count": len(context.messages),
        "system_prompt": context.system_prompt,
        "messages": [m.to_dict() for m in context.messages]
    }


@router.put("/sessions/{session_id}/system-prompt")
async def set_system_prompt(session_id: str, prompt: str):
    """设置系统提示"""
    manager = get_context_manager()
    context = manager.get_context(session_id)
    context.set_system_prompt(prompt)

    return {"success": True, "session_id": session_id}
