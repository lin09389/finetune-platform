"""
对话分享 API
支持生成分享链接、导出 Markdown/PDF
"""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

router = APIRouter(prefix="/chat/share", tags=["chat-share"])

DATA_DIR = Path("data/chat")
SHARE_DIR = Path("data/share")
SHARE_DIR.mkdir(parents=True, exist_ok=True)


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


def get_session_file(session_id: str) -> Path:
    return DATA_DIR / f"session_{session_id}.json"


def load_session(session_id: str) -> dict[str, Any] | None:
    file = get_session_file(session_id)
    if file.exists():
        with open(file, encoding='utf-8') as f:
            return json.load(f)
    return None


def save_share(share: SharedChat):
    file = get_share_file(share.share_id)
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(share.model_dump(), f, ensure_ascii=False, indent=2)


def load_share(share_id: str) -> SharedChat | None:
    file = get_share_file(share_id)
    if file.exists():
        with open(file, encoding='utf-8') as f:
            return SharedChat(**json.load(f))
    return None


@router.post("", response_model=ShareResponse)
async def create_share(request: CreateShareRequest):
    session = load_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    share_id = hashlib.sha256(
        f"{request.session_id}{datetime.now().isoformat()}".encode()
    ).hexdigest()[:12]

    messages = session.get("messages", [])
    title = request.title or session.get("title", "分享的对话")

    expires_at = None
    if request.expires_in_hours:
        from datetime import timedelta
        expires_at = (datetime.now() + timedelta(hours=request.expires_in_hours)).isoformat()

    share = SharedChat(
        share_id=share_id,
        session_id=request.session_id,
        title=title,
        messages=messages,
        created_at=datetime.now().isoformat(),
        expires_at=expires_at,
        is_public=request.is_public
    )

    save_share(share)

    return ShareResponse(
        share_id=share_id,
        share_url=f"/share/{share_id}",
        expires_at=expires_at
    )


@router.get("/{share_id}", response_model=SharedChat)
async def get_share(share_id: str):
    share = load_share(share_id)
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    if share.expires_at and datetime.fromisoformat(share.expires_at) < datetime.now():
        raise HTTPException(status_code=410, detail="Share has expired")

    share.view_count += 1
    save_share(share)

    return share


@router.get("/{share_id}/html", response_class=HTMLResponse)
async def get_share_html(share_id: str):
    share = load_share(share_id)
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    if share.expires_at and datetime.fromisoformat(share.expires_at) < datetime.now():
        raise HTTPException(status_code=410, detail="Share has expired")

    messages_html = ""
    for msg in share.messages:
        role = "用户" if msg.get("role") == "user" else "助手"
        role_class = "user-message" if msg.get("role") == "user" else "assistant-message"
        messages_html += f'''
        <div class="message {role_class}">
            <div class="role">{role}</div>
            <div class="content">{msg.get("content", "")}</div>
            <div class="time">{msg.get("timestamp", "")}</div>
        </div>
        '''

    html = f'''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{share.title}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
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
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
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
            pre {{
                background: #f5f5f5;
                padding: 12px;
                border-radius: 6px;
                overflow-x: auto;
            }}
            code {{
                font-family: 'Monaco', 'Menlo', monospace;
                font-size: 13px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="title">{share.title}</div>
            <div class="meta">
                分享于: {share.created_at} | 浏览 {share.view_count} 次
            </div>
        </div>
        <div class="messages">
            {messages_html}
        </div>
    </body>
    </html>
    '''

    return HTMLResponse(content=html)


@router.get("/{share_id}/markdown", response_class=PlainTextResponse)
async def export_markdown(share_id: str):
    share = load_share(share_id)
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    md = f"# {share.title}\n\n"
    md += f"> 分享于: {share.created_at}\n\n"
    md += "---\n\n"

    for msg in share.messages:
        role = "用户" if msg.get("role") == "user" else "助手"
        content = msg.get("content", "")
        timestamp = msg.get("timestamp", "")

        md += f"## {role}\n\n{content}\n\n"
        if timestamp:
            md += f"> {timestamp}\n\n"

    return PlainTextResponse(content=md, media_type="text/markdown")


@router.delete("/{share_id}")
async def delete_share(share_id: str):
    file = get_share_file(share_id)
    if not file.exists():
        raise HTTPException(status_code=404, detail="Share not found")

    file.unlink()
    return {"success": True, "message": "分享已删除"}
