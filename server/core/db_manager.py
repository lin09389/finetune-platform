"""
数据库连接管理模块
提供真正的连接池（Connection Pool）与上下文管理器支持
彻底修复 FastAPI asyncio 事件循环下 threading.local 引起的事务交叉问题
"""
import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)


class DatabaseConnectionPool:
    """
    SQLite 多路数据库连接池
    
    使用内存弹夹（List + Lock）模式替代有缺陷的 threading.local。
    每次请求通过 get_connection 签出 (pop) 一个独立连接，执行完毕后归还 (append)，
    确保并发请求的协程拥有各自独立的事务环境，避免事务覆盖和死锁。
    """

    def __init__(self, db_path: str = None, max_connections: int = 50):
        self._db_path = str(Path(db_path or "data/app.db"))
        self._max_connections = max_connections
        self._connections: List[sqlite3.Connection] = []
        self._connections_lock = threading.Lock()
        logger.info(f"数据库多路连接池已初始化：{self._db_path} (Max: {self._max_connections})")

    def _create_connection(self) -> sqlite3.Connection:
        """创建一个优化的、允许跨线程的 SQLite 连接"""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            self._db_path,
            timeout=10.0, # 增加等待时间，减少 db is locked
            isolation_level=None,
            check_same_thread=False, # 允许底层连接在不同线程/协程中穿梭
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL") # NORMAL 对于 WAL 模式性能最好且足够安全
        conn.execute("PRAGMA busy_timeout = 10000")
        logger.debug(f"已新建真实的数据库物理连接 -> {self._db_path}")
        return conn

    @contextmanager
    def get_connection(self):
        """
        获取数据库连接的上下文管理器 (池化借还模式)

        用法：
            with db_pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM table")
        """
        conn = None
        # 1. 尝试从池中弹出一个空闲连接
        with self._connections_lock:
            if self._connections:
                conn = self._connections.pop()
        
        # 2. 如果池空了，立即创建一个新连接（SQLite新建连接开销极小）
        if conn is None:
            conn = self._create_connection()

        try:
            conn.execute("BEGIN")
            yield conn
        except Exception as e:
            conn.rollback()
            logger.error(f"数据库操作失败，已回滚：{e}")
            raise
        else:
            conn.commit()
        finally:
            # 3. 释放回连接池
            with self._connections_lock:
                if len(self._connections) < self._max_connections:
                    self._connections.append(conn)
                else:
                    # 如果池子满了，直接销毁，避免无限增长
                    try:
                        conn.close()
                    except Exception as e:
                        logger.warning(f"超编连接销毁失败: {e}")

    def close_all(self):
        """关闭所有闲置连接"""
        with self._connections_lock:
            connections = self._connections[:]
            self._connections.clear()

        for conn in connections:
            try:
                conn.close()
            except Exception as e:
                logger.warning(f"关闭数据库闲置连接失败：{e}")
        logger.debug("数据库连接池中所有连接已物理关闭")

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
