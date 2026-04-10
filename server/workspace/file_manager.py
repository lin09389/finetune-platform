"""
文件管理器
提供文件的上传、下载、删除和管理功能
"""
import hashlib
import json
import logging
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from core.config import settings
from core.db_manager import get_db_pool
from workspace.models import (
    FILE_TYPE_EXTENSIONS,
    FileInfo,
    FileMetadata,
    FileType,
    FileUploadResult,
)
from workspace.project_manager import get_project_manager

logger = logging.getLogger(__name__)


class FileManager:
    """
    文件管理器

    功能：
    - 文件上传、下载、删除
    - 文件元数据管理
    - 文件类型检测
    - 内容哈希计算
    - 线程安全访问
    """

    _instance: Optional['FileManager'] = None
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

        self._files: dict[str, FileInfo] = {}
        self._files_lock = threading.RLock()
        self._storage_dir = settings.base_dir / "data" / "workspaces"
        self._db_path = self._storage_dir / "projects.db"
        self._initialized = True

        self._init_database()
        self._load_files()

        logger.info("文件管理器已初始化")

    def _init_database(self):
        """初始化数据库表"""
        db_pool = get_db_pool(str(self._db_path))

        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    file_type TEXT DEFAULT 'other',
                    size INTEGER DEFAULT 0,
                    content_hash TEXT,
                    current_version INTEGER DEFAULT 1,
                    version_count INTEGER DEFAULT 1,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    tags TEXT,
                    UNIQUE(project_id, path),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_files_project ON files(project_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_files_path ON files(path)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_files_type ON files(file_type)
            """)
            logger.debug("文件数据库表已初始化")

    def _load_files(self):
        """从数据库加载文件"""
        db_pool = get_db_pool(str(self._db_path))

        rows = db_pool.execute_query("SELECT * FROM files")

        with self._files_lock:
            for row in rows:
                metadata = json.loads(row['metadata']) if row['metadata'] else {}
                file_info = FileInfo(
                    id=row['id'],
                    project_id=row['project_id'],
                    path=row['path'],
                    name=row['name'],
                    file_type=row['file_type'],
                    size=row['size'],
                    content_hash=row['content_hash'],
                    current_version=row['current_version'],
                    version_count=row['version_count'],
                    metadata=FileMetadata(**metadata) if metadata else FileMetadata(),
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    tags=json.loads(row['tags']) if row['tags'] else [],
                )
                self._files[file_info.id] = file_info

        logger.info(f"已加载 {len(self._files)} 个文件")

    def _save_file(self, file_info: FileInfo):
        """保存文件到数据库"""
        db_pool = get_db_pool(str(self._db_path))

        db_pool.execute_update("""
            INSERT OR REPLACE INTO files
            (id, project_id, path, name, file_type, size, content_hash,
             current_version, version_count, metadata, created_at, updated_at, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            file_info.id,
            file_info.project_id,
            file_info.path,
            file_info.name,
            file_info.file_type,
            file_info.size,
            file_info.content_hash,
            file_info.current_version,
            file_info.version_count,
            file_info.metadata.model_dump_json(),
            file_info.created_at,
            file_info.updated_at,
            json.dumps(file_info.tags),
        ))

    def _detect_file_type(self, filename: str) -> FileType:
        """检测文件类型"""
        ext = Path(filename).suffix.lower()

        for file_type, extensions in FILE_TYPE_EXTENSIONS.items():
            if ext in extensions:
                return file_type

        return FileType.OTHER

    def _compute_hash(self, content: bytes) -> str:
        """计算内容哈希"""
        return hashlib.sha256(content).hexdigest()

    def _get_file_path(self, project_id: str, file_path: str) -> Path:
        """获取文件物理路径"""
        return self._storage_dir / project_id / "files" / file_path

    def upload_file(
        self,
        project_id: str,
        file_path: str,
        content: bytes,
        message: str | None = None,
        author: str | None = None,
    ) -> FileUploadResult:
        """
        上传文件

        Args:
            project_id: 项目ID
            file_path: 文件相对路径
            content: 文件内容
            message: 版本说明
            author: 作者
        Returns:
            上传结果
        """
        project_manager = get_project_manager()
        project = project_manager.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在：{project_id}")

        content_hash = self._compute_hash(content)
        filename = Path(file_path).name
        file_type = self._detect_file_type(filename)

        with self._files_lock:
            existing_file = None
            for f in self._files.values():
                if f.project_id == project_id and f.path == file_path:
                    existing_file = f
                    break

            if existing_file:
                if existing_file.content_hash == content_hash:
                    return FileUploadResult(
                        file_id=existing_file.id,
                        path=file_path,
                        size=existing_file.size,
                        version=existing_file.current_version,
                        is_new=False,
                        message="文件内容未变化",
                    )

                existing_file.current_version += 1
                existing_file.version_count += 1
                existing_file.content_hash = content_hash
                existing_file.size = len(content)
                existing_file.updated_at = datetime.now().isoformat()

                self._save_file(existing_file)

                physical_path = self._get_file_path(project_id, file_path)
                physical_path.parent.mkdir(parents=True, exist_ok=True)
                physical_path.write_bytes(content)

                from workspace.version_control import get_version_control
                version_control = get_version_control()
                version_control.create_version(
                    file_id=existing_file.id,
                    content=content,
                    content_hash=content_hash,
                    message=message or f"更新文件 {filename}",
                    author=author,
                )

                self._update_project_stats(project_id)

                return FileUploadResult(
                    file_id=existing_file.id,
                    path=file_path,
                    size=len(content),
                    version=existing_file.current_version,
                    is_new=False,
                    message="文件已更新",
                )

            file_info = FileInfo(
                project_id=project_id,
                path=file_path,
                name=filename,
                file_type=file_type,
                size=len(content),
                content_hash=content_hash,
            )

            self._files[file_info.id] = file_info
            self._save_file(file_info)

            physical_path = self._get_file_path(project_id, file_path)
            physical_path.parent.mkdir(parents=True, exist_ok=True)
            physical_path.write_bytes(content)

            from workspace.version_control import get_version_control
            version_control = get_version_control()
            version_control.create_version(
                file_id=file_info.id,
                content=content,
                content_hash=content_hash,
                message=message or f"创建文件 {filename}",
                author=author,
            )

            self._update_project_stats(project_id)

            logger.info(f"文件已上传：{file_info.id}, 路径：{file_path}")

            return FileUploadResult(
                file_id=file_info.id,
                path=file_path,
                size=len(content),
                version=1,
                is_new=True,
                message="上传成功",
            )

    def download_file(self, file_id: str, version: int | None = None) -> tuple[bytes, FileInfo] | None:
        """
        下载文件

        Args:
            file_id: 文件ID
            version: 版本号（None 表示最新版本）

        Returns:
            (内容, 文件信息) 或 None
        """
        with self._files_lock:
            file_info = self._files.get(file_id)

        if not file_info:
            return None

        if version and version != file_info.current_version:
            from workspace.version_control import get_version_control
            version_control = get_version_control()
            version_info = version_control.get_version(file_id, version)

            if not version_info:
                return None

            version_path = self._storage_dir / "versions" / version_info.version_id
            if not version_path.exists():
                return None

            content = version_path.read_bytes()
            return content, file_info

        physical_path = self._get_file_path(file_info.project_id, file_info.path)
        if not physical_path.exists():
            return None

        content = physical_path.read_bytes()
        return content, file_info

    def delete_file(self, file_id: str) -> bool:
        """删除文件"""
        with self._files_lock:
            file_info = self._files.get(file_id)
            if not file_info:
                return False

            project_id = file_info.project_id

            del self._files[file_id]

            db_pool = get_db_pool(str(self._db_path))
            db_pool.execute_update("DELETE FROM files WHERE id = ?", (file_id,))

            physical_path = self._get_file_path(file_info.project_id, file_info.path)
            if physical_path.exists():
                physical_path.unlink()

            self._update_project_stats(project_id)

        logger.info(f"文件已删除：{file_id}")
        return True

    def get_file(self, file_id: str) -> FileInfo | None:
        """获取文件信息"""
        with self._files_lock:
            return self._files.get(file_id)

    def get_file_by_path(self, project_id: str, file_path: str) -> FileInfo | None:
        """通过路径获取文件"""
        with self._files_lock:
            for f in self._files.values():
                if f.project_id == project_id and f.path == file_path:
                    return f
        return None

    def list_files(
        self,
        project_id: str,
        file_type: FileType | None = None,
        path_prefix: str | None = None,
    ) -> list[FileInfo]:
        """
        列出文件

        Args:
            project_id: 项目ID
            file_type: 文件类型筛选
            path_prefix: 路径前缀筛选
        """
        with self._files_lock:
            files = [f for f in self._files.values() if f.project_id == project_id]

        if file_type:
            files = [f for f in files if f.file_type == file_type.value]

        if path_prefix:
            files = [f for f in files if f.path.startswith(path_prefix)]

        return sorted(files, key=lambda f: f.path)

    def move_file(self, file_id: str, new_path: str) -> FileInfo | None:
        """移动文件"""
        with self._files_lock:
            file_info = self._files.get(file_id)
            if not file_info:
                return None

            old_path = self._get_file_path(file_info.project_id, file_info.path)
            new_physical_path = self._get_file_path(file_info.project_id, new_path)

            new_physical_path.parent.mkdir(parents=True, exist_ok=True)

            if old_path.exists():
                shutil.move(str(old_path), str(new_physical_path))

            file_info.path = new_path
            file_info.name = Path(new_path).name
            file_info.updated_at = datetime.now().isoformat()

            self._save_file(file_info)

        logger.info(f"文件已移动：{file_id} -> {new_path}")
        return file_info

    def copy_file(self, file_id: str, new_path: str) -> FileInfo | None:
        """复制文件"""
        result = self.download_file(file_id)
        if not result:
            return None

        content, original = result

        upload_result = self.upload_file(
            project_id=original.project_id,
            file_path=new_path,
            content=content,
            message=f"复制自 {original.path}",
        )

        return self.get_file(upload_result.file_id)

    def _update_project_stats(self, project_id: str):
        """更新项目统计"""
        files = self.list_files(project_id)

        file_types: dict[str, int] = {}
        total_size = 0
        version_count = 0

        for f in files:
            file_types[f.file_type] = file_types.get(f.file_type, 0) + 1
            total_size += f.size
            version_count += f.version_count

        project_manager = get_project_manager()
        project_manager.update_statistics(project_id, {
            "file_count": len(files),
            "total_size": total_size,
            "file_types": file_types,
            "version_count": version_count,
        })

    def get_storage_stats(self, project_id: str | None = None) -> dict[str, Any]:
        """
        获取存储统计信息

        Args:
            project_id: 项目ID（可选，不提供则返回所有项目的统计）

        Returns:
            存储统计信息
        """
        with self._files_lock:
            if project_id:
                files = [f for f in self._files.values() if f.project_id == project_id]
            else:
                files = list(self._files.values())

        total_size = sum(f.size for f in files)
        file_count = len(files)

        file_types: dict[str, int] = {}
        for f in files:
            file_types[f.file_type] = file_types.get(f.file_type, 0) + 1

        return {
            "file_count": file_count,
            "total_size": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "file_types": file_types,
            "project_id": project_id,
        }

    def get_file_by_hash(self, content_hash: str) -> FileInfo | None:
        """
        通过内容哈希查找文件（用于秒传）

        Args:
            content_hash: 内容哈希

        Returns:
            文件信息或None
        """
        with self._files_lock:
            for f in self._files.values():
                if f.content_hash == content_hash:
                    return f
        return None

    def check_disk_space(self, required_size: int) -> bool:
        """
        检查磁盘空间是否足够

        Args:
            required_size: 需要的空间大小（字节）

        Returns:
            是否有足够空间
        """
        try:
            import shutil
            total, used, free = shutil.disk_usage(self._storage_dir)
            return free >= required_size
        except Exception as e:
            logger.warning(f"检查磁盘空间失败：{e}")
            return True

    def cleanup_temp_files(self, max_age_hours: int = 24) -> int:
        """
        清理临时文件

        Args:
            max_age_hours: 最大保留时间（小时）

        Returns:
            清理的文件数量
        """
        import time

        temp_dir = self._storage_dir / "temp"
        if not temp_dir.exists():
            return 0

        cleaned = 0
        cutoff_time = time.time() - (max_age_hours * 3600)

        for file_path in temp_dir.rglob("*"):
            if file_path.is_file():
                try:
                    if file_path.stat().st_mtime < cutoff_time:
                        file_path.unlink()
                        cleaned += 1
                except Exception as e:
                    logger.warning(f"清理临时文件失败：{file_path}, 错误：{e}")

        logger.info(f"已清理 {cleaned} 个临时文件")
        return cleaned

    def get_file_tree(self, project_id: str) -> dict[str, Any]:
        """
        获取文件树结构

        Args:
            project_id: 项目ID

        Returns:
            文件树结构
        """
        files = self.list_files(project_id)

        tree = {
            "name": "root",
            "type": "directory",
            "children": {},
        }

        for file_info in files:
            parts = file_info.path.split("/")
            current = tree["children"]

            for _i, part in enumerate(parts[:-1]):
                if part not in current:
                    current[part] = {
                        "name": part,
                        "type": "directory",
                        "children": {},
                    }
                current = current[part]["children"]

            filename = parts[-1]
            current[filename] = {
                "name": filename,
                "type": "file",
                "file_id": file_info.id,
                "size": file_info.size,
                "file_type": file_info.file_type,
                "version": file_info.current_version,
            }

        return tree

    def batch_delete_files(self, file_ids: list[str]) -> dict[str, Any]:
        """
        批量删除文件

        Args:
            file_ids: 文件ID列表

        Returns:
            删除结果
        """
        success_count = 0
        failed = []

        for file_id in file_ids:
            try:
                if self.delete_file(file_id):
                    success_count += 1
                else:
                    failed.append({"file_id": file_id, "reason": "文件不存在"})
            except Exception as e:
                failed.append({"file_id": file_id, "reason": str(e)})

        return {
            "success_count": success_count,
            "failed_count": len(failed),
            "failed": failed,
        }

    def get_recent_files(self, project_id: str, limit: int = 10) -> list[FileInfo]:
        """
        获取最近修改的文件

        Args:
            project_id: 项目ID
            limit: 返回数量

        Returns:
            文件列表
        """
        files = self.list_files(project_id)
        files.sort(key=lambda f: f.updated_at, reverse=True)
        return files[:limit]


_file_manager: FileManager | None = None
_manager_lock = threading.Lock()


def get_file_manager() -> FileManager:
    """获取文件管理器实例"""
    global _file_manager
    with _manager_lock:
        if _file_manager is None:
            _file_manager = FileManager()
        return _file_manager
