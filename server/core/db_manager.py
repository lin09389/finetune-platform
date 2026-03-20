"""
数据库连接管理模�?提供连接池和上下文管理器支持
"""
import sqlite3
import threading
import logging
from pathlib import Path
from typing import Optional, ContextManager, Dict
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class DatabaseConnectionPool:
    """
    SQLite 数据库连接池
    
    由于 SQLite 是文件数据库，使用线程局部存储来管理连接
    每个线程维护自己的连接，避免多线程问�?    """
    
    _instance: Optional['DatabaseConnectionPool'] = None
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
            
        self._db_path = db_path or "data/app.db"
        self._thread_local = threading.local()
        self._initialized = True
        logger.info(f"数据库连接池已初始化：{self._db_path}")
    
    def _get_thread_connection(self) -> sqlite3.Connection:
        """获取当前线程的连�?""
        if not hasattr(self._thread_local, 'connection'):
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            # 启用外键约束
            conn.execute("PRAGMA foreign_keys = ON")
            # 设置 WAL 模式提高并发性能
            conn.execute("PRAGMA journal_mode = WAL")
            self._thread_local.connection = conn
            logger.debug(f"创建新数据库连接：线�?{threading.current_thread().name}")
        return self._thread_local.connection
    
    @contextmanager
    def get_connection(self):
        """
        获取数据库连接的上下文管理器
        
        用法�?            with db_pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM table")
        """
        conn = self._get_thread_connection()
        try:
            yield conn
        except Exception as e:
            conn.rollback()
            logger.error(f"数据库操作失败：{e}")
            raise
        else:
            conn.commit()
    
    def close_all(self):
        """关闭所有连�?""
        if hasattr(self._thread_local, 'connection'):
            try:
                self._thread_local.connection.close()
                del self._thread_local.connection
                logger.debug("数据库连接已关闭")
            except Exception as e:
                logger.warning(f"关闭数据库连接失败：{e}")
    
    def execute_query(self, query: str, params: tuple = ()):
        """执行查询并返回所有结�?""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
    
    def execute_one(self, query: str, params: tuple = ()):
        """执行查询并返回单个结�?""
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


# 全局连接池字�?- 按路径管理多个数据库连接�?_db_pools: Dict[str, DatabaseConnectionPool] = {}
_pool_lock = threading.Lock()


def get_db_pool(db_path: str = None) -> DatabaseConnectionPool:
    """获取数据库连接池实例（按路径缓存�?""
    global _db_pools
    if db_path is None:
        db_path = "data/app.db"

    with _pool_lock:
        if db_path not in _db_pools:
            _db_pools[db_path] = DatabaseConnectionPool(db_path)
        return _db_pools[db_path]


def init_db_pool(db_path: str) -> DatabaseConnectionPool:
    """初始化数据库连接�?""
    global _db_pools
    with _pool_lock:
        _db_pools[db_path] = DatabaseConnectionPool(db_path)
        return _db_pools[db_path]


def close_all_pools():
    """关闭所有数据库连接�?""
    global _db_pools
    for db_path, pool in _db_pools.items():
        pool.close_all()
        logger.info(f"已关闭数据库连接池：{db_path}")
    _db_pools.clear()


@contextmanager
def get_db_connection(db_path: str = None):
    """
    获取数据库连接的便捷函数
    
    用法�?        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM table")
    """
    pool = get_db_pool(db_path)
    with pool.get_connection() as conn:
        yield conn
