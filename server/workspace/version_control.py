"""
版本控制模块
提供文件版本历史记录和管理功能
"""
import json
import logging
import threading
from dataclasses import dataclass
from typing import Optional

from core.config import settings
from core.db_manager import get_db_pool
from workspace.models import FileVersion, FileVersionDiff

logger = logging.getLogger(__name__)


@dataclass
class VersionDiff:
    """版本差异"""
    additions: int
    deletions: int
    changes: list[dict]


class VersionControl:
    """
    版本控制器

    功能：
    - 创建文件版本
    - 获取版本历史
    - 版本对比
    - 版本回滚
    - 线程安全访问
    """

    _instance: Optional['VersionControl'] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._versions: dict[str, FileVersion] = {}
        self._file_versions: dict[str, list[str]] = {}
        self._versions_lock = threading.RLock()
        self._storage_dir = settings.base_dir / "data" / "workspaces"
        self._db_path = self._storage_dir / "projects.db"
        self._versions_dir = self._storage_dir / "versions"
        self._initialized = True

        self._init_database()
        self._init_storage()
        self._load_versions()

        logger.info("版本控制器已初始化")

    def _init_database(self):
        """初始化数据库表"""
        db_pool = get_db_pool(str(self._db_path))

        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS file_versions (
                    version_id TEXT PRIMARY KEY,
                    file_id TEXT NOT NULL,
                    version_number INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    message TEXT,
                    author TEXT,
                    created_at TEXT NOT NULL,
                    metadata TEXT,
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                    UNIQUE(file_id, version_number)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_versions_file ON file_versions(file_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_versions_number ON file_versions(file_id, version_number)
            """)
            logger.debug("版本数据库表已初始化")

    def _init_storage(self):
        """初始化版本存储目录"""
        self._versions_dir.mkdir(parents=True, exist_ok=True)

    def _load_versions(self):
        """从数据库加载版本"""
        db_pool = get_db_pool(str(self._db_path))

        rows = db_pool.execute_query("SELECT * FROM file_versions ORDER BY version_number")

        with self._versions_lock:
            for row in rows:
                version = FileVersion(
                    version_id=row['version_id'],
                    file_id=row['file_id'],
                    version_number=row['version_number'],
                    content_hash=row['content_hash'],
                    size=row['size'],
                    message=row['message'],
                    author=row['author'],
                    created_at=row['created_at'],
                    metadata=json.loads(row['metadata']) if row['metadata'] else {},
                )
                self._versions[version.version_id] = version

                if version.file_id not in self._file_versions:
                    self._file_versions[version.file_id] = []
                self._file_versions[version.file_id].append(version.version_id)

        logger.info(f"已加载 {len(self._versions)} 个版本")

    def _save_version(self, version: FileVersion):
        """保存版本到数据库"""
        db_pool = get_db_pool(str(self._db_path))

        db_pool.execute_update("""
            INSERT INTO file_versions
            (version_id, file_id, version_number, content_hash, size, message, author, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(version_id) DO UPDATE SET
                content_hash=excluded.content_hash,
                size=excluded.size,
                message=excluded.message,
                metadata=excluded.metadata
        """, (
            version.version_id,
            version.file_id,
            version.version_number,
            version.content_hash,
            version.size,
            version.message,
            version.author,
            version.created_at,
            json.dumps(version.metadata),
        ))

    def create_version(
        self,
        file_id: str,
        content: bytes,
        content_hash: str,
        message: str | None = None,
        author: str | None = None,
        metadata: dict | None = None,
    ) -> FileVersion:
        """
        创建新版本

        Args:
            file_id: 文件ID
            content: 文件内容
            content_hash: 内容哈希
            message: 版本说明
            author: 作者
            metadata: 元数据

        Returns:
            版本信息
        """
        with self._versions_lock:
            version_number = len(self._file_versions.get(file_id, [])) + 1

            version = FileVersion(
                file_id=file_id,
                version_number=version_number,
                content_hash=content_hash,
                size=len(content),
                message=message,
                author=author,
                metadata=metadata or {},
            )

            self._versions[version.version_id] = version

            if file_id not in self._file_versions:
                self._file_versions[file_id] = []
            self._file_versions[file_id].append(version.version_id)

            self._save_version(version)

            version_path = self._versions_dir / version.version_id
            version_path.write_bytes(content)

        logger.info(f"版本已创建：{version.version_id}, 文件：{file_id}, 版本号：{version_number}")
        return version

    def get_version(self, file_id: str, version_number: int) -> FileVersion | None:
        """获取指定版本"""
        with self._versions_lock:
            version_ids = self._file_versions.get(file_id, [])

            for vid in version_ids:
                version = self._versions.get(vid)
                if version and version.version_number == version_number:
                    return version

        return None

    def get_latest_version(self, file_id: str) -> FileVersion | None:
        """获取最新版本"""
        with self._versions_lock:
            version_ids = self._file_versions.get(file_id, [])

            if not version_ids:
                return None

            return self._versions.get(version_ids[-1])

    def get_version_history(
        self,
        file_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FileVersion]:
        """
        获取版本历史

        Args:
            file_id: 文件ID
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            版本列表（按版本号倒序）
        """
        with self._versions_lock:
            version_ids = self._file_versions.get(file_id, [])

            versions = []
            for vid in reversed(version_ids[offset:offset + limit]):
                version = self._versions.get(vid)
                if version:
                    versions.append(version)

            return versions

    def get_version_content(self, version_id: str) -> bytes | None:
        """获取版本内容"""
        version_path = self._versions_dir / version_id

        if not version_path.exists():
            return None

        return version_path.read_bytes()

    def compare_versions(
        self,
        file_id: str,
        version_from: int,
        version_to: int,
    ) -> FileVersionDiff | None:
        """
        对比两个版本

        Args:
            file_id: 文件ID
            version_from: 起始版本
            version_to: 目标版本

        Returns:
            版本差异
        """
        v1 = self.get_version(file_id, version_from)
        v2 = self.get_version(file_id, version_to)

        if not v1 or not v2:
            return None

        content1 = self.get_version_content(v1.version_id)
        content2 = self.get_version_content(v2.version_id)

        if content1 is None or content2 is None:
            return None

        try:
            lines1 = content1.decode('utf-8').splitlines()
            lines2 = content2.decode('utf-8').splitlines()
        except UnicodeDecodeError:
            return FileVersionDiff(
                version_from=version_from,
                version_to=version_to,
                additions=0,
                deletions=0,
                changes=[{"type": "binary", "message": "二进制文件无法对比"}],
            )

        diff = self._compute_diff(lines1, lines2)

        return FileVersionDiff(
            version_from=version_from,
            version_to=version_to,
            additions=diff.additions,
            deletions=diff.deletions,
            changes=diff.changes,
        )

    def _compute_diff(self, lines1: list[str], lines2: list[str]) -> VersionDiff:
        """计算行差异"""
        additions = 0
        deletions = 0
        changes = []

        from difflib import SequenceMatcher
        matcher = SequenceMatcher(None, lines1, lines2)

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'replace':
                deletions += i2 - i1
                additions += j2 - j1
                changes.append({
                    "type": "replace",
                    "old_start": i1 + 1,
                    "old_end": i2,
                    "new_start": j1 + 1,
                    "new_end": j2,
                    "old_lines": lines1[i1:i2],
                    "new_lines": lines2[j1:j2],
                })
            elif tag == 'delete':
                deletions += i2 - i1
                changes.append({
                    "type": "delete",
                    "start": i1 + 1,
                    "end": i2,
                    "lines": lines1[i1:i2],
                })
            elif tag == 'insert':
                additions += j2 - j1
                changes.append({
                    "type": "insert",
                    "start": j1 + 1,
                    "end": j2,
                    "lines": lines2[j1:j2],
                })

        return VersionDiff(additions=additions, deletions=deletions, changes=changes)

    def rollback_to_version(self, file_id: str, version_number: int) -> bytes | None:
        """
        回滚到指定版本

        Args:
            file_id: 文件ID
            version_number: 目标版本号

        Returns:
            版本内容
        """
        version = self.get_version(file_id, version_number)
        if not version:
            return None

        content = self.get_version_content(version.version_id)
        if content is None:
            return None

        return content

    def delete_version(self, version_id: str) -> bool:
        """删除版本"""
        with self._versions_lock:
            version = self._versions.get(version_id)
            if not version:
                return False

            file_id = version.file_id

            del self._versions[version_id]

            if file_id in self._file_versions:
                self._file_versions[file_id] = [
                    vid for vid in self._file_versions[file_id] if vid != version_id
                ]

            db_pool = get_db_pool(str(self._db_path))
            db_pool.execute_update("DELETE FROM file_versions WHERE version_id = ?", (version_id,))

            version_path = self._versions_dir / version_id
            if version_path.exists():
                version_path.unlink()

        logger.info(f"版本已删除：{version_id}")
        return True

    def get_version_count(self, file_id: str) -> int:
        """获取文件版本数量"""
        with self._versions_lock:
            return len(self._file_versions.get(file_id, []))

    def cleanup_old_versions(self, file_id: str, keep_count: int = 10) -> int:
        """
        清理旧版本，保留最近的 N 个版本

        Args:
            file_id: 文件ID
            keep_count: 保留数量

        Returns:
            删除的版本数量
        """
        with self._versions_lock:
            version_ids = self._file_versions.get(file_id, [])

            if len(version_ids) <= keep_count:
                return 0

            to_delete = version_ids[:-keep_count]
            deleted = 0

            for vid in to_delete:
                version = self._versions.get(vid)
                if version:
                    del self._versions[vid]

                    db_pool = get_db_pool(str(self._db_path))
                    db_pool.execute_update("DELETE FROM file_versions WHERE version_id = ?", (vid,))

                    version_path = self._versions_dir / vid
                    if version_path.exists():
                        version_path.unlink()

                    deleted += 1

            self._file_versions[file_id] = version_ids[-keep_count:]

        logger.info(f"已清理 {deleted} 个旧版本，文件：{file_id}")
        return deleted


_version_control: VersionControl | None = None
_manager_lock = threading.Lock()


def get_version_control() -> VersionControl:
    """获取版本控制器实例"""
    global _version_control
    with _manager_lock:
        if _version_control is None:
            _version_control = VersionControl()
        return _version_control
