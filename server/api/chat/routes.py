from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from api.chat_branch import get_next_message_tree_metadata, register_branch_message

from .context import get_context_manager
from .session import get_session_manager

router = APIRouter(prefix="/chat", tags=["Chat"])
class SendMessageRequest(BaseModel):
    content: str = Field(..., description="Message content")
    role: str = Field(default="user", description="Message role")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Message metadata")


class CreateSessionRequest(BaseModel):
    title: str = Field(default="New Chat")
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateSessionMetadataRequest(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: str


class SessionResponse(BaseModel):
    id: str
    title: str
    message_count: int
    created_at: str
    updated_at: str


@router.post("/sessions")
async def create_session(request: CreateSessionRequest | None = None, title: str | None = None):
    manager = get_session_manager()
    resolved_title = request.title if request and request.title else (title or "New Chat")
    session = manager.create_session(
        title=resolved_title,
        metadata=request.metadata if request else None,
    )
    return {
        "id": session.id,
        "title": session.title,
        "message_count": session.message_count,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


@router.get("/sessions")
async def list_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    manager = get_session_manager()
    sessions = manager.list_sessions(limit=limit, offset=offset)

    return {
        "sessions": [
            {
                "id": s.id,
                "title": s.title,
                "message_count": s.message_count,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
                "metadata": s.metadata,
            }
            for s in sessions
        ],
        "total": manager.get_session_count(),
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
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
        "metadata": session.metadata,
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    manager = get_session_manager()
    success = manager.delete_session(session_id)

    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"success": True, "session_id": session_id}


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, request: SendMessageRequest):
    session_manager = get_session_manager()
    context_manager = get_context_manager()

    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    message_metadata, current_branch_id = get_next_message_tree_metadata(session, request.metadata)
    message = session.add_message(
        role=request.role,
        content=request.content,
        metadata=message_metadata,
    )
    register_branch_message(session, current_branch_id, message.id)
    session_manager.save_session(session_id)

    context_manager.add_message(
        session_id=session_id,
        role=request.role,
        content=request.content,
        metadata=message_metadata,
    )

    return {
        "id": message.id,
        "session_id": session_id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=200),
):
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
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
        "total": len(messages),
    }


@router.delete("/sessions/{session_id}/messages")
async def clear_messages(session_id: str):
    session_manager = get_session_manager()
    context_manager = get_context_manager()

    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.clear_messages()
    session_manager.save_session(session_id)
    context_manager.clear_context(session_id)

    return {"success": True, "session_id": session_id}


@router.put("/sessions/{session_id}/title")
async def update_session_title(session_id: str, title: str):
    manager = get_session_manager()
    success = manager.update_session_title(session_id, title)

    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"success": True, "session_id": session_id, "title": title}


@router.put("/sessions/{session_id}/metadata")
async def update_session_metadata(session_id: str, request: UpdateSessionMetadataRequest):
    manager = get_session_manager()
    success = manager.update_session_metadata(session_id, request.metadata)

    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

    session = manager.get_session(session_id)
    return {
        "success": True,
        "session_id": session_id,
        "metadata": session.metadata if session else request.metadata,
    }


@router.get("/sessions/{session_id}/context")
async def get_context(session_id: str):
    manager = get_context_manager()
    context = manager.get_context(session_id)

    return {
        "session_id": session_id,
        "message_count": len(context.messages),
        "system_prompt": context.system_prompt,
        "messages": [m.to_dict() for m in context.messages],
    }


@router.put("/sessions/{session_id}/system-prompt")
async def set_system_prompt(session_id: str, prompt: str):
    manager = get_context_manager()
    context = manager.get_context(session_id)
    context.set_system_prompt(prompt)

    return {"success": True, "session_id": session_id}
