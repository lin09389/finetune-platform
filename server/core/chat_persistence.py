"""
数据持久化服务
提供对话、分支、分享等数据的数据库存储
"""
import json
import logging
from datetime import datetime

from core.db_manager import get_db_pool

logger = logging.getLogger(__name__)


class ChatPersistenceService:
    """对话数据持久化服务"""

    def __init__(self, db_path: str = "data/chat.db"):
        self.db_path = db_path
        self._init_tables()

    def _init_tables(self):
        """初始化数据库表"""
        pool = get_db_pool(self.db_path)

        with pool.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    model_id TEXT,
                    backend TEXT DEFAULT 'ollama',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    parent_id TEXT,
                    branch_id TEXT,
                    metadata TEXT,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_branches (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    root_message_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    message_count INTEGER DEFAULT 0,
                    metadata TEXT,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_shares (
                    share_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    title TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    view_count INTEGER DEFAULT 0,
                    is_public INTEGER DEFAULT 1,
                    messages TEXT,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session
                ON chat_messages(session_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_parent
                ON chat_messages(parent_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_branches_session
                ON chat_branches(session_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_shares_session
                ON chat_shares(session_id)
            """)

            logger.info("对话数据库表初始化完成")

    def create_session(self, session_id: str, title: str = "",
                       model_id: str = None, backend: str = "ollama",
                       metadata: dict = None) -> dict:
        """创建对话会话"""
        pool = get_db_pool(self.db_path)

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_sessions (id, title, model_id, backend, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (session_id, title, model_id, backend,
                  json.dumps(metadata) if metadata else None))

            return {
                "id": session_id,
                "title": title,
                "model_id": model_id,
                "backend": backend,
                "created_at": datetime.now().isoformat(),
                "metadata": metadata
            }

    def get_session(self, session_id: str) -> dict | None:
        """获取对话会话"""
        pool = get_db_pool(self.db_path)

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, model_id, backend, created_at, updated_at, metadata
                FROM chat_sessions WHERE id = ?
            """, (session_id,))

            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "title": row[1],
                    "model_id": row[2],
                    "backend": row[3],
                    "created_at": row[4],
                    "updated_at": row[5],
                    "metadata": json.loads(row[6]) if row[6] else None
                }
            return None

    def list_sessions(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """列出对话会话"""
        pool = get_db_pool(self.db_path)

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, model_id, backend, created_at, updated_at
                FROM chat_sessions
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))

            sessions = []
            for row in cursor.fetchall():
                sessions.append({
                    "id": row[0],
                    "title": row[1],
                    "model_id": row[2],
                    "backend": row[3],
                    "created_at": row[4],
                    "updated_at": row[5]
                })
            return sessions

    def delete_session(self, session_id: str) -> bool:
        """删除对话会话（级联删除消息、分支、分享）"""
        pool = get_db_pool(self.db_path)

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
            return cursor.rowcount > 0

    def add_message(self, message_id: str, session_id: str, role: str,
                    content: str, parent_id: str = None,
                    branch_id: str = None, metadata: dict = None) -> dict:
        """添加消息"""
        pool = get_db_pool(self.db_path)

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_messages
                (id, session_id, role, content, parent_id, branch_id, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (message_id, session_id, role, content, parent_id, branch_id,
                  json.dumps(metadata) if metadata else None))

            cursor.execute("""
                UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (session_id,))

            return {
                "id": message_id,
                "session_id": session_id,
                "role": role,
                "content": content,
                "parent_id": parent_id,
                "branch_id": branch_id,
                "timestamp": datetime.now().isoformat(),
                "metadata": metadata
            }

    def get_messages(self, session_id: str, branch_id: str = None) -> list[dict]:
        """获取会话消息"""
        pool = get_db_pool(self.db_path)

        with pool.get_connection() as conn:
            cursor = conn.cursor()

            if branch_id:
                cursor.execute("""
                    SELECT id, session_id, role, content, timestamp, parent_id, branch_id, metadata
                    FROM chat_messages
                    WHERE session_id = ? AND (branch_id = ? OR branch_id IS NULL)
                    ORDER BY timestamp ASC
                """, (session_id, branch_id))
            else:
                cursor.execute("""
                    SELECT id, session_id, role, content, timestamp, parent_id, branch_id, metadata
                    FROM chat_messages
                    WHERE session_id = ?
                    ORDER BY timestamp ASC
                """, (session_id,))

            messages = []
            for row in cursor.fetchall():
                messages.append({
                    "id": row[0],
                    "session_id": row[1],
                    "role": row[2],
                    "content": row[3],
                    "timestamp": row[4],
                    "parent_id": row[5],
                    "branch_id": row[6],
                    "metadata": json.loads(row[7]) if row[7] else None
                })
            return messages

    def delete_message(self, message_id: str) -> bool:
        """删除消息"""
        pool = get_db_pool(self.db_path)

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chat_messages WHERE id = ?", (message_id,))
            return cursor.rowcount > 0

    def create_branch(self, branch_id: str, session_id: str, name: str,
                      root_message_id: str = None, metadata: dict = None) -> dict:
        """创建分支"""
        pool = get_db_pool(self.db_path)

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_branches (id, session_id, name, root_message_id, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (branch_id, session_id, name, root_message_id,
                  json.dumps(metadata) if metadata else None))

            return {
                "id": branch_id,
                "session_id": session_id,
                "name": name,
                "root_message_id": root_message_id,
                "created_at": datetime.now().isoformat(),
                "message_count": 0,
                "metadata": metadata
            }

    def get_branches(self, session_id: str) -> list[dict]:
        """获取会话分支列表"""
        pool = get_db_pool(self.db_path)

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, session_id, name, root_message_id, created_at, message_count, metadata
                FROM chat_branches
                WHERE session_id = ?
                ORDER BY created_at ASC
            """, (session_id,))

            branches = []
            for row in cursor.fetchall():
                branches.append({
                    "id": row[0],
                    "session_id": row[1],
                    "name": row[2],
                    "root_message_id": row[3],
                    "created_at": row[4],
                    "message_count": row[5],
                    "metadata": json.loads(row[6]) if row[6] else None
                })
            return branches

    def delete_branch(self, branch_id: str) -> bool:
        """删除分支"""
        pool = get_db_pool(self.db_path)

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chat_messages WHERE branch_id = ?", (branch_id,))
            cursor.execute("DELETE FROM chat_branches WHERE id = ?", (branch_id,))
            return cursor.rowcount > 0

    def create_share(self, share_id: str, session_id: str, title: str,
                     messages: list[dict], expires_at: str = None,
                     is_public: bool = True) -> dict:
        """创建分享"""
        pool = get_db_pool(self.db_path)

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_shares
                (share_id, session_id, title, messages, expires_at, is_public)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (share_id, session_id, title, json.dumps(messages),
                  expires_at, 1 if is_public else 0))

            return {
                "share_id": share_id,
                "session_id": session_id,
                "title": title,
                "messages": messages,
                "created_at": datetime.now().isoformat(),
                "expires_at": expires_at,
                "is_public": is_public,
                "view_count": 0
            }

    def get_share(self, share_id: str) -> dict | None:
        """获取分享"""
        pool = get_db_pool(self.db_path)

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT share_id, session_id, title, created_at, expires_at,
                       view_count, is_public, messages
                FROM chat_shares WHERE share_id = ?
            """, (share_id,))

            row = cursor.fetchone()
            if row:
                return {
                    "share_id": row[0],
                    "session_id": row[1],
                    "title": row[2],
                    "created_at": row[3],
                    "expires_at": row[4],
                    "view_count": row[5],
                    "is_public": bool(row[6]),
                    "messages": json.loads(row[7]) if row[7] else []
                }
            return None

    def increment_view_count(self, share_id: str):
        """增加分享浏览次数"""
        pool = get_db_pool(self.db_path)

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE chat_shares SET view_count = view_count + 1
                WHERE share_id = ?
            """, (share_id,))

    def delete_share(self, share_id: str) -> bool:
        """删除分享"""
        pool = get_db_pool(self.db_path)

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chat_shares WHERE share_id = ?", (share_id,))
            return cursor.rowcount > 0

    def cleanup_expired_shares(self) -> int:
        """清理过期分享"""
        pool = get_db_pool(self.db_path)

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM chat_shares
                WHERE expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP
            """)
            deleted_count = cursor.rowcount
            if deleted_count > 0:
                logger.info(f"已清理 {deleted_count} 个过期分享")
            return deleted_count


_chat_persistence: ChatPersistenceService | None = None


def get_chat_persistence(db_path: str = "data/chat.db") -> ChatPersistenceService:
    """获取对话持久化服务实例"""
    global _chat_persistence
    if _chat_persistence is None:
        _chat_persistence = ChatPersistenceService(db_path)
    return _chat_persistence
