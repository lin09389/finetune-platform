"""Chat sharing endpoints backed by the canonical session store."""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from api.chat.session import Session, get_session_manager
from core.storage import ChatShareRepository, StorageOutboxRepository, dual_write_enabled, json_fallback_enabled

router = APIRouter(prefix="/chat/share", tags=["chat-share"])

SHARE_DIR = Path("data/share")
SHARE_DIR.mkdir(parents=True, exist_ok=True)
share_repository = ChatShareRepository()
share_outbox = StorageOutboxRepository()


class SharedChat(BaseModel):
    share_id: str
    session_id: str
    title: str
    messages: list[dict[str, Any]]
    created_at: str
    expires_at: str | None = None
    view_count: int = 0
    is_public: bool = True


class CreateShareRequest(BaseModel):
    session_id: str
    title: str | None = None
    expires_in_hours: int | None = None
    is_public: bool = True


class ShareResponse(BaseModel):
    share_id: str
    share_url: str
    expires_at: str | None = None


def get_share_file(share_id: str) -> Path:
    return SHARE_DIR / f"share_{share_id}.json"


def save_share(share: SharedChat) -> None:
    payload = share.model_dump()
    share_repository.save_share(payload)
    if not dual_write_enabled():
        return

    file_path = get_share_file(share.share_id)
    task_id = share_outbox.enqueue(
        task_type="json_shadow_write",
        target=str(file_path),
        payload=payload,
        task_id=f"json_share_{share.share_id}",
    )
    tmp_path = file_path.with_suffix(f".json.tmp.{share.share_id}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
        tmp_path.replace(file_path)
        share_outbox.mark_done(task_id)
    except Exception as exc:
        share_outbox.mark_failed(task_id, str(exc))


def load_share(share_id: str) -> SharedChat | None:
    payload = share_repository.get_share(share_id)
    if payload:
        return SharedChat(**payload)

    if not json_fallback_enabled():
        return None

    file_path = get_share_file(share_id)
    if not file_path.exists():
        return None
    with open(file_path, encoding="utf-8") as handle:
        share = SharedChat(**json.load(handle))
    share_repository.save_share(share.model_dump())
    return share


def _normalize_message(message: Any) -> dict[str, Any]:
    if hasattr(message, "to_dict"):
        message = message.to_dict()

    if not isinstance(message, dict):
        return {
            "id": "",
            "role": "assistant",
            "content": str(message),
            "timestamp": "",
        }

    timestamp = (
        message.get("timestamp")
        or message.get("created_at")
        or message.get("updated_at")
        or ""
    )
    return {
        "id": str(message.get("id", "")),
        "role": str(message.get("role", "assistant")),
        "content": str(message.get("content", "")),
        "timestamp": str(timestamp),
        "metadata": message.get("metadata", {}) or {},
    }


def _get_session(session_id: str) -> Session:
    session = get_session_manager().get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _ensure_not_expired(share: SharedChat) -> None:
    if share.expires_at and datetime.fromisoformat(share.expires_at) < datetime.now():
        raise HTTPException(status_code=410, detail="Share has expired")


@router.post("", response_model=ShareResponse)
async def create_share(request: CreateShareRequest):
    session = _get_session(request.session_id)
    share_id = hashlib.sha256(
        f"{request.session_id}:{datetime.now().isoformat()}".encode()
    ).hexdigest()[:12]

    expires_at = None
    if request.expires_in_hours:
        expires_at = (
            datetime.now() + timedelta(hours=request.expires_in_hours)
        ).isoformat()

    share = SharedChat(
        share_id=share_id,
        session_id=request.session_id,
        title=request.title or session.title or "Shared Chat",
        messages=[_normalize_message(message) for message in session.messages],
        created_at=datetime.now().isoformat(),
        expires_at=expires_at,
        is_public=request.is_public,
    )
    save_share(share)

    return ShareResponse(
        share_id=share_id,
        share_url=f"/share/{share_id}",
        expires_at=expires_at,
    )


@router.get("/{share_id}", response_model=SharedChat)
async def get_share(share_id: str):
    share = load_share(share_id)
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    _ensure_not_expired(share)
    share.view_count = share_repository.increment_view_count(share.share_id)
    if dual_write_enabled():
        save_share(share)
    return share


@router.get("/{share_id}/html", response_class=HTMLResponse)
async def get_share_html(share_id: str):
    share = load_share(share_id)
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    _ensure_not_expired(share)

    message_blocks: list[str] = []
    for message in share.messages:
        role = "User" if message.get("role") == "user" else "Assistant"
        role_class = "user-message" if message.get("role") == "user" else "assistant-message"
        message_blocks.append(
            f"""
            <div class="message {role_class}">
                <div class="role">{role}</div>
                <div class="content">{message.get("content", "")}</div>
                <div class="time">{message.get("timestamp", "")}</div>
            </div>
            """
        )

    html = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{share.title}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                background: #f5f5f5;
            }}
            .header {{
                text-align: center;
                padding: 20px 0;
                border-bottom: 1px solid #e0e0e0;
                margin-bottom: 20px;
            }}
            .title {{
                font-size: 24px;
                font-weight: 600;
                color: #333;
            }}
            .meta {{
                font-size: 12px;
                color: #999;
                margin-top: 8px;
            }}
            .message {{
                padding: 16px;
                margin: 12px 0;
                border-radius: 12px;
                background: white;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            }}
            .user-message {{
                background: #e3f2fd;
                margin-left: 40px;
            }}
            .assistant-message {{
                background: white;
                margin-right: 40px;
            }}
            .role {{
                font-weight: 600;
                font-size: 12px;
                color: #666;
                margin-bottom: 8px;
            }}
            .content {{
                white-space: pre-wrap;
                line-height: 1.6;
            }}
            .time {{
                font-size: 11px;
                color: #999;
                margin-top: 8px;
                text-align: right;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="title">{share.title}</div>
            <div class="meta">
                Shared at {share.created_at} | Views {share.view_count}
            </div>
        </div>
        <div class="messages">
            {''.join(message_blocks)}
        </div>
    </body>
    </html>
    """

    return HTMLResponse(content=html)


@router.get("/{share_id}/markdown", response_class=PlainTextResponse)
async def export_markdown(share_id: str):
    share = load_share(share_id)
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    _ensure_not_expired(share)

    lines = [f"# {share.title}", "", f"> Shared at {share.created_at}", "", "---", ""]
    for message in share.messages:
        role = "User" if message.get("role") == "user" else "Assistant"
        lines.extend([f"## {role}", "", str(message.get("content", "")), ""])
        if message.get("timestamp"):
            lines.extend([f"> {message['timestamp']}", ""])

    return PlainTextResponse(content="\n".join(lines), media_type="text/markdown")


@router.delete("/{share_id}")
async def delete_share(share_id: str):
    file_path = get_share_file(share_id)
    deleted = share_repository.delete_share(share_id)
    if not deleted and not file_path.exists():
        raise HTTPException(status_code=404, detail="Share not found")

    if file_path.exists():
        file_path.unlink()
    return {"success": True, "message": "Share deleted"}
