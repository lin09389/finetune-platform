"""
会话持久化存储模�?
功能�?- 会话 CRUD 操作
- 会话元数据管理（标题、标签、时间）
- 按时间、标签搜索会�?- 会话恢复（重新加载历史消息）
- 消息重要性评�?"""
import sqlite3
import json
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class SessionStatus(str, Enum):
    """会话状�?""
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class MessageRole(str, Enum):
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"


@dataclass
class SessionMetadata:
    """会话元数�?""
    title: str = ""
    description: str = ""
    model_id: str = ""
    tags: List[str] = field(default_factory=list)
    status: SessionStatus = SessionStatus.ACTIVE
    starred: bool = False
    pinned: bool = False
    custom_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionMessage:
    """会话消息"""
    id: str = ""
    session_id: str = ""
    role: MessageRole = MessageRole.USER
    content: str = ""
    timestamp: str = ""
    token_count: int = 0
    importance: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role.value if isinstance(self.role, MessageRole) else self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "token_count": self.token_count,
            "importance": self.importance,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionMessage":
        return cls(
            id=data.get("id", ""),
            session_id=data.get("session_id", ""),
            role=MessageRole(data.get("role", "user")),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", ""),
            token_count=data.get("token_count", 0),
            importance=data.get("importance", 0.5),
            metadata=data.get("metadata", {})
        )


@dataclass
class ChatSession:
    """聊天会话"""
    id: str = ""
    metadata: SessionMetadata = field(default_factory=SessionMetadata)
    messages: List[SessionMessage] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    message_count: int = 0
    total_tokens: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.metadata.title,
            "description": self.metadata.description,
            "model_id": self.metadata.model_id,
            "tags": self.metadata.tags,
            "status": self.metadata.status.value if isinstance(self.metadata.status, SessionStatus) else self.metadata.status,
            "starred": self.metadata.starred,
            "pinned": self.metadata.pinned,
            "custom_data": self.metadata.custom_data,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": self.message_count,
            "total_tokens": self.total_tokens
        }


