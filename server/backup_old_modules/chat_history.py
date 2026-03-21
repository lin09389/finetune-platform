"""
对话历史管理 API
管理聊天会话和消息记录
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import sqlite3
import json
import os
from pathlib import Path
import logging

from core.db_manager import get_db_pool, init_db_pool

logger = logging.getLogger(__name__)

router = APIRouter()

DB_DIR = Path(__file__).parent.parent / "data"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "chat_history.db"


def init_db():
    """初始化数据库"""
    pool = init_db_pool(str(DB_PATH))
    
    with pool.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                model_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session
            ON chat_messages(session_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_updated
            ON chat_sessions(updated_at DESC)
        """)


class ChatSessionCreate(BaseModel):
    """创建会话请求"""
    title: str = Field(..., description="会话标题")
    model_id: str = Field(default="", description="模型 ID")


class ChatSession(BaseModel):
    """会话信息"""
    id: str
    title: str
    model_id: str
    created_at: str
    updated_at: str
    message_count: int = 0


class ChatMessage(BaseModel):
    """消息信息"""
    id: str
    session_id: str
    role: str
    content: str
    timestamp: str


class MessageBatch(BaseModel):
    """批量消息"""
    messages: List[Dict[str, Any]]


def init_chat_db():
    """初始化聊天历史数据库"""
    init_db()
    logger.info(f"Chat history database initialized at {DB_PATH}")


@router.get("/history", response_model=List[ChatSession])
async def get_history():
    """获取所有会话列表"""
    pool = get_db_pool()
    with pool.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                s.*,
                COUNT(m.id) as message_count
            FROM chat_sessions s
            LEFT JOIN chat_messages m ON s.id = m.session_id
            GROUP BY s.id
            ORDER BY s.updated_at DESC
        """)

        rows = cursor.fetchall()

        sessions = []
        for row in rows:
            sessions.append({
                "id": row["id"],
                "title": row["title"],
                "model_id": row["model_id"] or "",
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "message_count": row["message_count"]
            })

        return sessions


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """获取单个会话详情"""
    pool = get_db_pool()
    with pool.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM chat_sessions WHERE id = ?
        """, (session_id,))

        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="会话不存在")

        cursor.execute("""
            SELECT * FROM chat_messages
            WHERE session_id = ?
            ORDER BY timestamp ASC
        """, (session_id,))

        messages = []
        for msg_row in cursor.fetchall():
            messages.append({
                "id": msg_row["id"],
                "role": msg_row["role"],
                "content": msg_row["content"],
                "timestamp": msg_row["timestamp"]
            })

        return {
            "id": row["id"],
            "title": row["title"],
            "model_id": row["model_id"] or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "messages": messages
        }


@router.post("/session", response_model=ChatSession)
async def create_session(data: ChatSessionCreate):
    """创建新会话"""
    session_id = f"session_{datetime.now().strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}"

    pool = get_db_pool()
    with pool.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO chat_sessions (id, title, model_id)
            VALUES (?, ?, ?)
        """, (session_id, data.title, data.model_id))

    return {
        "id": session_id,
        "title": data.title,
        "model_id": data.model_id,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "message_count": 0
    }


@router.put("/session/{session_id}")
async def update_session(session_id: str, data: ChatSessionCreate):
    """更新会话标题"""
    pool = get_db_pool()
    with pool.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE chat_sessions
            SET title = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (data.title, session_id))

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="会话不存在")

    return {"message": "会话已更新"}


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    pool = get_db_pool()
    with pool.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM chat_messages WHERE session_id = ?
        """, (session_id,))

        cursor.execute("""
            DELETE FROM chat_sessions WHERE id = ?
        """, (session_id,))

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="会话不存在")

    return {"message": "会话已删除"}


@router.post("/session/{session_id}/message")
async def add_messages(session_id: str, data: MessageBatch):
    """添加消息到会话"""
    pool = get_db_pool()
    with pool.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id FROM chat_sessions WHERE id = ?
        """, (session_id,))

        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="会话不存在")

        for msg in data.messages:
            msg_id = msg.get("id", f"msg_{datetime.now().strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}")
            cursor.execute("""
                INSERT INTO chat_messages (id, session_id, role, content, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (
                msg_id,
                session_id,
                msg.get("role", "user"),
                msg.get("content", ""),
                msg.get("timestamp", datetime.now().isoformat())
            ))

        cursor.execute("""
            UPDATE chat_sessions
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (session_id,))

    return {"message": "消息已添加", "count": len(data.messages)}


@router.delete("/session/{session_id}/message/{message_id}")
async def delete_message(session_id: str, message_id: str):
    """删除单条消息"""
    pool = get_db_pool()
    with pool.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM chat_messages
            WHERE session_id = ? AND id = ?
        """, (session_id, message_id))

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="消息不存在")

        cursor.execute("""
            UPDATE chat_sessions
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (session_id,))

    return {"message": "消息已删除"}


@router.get("/stats")
async def get_stats():
    """获取统计信息"""
    pool = get_db_pool()
    with pool.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM chat_sessions")
        total_sessions = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM chat_messages")
        total_messages = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(DISTINCT session_id)
            FROM chat_messages
            WHERE timestamp >= datetime('now', '-7 days')
        """)
        active_sessions = cursor.fetchone()[0]

    return {
        "total_sessions": total_sessions,
        "total_messages": total_messages,
        "active_sessions_7d": active_sessions
    }
