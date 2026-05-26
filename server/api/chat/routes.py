from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from api.chat_branch import get_next_message_tree_metadata, register_branch_message
from core.db_manager import run_sync

from .context import get_context_manager
from .session import Message, get_session_manager

router = APIRouter(prefix="/chat", tags=["Chat"])


class ChatApiModel(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class SendMessageRequest(ChatApiModel):
    content: str = Field(..., description="Message content")
    role: str = Field(default="user", description="Message role")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Message metadata")


class CreateSessionRequest(ChatApiModel):
    title: str = Field(default="New Chat")
    model_id: str | None = Field(default=None)
    backend: str | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateSessionMetadataRequest(ChatApiModel):
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateMessageRequest(ChatApiModel):
    content: str | None = Field(default=None, description="Updated message content")
    role: str | None = Field(default=None, description="Updated message role")
    metadata: dict[str, Any] | None = Field(default=None, description="Updated message metadata")


class ReplaceMessageItem(ChatApiModel):
    id: str | None = Field(default=None, description="Existing message id")
    content: str = Field(..., description="Message content")
    role: str = Field(default="user", description="Message role")
    created_at: str | None = Field(default=None, description="Existing message timestamp")
    timestamp: str | None = Field(default=None, description="Existing client timestamp")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Message metadata")


class ReplaceMessagesRequest(ChatApiModel):
    messages: list[ReplaceMessageItem] = Field(default_factory=list)


class MessageResponse(ChatApiModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionResponse(ChatApiModel):
    id: str
    title: str
    message_count: int
    created_at: str
    updated_at: str


async def _sync_context_from_session(session_id: str) -> None:
    session = await run_sync(get_session_manager().get_session, session_id)
    context_manager = get_context_manager()
    await run_sync(context_manager.clear_context, session_id)
    if not session:
        return
    for message in session.messages:
        await run_sync(
            context_manager.add_message,
            session_id=session_id,
            role=message.role,
            content=message.content,
            metadata=message.metadata,
        )


@router.post("/sessions")
async def create_session(request: CreateSessionRequest | None = None, title: str | None = None):
    manager = get_session_manager()
    resolved_title = request.title if request and request.title else (title or "New Chat")
    metadata = dict(request.metadata) if request else {}
    if request and request.model_id:
        metadata["model_id"] = request.model_id
    if request and request.backend:
        metadata["backend"] = request.backend
    session = await run_sync(
        manager.create_session,
        title=resolved_title,
        metadata=metadata,
    )
    return {
        "id": session.id,
        "title": session.title,
        "model_id": session.metadata.get("model_id"),
        "backend": session.metadata.get("backend"),
        "message_count": session.message_count,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "metadata": session.metadata,
    }


@router.get("/sessions")
async def list_sessions(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    manager = get_session_manager()
    sessions = await run_sync(manager.list_sessions, limit=limit, offset=offset)

    return {
        "sessions": [
            {
                "id": s.id,
                "title": s.title,
                "model_id": s.metadata.get("model_id"),
                "backend": s.metadata.get("backend"),
                "message_count": s.message_count,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
                "metadata": s.metadata,
            }
            for s in sessions
        ],
        "total": await run_sync(manager.get_session_count),
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    manager = get_session_manager()
    session = await run_sync(manager.get_session, session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "id": session.id,
        "title": session.title,
        "model_id": session.metadata.get("model_id"),
        "backend": session.metadata.get("backend"),
        "message_count": session.message_count,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "metadata": session.metadata,
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    manager = get_session_manager()
    await run_sync(manager.delete_session, session_id)

    # 无论找没找到都返回 200，因为目标是"让它不存在"
    return {"success": True, "session_id": session_id}


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, request: SendMessageRequest):
    session_manager = get_session_manager()
    context_manager = get_context_manager()

    session = await run_sync(session_manager.get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    message_metadata, current_branch_id = get_next_message_tree_metadata(session, request.metadata)
    message = Message(role=request.role, content=request.content, metadata=message_metadata)
    register_branch_message(session, current_branch_id, message.id)
    await run_sync(session_manager.append_message, session_id, message)

    await run_sync(
        context_manager.add_message,
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
        "metadata": message.metadata,
    }


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: str,
    limit: int = Query(default=200, ge=1, le=500),
):
    manager = get_session_manager()
    session = await run_sync(manager.get_session, session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = await run_sync(session.get_messages, limit=limit)

    return {
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
                "metadata": m.metadata,
            }
            for m in messages
        ],
        "total": len(messages),
    }


@router.put("/sessions/{session_id}/messages")
async def replace_messages(session_id: str, request: ReplaceMessagesRequest):
    session_manager = get_session_manager()

    session = await run_sync(session_manager.get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = [
        {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at or message.timestamp,
            "metadata": message.metadata,
        }
        for message in request.messages
    ]
    await run_sync(session_manager.replace_session_messages, session_id, messages)
    await _sync_context_from_session(session_id)

    updated_session = await run_sync(session_manager.get_session, session_id)
    return {
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
                "metadata": m.metadata,
            }
            for m in (updated_session.messages if updated_session else [])
        ],
        "total": updated_session.message_count if updated_session else 0,
    }


@router.delete("/sessions/{session_id}/messages")
async def clear_messages(session_id: str):
    session_manager = get_session_manager()
    context_manager = get_context_manager()

    session = await run_sync(session_manager.get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await run_sync(session_manager.clear_session_messages, session_id)
    await run_sync(context_manager.clear_context, session_id)

    return {"success": True, "session_id": session_id}


@router.put("/sessions/{session_id}/messages/{message_id}")
async def update_message(session_id: str, message_id: str, request: UpdateMessageRequest):
    manager = get_session_manager()
    message = await run_sync(
        manager.update_message,
        session_id,
        message_id,
        content=request.content,
        metadata=request.metadata,
        role=request.role,
    )

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    await _sync_context_from_session(session_id)

    return {
        "id": message.id,
        "session_id": session_id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
        "metadata": message.metadata,
    }


@router.delete("/sessions/{session_id}/messages/{message_id}")
async def delete_message(session_id: str, message_id: str):
    manager = get_session_manager()
    success = await run_sync(manager.delete_message, session_id, message_id)

    if not success:
        raise HTTPException(status_code=404, detail="Message not found")

    await _sync_context_from_session(session_id)

    return {"success": True, "session_id": session_id, "message_id": message_id}


@router.put("/sessions/{session_id}/title")
async def update_session_title(session_id: str, title: str):
    manager = get_session_manager()
    success = await run_sync(manager.update_session_title, session_id, title)

    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"success": True, "session_id": session_id, "title": title}


@router.put("/sessions/{session_id}/metadata")
async def update_session_metadata(session_id: str, request: UpdateSessionMetadataRequest):
    manager = get_session_manager()
    success = await run_sync(manager.update_session_metadata, session_id, request.metadata)

    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

    session = await run_sync(manager.get_session, session_id)
    return {
        "success": True,
        "session_id": session_id,
        "metadata": session.metadata if session else request.metadata,
    }


@router.get("/sessions/{session_id}/context")
async def get_context(session_id: str):
    manager = get_context_manager()
    context = await run_sync(manager.get_context, session_id)

    return {
        "session_id": session_id,
        "message_count": len(context.messages),
        "system_prompt": context.system_prompt,
        "messages": [m.to_dict() for m in context.messages],
    }


@router.put("/sessions/{session_id}/system-prompt")
async def set_system_prompt(session_id: str, prompt: str):
    manager = get_context_manager()
    context = await run_sync(manager.get_context, session_id)
    await run_sync(context.set_system_prompt, prompt)

    return {"success": True, "session_id": session_id}