class SessionStore:
    """会话存储管理�?""

    _instance: Optional['SessionStore'] = None
    _lock = threading.Lock()

    def __new__(cls, db_path: str = None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str = None):
        if self._initialized:
            return

        self._db_path = db_path or str(Path(__file__).parent.parent / "data" / "sessions.db")
        self._thread_local = threading.local()
        self._initialized = True
        self._init_database()
        logger.info(f"会话存储已初始化: {self._db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接"""
        if not hasattr(self._thread_local, 'connection'):
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            self._thread_local.connection = conn
        return self._thread_local.connection

    def _init_database(self):
        """初始化数据库表结�?""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                description TEXT DEFAULT '',
                model_id TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                starred INTEGER DEFAULT 0,
                pinned INTEGER DEFAULT 0,
                custom_data TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_count INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS session_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                token_count INTEGER DEFAULT 0,
                importance REAL DEFAULT 0.5,
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS session_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                UNIQUE(session_id, tag)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session
            ON session_messages(session_id, timestamp)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_updated
            ON sessions(updated_at DESC)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_status
            ON sessions(status)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tags_session
            ON session_tags(session_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tags_tag
            ON session_tags(tag)
        """)

        conn.commit()
        logger.debug("数据库表结构初始化完�?)

    def generate_id(self, prefix: str = "session") -> str:
        """生成唯一 ID"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        unique_part = uuid.uuid4().hex[:8]
        return f"{prefix}_{timestamp}_{unique_part}"

    def create_session(
        self,
        title: str = "",
        model_id: str = "",
        description: str = "",
        tags: List[str] = None,
        custom_data: Dict[str, Any] = None
    ) -> ChatSession:
        """创建新会�?""
        session_id = self.generate_id("session")
        now = datetime.now().isoformat()

        if not title:
            title = f"新对�?{datetime.now().strftime('%Y-%m-%d %H:%M')}"

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO sessions (id, title, description, model_id, custom_data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            title,
            description,
            model_id,
            json.dumps(custom_data or {}, ensure_ascii=False),
            now,
            now
        ))

        if tags:
            for tag in tags:
                cursor.execute("""
                    INSERT OR IGNORE INTO session_tags (session_id, tag)
                    VALUES (?, ?)
                """, (session_id, tag))

        conn.commit()

        session = ChatSession(
            id=session_id,
            metadata=SessionMetadata(
                title=title,
                description=description,
                model_id=model_id,
                tags=tags or [],
                custom_data=custom_data or {}
            ),
            created_at=now,
            updated_at=now
        )

        logger.info(f"创建会话: {session_id}")
        return session

    def get_session(self, session_id: str, include_messages: bool = True) -> Optional[ChatSession]:
        """获取会话详情"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM sessions WHERE id = ?
        """, (session_id,))

        row = cursor.fetchone()
        if not row:
            return None

        cursor.execute("""
            SELECT tag FROM session_tags WHERE session_id = ?
        """, (session_id,))
        tags = [r["tag"] for r in cursor.fetchall()]

        metadata = SessionMetadata(
            title=row["title"],
            description=row["description"] or "",
            model_id=row["model_id"] or "",
            tags=tags,
            status=SessionStatus(row["status"]),
            starred=bool(row["starred"]),
            pinned=bool(row["pinned"]),
            custom_data=json.loads(row["custom_data"] or "{}")
        )

        messages = []
        if include_messages:
            cursor.execute("""
                SELECT * FROM session_messages
                WHERE session_id = ?
                ORDER BY timestamp ASC
            """, (session_id,))

            for msg_row in cursor.fetchall():
                messages.append(SessionMessage(
                    id=msg_row["id"],
                    session_id=msg_row["session_id"],
                    role=MessageRole(msg_row["role"]),
                    content=msg_row["content"],
                    timestamp=msg_row["timestamp"],
                    token_count=msg_row["token_count"],
                    importance=msg_row["importance"],
                    metadata=json.loads(msg_row["metadata"] or "{}")
                ))

        return ChatSession(
            id=row["id"],
            metadata=metadata,
            messages=messages,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            message_count=row["message_count"],
            total_tokens=row["total_tokens"]
        )

    def update_session(
        self,
        session_id: str,
        title: str = None,
        description: str = None,
        model_id: str = None,
        tags: List[str] = None,
        status: SessionStatus = None,
        starred: bool = None,
        pinned: bool = None,
        custom_data: Dict[str, Any] = None
    ) -> bool:
        """更新会话元数�?""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if not cursor.fetchone():
            return False

        updates = []
        params = []

        if title is not None:
            updates.append("title = ?")
            params.append(title)

        if description is not None:
            updates.append("description = ?")
            params.append(description)

        if model_id is not None:
            updates.append("model_id = ?")
            params.append(model_id)

        if status is not None:
            updates.append("status = ?")
            params.append(status.value)

        if starred is not None:
            updates.append("starred = ?")
            params.append(1 if starred else 0)

        if pinned is not None:
            updates.append("pinned = ?")
            params.append(1 if pinned else 0)

        if custom_data is not None:
            updates.append("custom_data = ?")
            params.append(json.dumps(custom_data, ensure_ascii=False))

        if updates:
            updates.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(session_id)

            cursor.execute(f"""
                UPDATE sessions SET {', '.join(updates)}
                WHERE id = ?
            """, params)

        if tags is not None:
            cursor.execute("DELETE FROM session_tags WHERE session_id = ?", (session_id,))
            for tag in tags:
                cursor.execute("""
                    INSERT OR IGNORE INTO session_tags (session_id, tag)
                    VALUES (?, ?)
                """, (session_id, tag))

        conn.commit()
        logger.debug(f"更新会话: {session_id}")
        return True

    def delete_session(self, session_id: str, soft_delete: bool = True) -> bool:
        """删除会话"""
        conn = self._get_connection()
        cursor = conn.cursor()

        if soft_delete:
            cursor.execute("""
                UPDATE sessions SET status = ?, updated_at = ?
                WHERE id = ?
            """, (SessionStatus.DELETED.value, datetime.now().isoformat(), session_id))
        else:
            cursor.execute("DELETE FROM session_tags WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM session_messages WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

        success = cursor.rowcount > 0
        conn.commit()

        if success:
            logger.info(f"{'�? if soft_delete else '�?}删除会话: {session_id}")
        return success

    def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        token_count: int = 0,
        importance: float = 0.5,
        metadata: Dict[str, Any] = None
    ) -> Optional[SessionMessage]:
        """添加消息到会�?""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if not cursor.fetchone():
            return None

        message_id = self.generate_id("msg")
        now = datetime.now().isoformat()

        cursor.execute("""
            INSERT INTO session_messages (id, session_id, role, content, timestamp, token_count, importance, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            message_id,
            session_id,
            role.value if isinstance(role, MessageRole) else role,
            content,
            now,
            token_count,
            importance,
            json.dumps(metadata or {}, ensure_ascii=False)
        ))

        cursor.execute("""
            UPDATE sessions
            SET message_count = message_count + 1,
                total_tokens = total_tokens + ?,
                updated_at = ?
            WHERE id = ?
        """, (token_count, now, session_id))

        conn.commit()

        message = SessionMessage(
            id=message_id,
            session_id=session_id,
            role=role if isinstance(role, MessageRole) else MessageRole(role),
            content=content,
            timestamp=now,
            token_count=token_count,
            importance=importance,
            metadata=metadata or {}
        )

        logger.debug(f"添加消息到会�?{session_id}: {message_id}")
        return message

    def add_messages_batch(
        self,
        session_id: str,
        messages: List[Dict[str, Any]]
    ) -> int:
        """批量添加消息"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if not cursor.fetchone():
            return 0

        now = datetime.now().isoformat()
        total_tokens = 0
        count = 0

        for msg in messages:
            message_id = msg.get("id") or self.generate_id("msg")
            role = msg.get("role", "user")
            content = msg.get("content", "")
            token_count = msg.get("token_count", 0)
            importance = msg.get("importance", 0.5)
            metadata = msg.get("metadata", {})
            timestamp = msg.get("timestamp", now)

            cursor.execute("""
                INSERT INTO session_messages (id, session_id, role, content, timestamp, token_count, importance, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                message_id,
                session_id,
                role,
                content,
                timestamp,
                token_count,
                importance,
                json.dumps(metadata, ensure_ascii=False)
            ))

            total_tokens += token_count
            count += 1

        cursor.execute("""
            UPDATE sessions
            SET message_count = message_count + ?,
                total_tokens = total_tokens + ?,
                updated_at = ?
            WHERE id = ?
        """, (count, total_tokens, now, session_id))

        conn.commit()
        logger.debug(f"批量添加 {count} 条消息到会话 {session_id}")
        return count

    def delete_message(self, session_id: str, message_id: str) -> bool:
        """删除单条消息"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT token_count FROM session_messages
            WHERE session_id = ? AND id = ?
        """, (session_id, message_id))

        row = cursor.fetchone()
        if not row:
            return False

        token_count = row["token_count"]

        cursor.execute("""
            DELETE FROM session_messages
            WHERE session_id = ? AND id = ?
        """, (session_id, message_id))

        cursor.execute("""
            UPDATE sessions
            SET message_count = message_count - 1,
                total_tokens = total_tokens - ?,
                updated_at = ?
            WHERE id = ?
        """, (token_count, datetime.now().isoformat(), session_id))

        conn.commit()
        logger.debug(f"删除消息: {message_id}")
        return True

    def get_messages(
        self,
        session_id: str,
        limit: int = None,
        offset: int = 0,
        roles: List[MessageRole] = None
    ) -> List[SessionMessage]:
        """获取会话消息"""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM session_messages WHERE session_id = ?"
        params = [session_id]

        if roles:
            placeholders = ", ".join("?" * len(roles))
            query += f" AND role IN ({placeholders})"
            params.extend([r.value if isinstance(r, MessageRole) else r for r in roles])

        query += " ORDER BY timestamp ASC"

        if limit:
            query += f" LIMIT {limit} OFFSET {offset}"

        cursor.execute(query, params)

        messages = []
        for row in cursor.fetchall():
            messages.append(SessionMessage(
                id=row["id"],
                session_id=row["session_id"],
                role=MessageRole(row["role"]),
                content=row["content"],
                timestamp=row["timestamp"],
                token_count=row["token_count"],
                importance=row["importance"],
                metadata=json.loads(row["metadata"] or "{}")
            ))

        return messages

    def search_sessions(
        self,
        query: str = None,
        tags: List[str] = None,
        status: SessionStatus = None,
        starred: bool = None,
        pinned: bool = None,
        model_id: str = None,
        start_date: str = None,
        end_date: str = None,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "updated_at",
        order_desc: bool = True
    ) -> Tuple[List[ChatSession], int]:
        """搜索会话"""
        conn = self._get_connection()
        cursor = conn.cursor()

        conditions = ["s.status != ?"]
        params = [SessionStatus.DELETED.value]

        if query:
            conditions.append("(s.title LIKE ? OR s.description LIKE ?)")
            search_term = f"%{query}%"
            params.extend([search_term, search_term])

        if tags:
            placeholders = ", ".join("?" * len(tags))
            conditions.append(f"""
                s.id IN (
                    SELECT session_id FROM session_tags
                    WHERE tag IN ({placeholders})
                    GROUP BY session_id
                    HAVING COUNT(DISTINCT tag) = ?
                )
            """)
            params.extend(tags)
            params.append(len(tags))

        if status:
            conditions.append("s.status = ?")
            params.append(status.value)

        if starred is not None:
            conditions.append("s.starred = ?")
            params.append(1 if starred else 0)

        if pinned is not None:
            conditions.append("s.pinned = ?")
            params.append(1 if pinned else 0)

        if model_id:
            conditions.append("s.model_id = ?")
            params.append(model_id)

        if start_date:
            conditions.append("s.created_at >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("s.created_at <= ?")
            params.append(end_date)

        where_clause = " AND ".join(conditions)
        order_direction = "DESC" if order_desc else "ASC"

        valid_order_columns = {"created_at", "updated_at", "title", "message_count", "total_tokens"}
        if order_by not in valid_order_columns:
            order_by = "updated_at"

        count_query = f"SELECT COUNT(*) FROM sessions s WHERE {where_clause}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        query_str = f"""
            SELECT s.* FROM sessions s
            WHERE {where_clause}
            ORDER BY s.pinned DESC, s.{order_by} {order_direction}
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        cursor.execute(query_str, params)
        rows = cursor.fetchall()

        sessions = []
        for row in rows:
            cursor.execute("""
                SELECT tag FROM session_tags WHERE session_id = ?
            """, (row["id"],))
            session_tags = [r["tag"] for r in cursor.fetchall()]

            metadata = SessionMetadata(
                title=row["title"],
                description=row["description"] or "",
                model_id=row["model_id"] or "",
                tags=session_tags,
                status=SessionStatus(row["status"]),
                starred=bool(row["starred"]),
                pinned=bool(row["pinned"]),
                custom_data=json.loads(row["custom_data"] or "{}")
            )

            sessions.append(ChatSession(
                id=row["id"],
                metadata=metadata,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                message_count=row["message_count"],
                total_tokens=row["total_tokens"]
            ))

        return sessions, total

    def get_all_tags(self) -> List[Dict[str, Any]]:
        """获取所有标签及其使用次�?""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT tag, COUNT(*) as count
            FROM session_tags
            WHERE session_id IN (SELECT id FROM sessions WHERE status != ?)
            GROUP BY tag
            ORDER BY count DESC
        """, (SessionStatus.DELETED.value,))

        return [{"tag": row["tag"], "count": row["count"]} for row in cursor.fetchall()]

    def restore_session(self, session_id: str) -> Optional[ChatSession]:
        """恢复已删除的会话"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE sessions SET status = ?, updated_at = ?
            WHERE id = ? AND status = ?
        """, (SessionStatus.ACTIVE.value, datetime.now().isoformat(), session_id, SessionStatus.DELETED.value))

        if cursor.rowcount == 0:
            return None

        conn.commit()
        logger.info(f"恢复会话: {session_id}")
        return self.get_session(session_id)

    def archive_session(self, session_id: str) -> bool:
        """归档会话"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE sessions SET status = ?, updated_at = ?
            WHERE id = ?
        """, (SessionStatus.ARCHIVED.value, datetime.now().isoformat(), session_id))

        success = cursor.rowcount > 0
        conn.commit()

        if success:
            logger.info(f"归档会话: {session_id}")
        return success

    def get_statistics(self) -> Dict[str, Any]:
        """获取会话统计信息"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM sessions
            GROUP BY status
        """)
        status_counts = {row["status"]: row["count"] for row in cursor.fetchall()}

        cursor.execute("SELECT SUM(message_count) FROM sessions WHERE status != ?", (SessionStatus.DELETED.value,))
        total_messages = cursor.fetchone()[0] or 0

        cursor.execute("SELECT SUM(total_tokens) FROM sessions WHERE status != ?", (SessionStatus.DELETED.value,))
        total_tokens = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT COUNT(DISTINCT session_id)
            FROM session_messages
            WHERE timestamp >= datetime('now', '-7 days')
        """)
        active_sessions_7d = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(DISTINCT session_id)
            FROM session_messages
            WHERE timestamp >= datetime('now', '-30 days')
        """)
        active_sessions_30d = cursor.fetchone()[0]

        return {
            "total_sessions": sum(status_counts.values()),
            "active_sessions": status_counts.get(SessionStatus.ACTIVE.value, 0),
            "archived_sessions": status_counts.get(SessionStatus.ARCHIVED.value, 0),
            "deleted_sessions": status_counts.get(SessionStatus.DELETED.value, 0),
            "total_messages": total_messages,
            "total_tokens": total_tokens,
            "active_sessions_7d": active_sessions_7d,
            "active_sessions_30d": active_sessions_30d
        }

    def export_session(self, session_id: str, format: str = "json") -> Optional[str]:
        """导出会话"""
        session = self.get_session(session_id, include_messages=True)
        if not session:
            return None

        if format == "json":
            export_data = {
                "session": session.to_dict(),
                "messages": [msg.to_dict() for msg in session.messages],
                "exported_at": datetime.now().isoformat()
            }
            return json.dumps(export_data, ensure_ascii=False, indent=2)

        elif format == "markdown":
            lines = [
                f"# {session.metadata.title}",
                f"",
                f"- 创建时间: {session.created_at}",
                f"- 模型: {session.metadata.model_id}",
                f"- 标签: {', '.join(session.metadata.tags)}",
                f"- 消息�? {session.message_count}",
                f"",
                "---",
                f""
            ]

            for msg in session.messages:
                role_label = {
                    MessageRole.SYSTEM: "System",
                    MessageRole.USER: "User",
                    MessageRole.ASSISTANT: "Assistant",
                    MessageRole.FUNCTION: "Function"
                }.get(msg.role, msg.role.value)
                lines.append(f"## {role_label}")
                lines.append(f"")
                lines.append(msg.content)
                lines.append(f"")
                lines.append(f"*{msg.timestamp}*")
                lines.append(f"")
                lines.append("---")
                lines.append(f"")

            return "\n".join(lines)

        return None

    def close(self):
        """关闭数据库连�?""
        if hasattr(self._thread_local, 'connection'):
            try:
                self._thread_local.connection.close()
                del self._thread_local.connection
                logger.debug("会话存储数据库连接已关闭")
            except Exception as e:
                logger.warning(f"关闭数据库连接失�? {e}")


_session_store: Optional[SessionStore] = None
_store_lock = threading.Lock()


def get_session_store(db_path: str = None) -> SessionStore:
    """获取会话存储实例"""
    global _session_store
    with _store_lock:
        if _session_store is None:
            _session_store = SessionStore(db_path)
        return _session_store


def init_session_store(db_path: str) -> SessionStore:
    """初始化会话存�?""
    global _session_store
    with _store_lock:
        _session_store = SessionStore(db_path)
        return _session_store
