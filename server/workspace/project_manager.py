"""
项目管理器
提供项目的 CRUD 操作和存储管理
"""
import json
import logging
import threading
from datetime import datetime
from typing import Optional

from core.config import settings
from core.db_manager import get_db_pool
from workspace.models import (
    Project,
    ProjectCreate,
    ProjectStatistics,
    ProjectStatus,
    ProjectUpdate,
)

logger = logging.getLogger(__name__)


class ProjectManager:
    """
    项目管理器
    
    功能：
    - 项目 CRUD 操作
    - 项目持久化存储（SQLite + JSON 备份）
    - 项目统计信息
    - 线程安全访问
    """

    _instance: Optional['ProjectManager'] = None
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

        self._projects: dict[str, Project] = {}
        self._projects_lock = threading.RLock()
        self._storage_dir = settings.base_dir / "data" / "workspaces"
        self._db_path = self._storage_dir / "projects.db"
        self._initialized = True

        self._ensure_storage()
        self._init_database()
        self._load_projects()

        logger.info(f"项目管理器已初始化，存储目录：{self._storage_dir}")

    def _ensure_storage(self):
        """确保存储目录存在"""
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def _init_database(self):
        """初始化数据库表"""
        db_pool = get_db_pool(str(self._db_path))

        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    tags TEXT,
                    status TEXT DEFAULT 'active',
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    file_count INTEGER DEFAULT 0,
                    total_size INTEGER DEFAULT 0
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name)
            """)
            logger.debug("项目数据库表已初始化")

    def _load_projects(self):
        """从数据库加载项目"""
        db_pool = get_db_pool(str(self._db_path))

        rows = db_pool.execute_query("SELECT * FROM projects WHERE status != ?", ("deleted",))

        with self._projects_lock:
            for row in rows:
                project = Project(
                    id=row['id'],
                    name=row['name'],
                    description=row['description'],
                    tags=json.loads(row['tags']) if row['tags'] else [],
                    status=row['status'],
                    metadata=json.loads(row['metadata']) if row['metadata'] else {},
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    file_count=row['file_count'] or 0,
                    total_size=row['total_size'] or 0,
                )
                self._projects[project.id] = project

        logger.info(f"已加载 {len(self._projects)} 个项目")

    def _save_project(self, project: Project):
        """保存项目到数据库"""
        db_pool = get_db_pool(str(self._db_path))

        db_pool.execute_update("""
            INSERT OR REPLACE INTO projects 
            (id, name, description, tags, status, metadata, created_at, updated_at, file_count, total_size)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            project.id,
            project.name,
            project.description,
            json.dumps(project.tags),
            project.status,
            json.dumps(project.metadata),
            project.created_at,
            project.updated_at,
            project.file_count,
            project.total_size,
        ))

    def create_project(self, data: ProjectCreate) -> Project:
        """创建项目"""
        project = Project(
            name=data.name,
            description=data.description,
            tags=data.tags,
            metadata=data.metadata,
        )

        project_dir = self._storage_dir / project.id
        project_dir.mkdir(parents=True, exist_ok=True)

        with self._projects_lock:
            self._projects[project.id] = project

        self._save_project(project)

        logger.info(f"项目已创建：{project.id}, 名称：{project.name}")
        return project

    def get_project(self, project_id: str) -> Project | None:
        """获取项目"""
        with self._projects_lock:
            return self._projects.get(project_id)

    def list_projects(
        self,
        status: ProjectStatus | None = None,
        tags: list[str] | None = None,
        search: str | None = None,
    ) -> list[Project]:
        """
        列出项目
        
        Args:
            status: 按状态筛选
            tags: 按标签筛选
            search: 搜索名称或描述
        """
        with self._projects_lock:
            projects = list(self._projects.values())

        if status:
            projects = [p for p in projects if p.status == status.value]

        if tags:
            projects = [p for p in projects if any(tag in p.tags for tag in tags)]

        if search:
            search_lower = search.lower()
            projects = [
                p for p in projects
                if search_lower in p.name.lower() or
                   (p.description and search_lower in p.description.lower())
            ]

        return sorted(projects, key=lambda p: p.updated_at, reverse=True)

    def update_project(self, project_id: str, data: ProjectUpdate) -> Project | None:
        """更新项目"""
        with self._projects_lock:
            project = self._projects.get(project_id)
            if not project:
                return None

            update_data = data.model_dump(exclude_unset=True)

            for key, value in update_data.items():
                if hasattr(project, key):
                    setattr(project, key, value)

            project.updated_at = datetime.now().isoformat()

            self._save_project(project)

        logger.info(f"项目已更新：{project_id}")
        return project

    def delete_project(self, project_id: str, hard: bool = False) -> bool:
        """
        删除项目
        
        Args:
            project_id: 项目ID
            hard: 是否硬删除（物理删除）
        """
        with self._projects_lock:
            project = self._projects.get(project_id)
            if not project:
                return False

            if hard:
                del self._projects[project_id]
                db_pool = get_db_pool(str(self._db_path))
                db_pool.execute_update("DELETE FROM projects WHERE id = ?", (project_id,))

                import shutil
                project_dir = self._storage_dir / project_id
                if project_dir.exists():
                    shutil.rmtree(project_dir)

                logger.info(f"项目已硬删除：{project_id}")
            else:
                project.status = ProjectStatus.DELETED.value
                project.updated_at = datetime.now().isoformat()
                self._save_project(project)

                logger.info(f"项目已软删除：{project_id}")

        return True

    def restore_project(self, project_id: str) -> Project | None:
        """恢复已删除的项目"""
        db_pool = get_db_pool(str(self._db_path))

        row = db_pool.execute_one(
            "SELECT * FROM projects WHERE id = ? AND status = ?",
            (project_id, "deleted")
        )

        if not row:
            return None

        project = Project(
            id=row['id'],
            name=row['name'],
            description=row['description'],
            tags=json.loads(row['tags']) if row['tags'] else [],
            status=ProjectStatus.ACTIVE.value,
            metadata=json.loads(row['metadata']) if row['metadata'] else {},
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            file_count=row['file_count'] or 0,
            total_size=row['total_size'] or 0,
        )

        with self._projects_lock:
            self._projects[project.id] = project

        self._save_project(project)

        logger.info(f"项目已恢复：{project_id}")
        return project

    def get_statistics(self, project_id: str) -> ProjectStatistics | None:
        """获取项目统计信息"""
        project = self.get_project(project_id)
        if not project:
            return None

        return ProjectStatistics(
            project_id=project_id,
            total_files=project.file_count,
            total_size=project.total_size,
            file_types=project.metadata.get("file_types", {}),
            version_count=project.metadata.get("version_count", 0),
            latest_activity=project.updated_at,
        )

    def update_statistics(self, project_id: str, stats: dict):
        """更新项目统计信息"""
        project = self.get_project(project_id)
        if not project:
            return

        project.file_count = stats.get("file_count", project.file_count)
        project.total_size = stats.get("total_size", project.total_size)
        project.metadata["file_types"] = stats.get("file_types", {})
        project.metadata["version_count"] = stats.get("version_count", 0)
        project.updated_at = datetime.now().isoformat()

        self._save_project(project)


_project_manager: ProjectManager | None = None
_manager_lock = threading.Lock()


def get_project_manager() -> ProjectManager:
    """获取项目管理器实例"""
    global _project_manager
    with _manager_lock:
        if _project_manager is None:
            _project_manager = ProjectManager()
        return _project_manager
