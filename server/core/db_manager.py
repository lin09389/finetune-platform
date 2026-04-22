"""
数据库连接管理模块
提供连接池和上下文管理器支持
"""
import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DatabaseConnectionPool:
    """
    SQLite 数据库连接池

    由于 SQLite 是文件数据库，使用线程局部存储来管理连接
    每个线程维护自己的连接，避免多线程问题
    """

    def __init__(self, db_path: str = None):
        self._db_path = str(Path(db_path or "data/app.db"))
        self._thread_local = threading.local()
        self._connections: dict[int, sqlite3.Connection] = {}
        self._connections_lock = threading.Lock()
        logger.info(f"数据库连接池已初始化：{self._db_path}")

    def _get_thread_connection(self) -> sqlite3.Connection:
        """获取当前线程的连接"""
        if not hasattr(self._thread_local, 'connection'):
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                self._db_path,
                timeout=5.0,
                isolation_level=None,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = FULL")
            conn.execute("PRAGMA busy_timeout = 5000")
            self._thread_local.connection = conn
            with self._connections_lock:
                self._connections[threading.get_ident()] = conn
            logger.debug(f"创建新数据库连接：线程 {threading.current_thread().name}")
        return self._thread_local.connection

    @contextmanager
    def get_connection(self):
        """
        获取数据库连接的上下文管理器

        用法：
            with db_pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM table")
        """
        conn = self._get_thread_connection()
        try:
            conn.execute("BEGIN")
            yield conn
        except Exception as e:
            conn.rollback()
            logger.error(f"数据库操作失败：{e}")
            raise
        else:
            conn.commit()

    def close_all(self):
        """关闭所有连接"""
        with self._connections_lock:
            connections = list(self._connections.values())
            self._connections.clear()

        for conn in connections:
            try:
                conn.close()
            except Exception as e:
                logger.warning(f"关闭数据库连接失败：{e}")

        if hasattr(self._thread_local, 'connection'):
            del self._thread_local.connection
        logger.debug("数据库连接已关闭")

    def execute_query(self, query: str, params: tuple = ()):
        """执行查询并返回所有结果"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()

    def execute_one(self, query: str, params: tuple = ()):
        """执行查询并返回单个结果"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()

    def execute_update(self, query: str, params: tuple = ()):
        """执行更新操作"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.rowcount

    def execute_many(self, query: str, params_list: list):
        """批量执行操作"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            return cursor.rowcount


_db_pools: dict[str, DatabaseConnectionPool] = {}
_pool_lock = threading.Lock()


def get_db_pool(db_path: str = None) -> DatabaseConnectionPool:
    """获取数据库连接池实例（按路径缓存）"""
    global _db_pools
    if db_path is None:
        db_path = "data/app.db"
    db_path = str(Path(db_path))

    with _pool_lock:
        if db_path not in _db_pools:
            _db_pools[db_path] = DatabaseConnectionPool(db_path)
        return _db_pools[db_path]


def init_db_pool(db_path: str) -> DatabaseConnectionPool:
    """初始化数据库连接池"""
    global _db_pools
    db_path = str(Path(db_path))
    with _pool_lock:
        _db_pools[db_path] = DatabaseConnectionPool(db_path)
        return _db_pools[db_path]


def close_all_pools():
    """关闭所有数据库连接池"""
    global _db_pools
    for db_path, pool in _db_pools.items():
        pool.close_all()
        logger.info(f"已关闭数据库连接池：{db_path}")
    _db_pools.clear()


@contextmanager
def get_db_connection(db_path: str = None):
    """
    获取数据库连接的便捷函数

    用法：
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM table")
    """
    pool = get_db_pool(db_path)
    with pool.get_connection() as conn:
        yield conn
