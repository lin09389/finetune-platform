"""
数据库连接管理模块
提供真正的连接池（Connection Pool）与上下文管理器支持
彻底修复 FastAPI asyncio 事件循环下 threading.local 引起的事务交叉问题

修复清单（2026-05-04）
  1. DEFERRED → IMMEDIATE：所有写事务默认使用 BEGIN IMMEDIATE，消除多写并发下的
     SQLITE_BUSY 死锁。只读操作使用 get_readonly_connection 来避免锁升级问题。
  2. 连接污染防护：COMMIT / ROLLBACK 失败后物理关闭连接，不再归还池中。
  3. executescript 安全封装：提供 safe_execute_script，在 autocommit 模式下执行
     DDL 脚本，避免 executescript 的隐式 COMMIT 破坏当前事务原子性。
  4. SQL 注入防护工具：提供 validate_column_names 白名单校验函数，供 Repository
     层在动态拼接字段名时使用。
  5. 异步安全包装：提供 run_sync 辅助函数，将同步 SQLite 操作移至线程池执行，
     避免阻塞 asyncio 事件循环。
"""
import logging
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import List, Callable, Any, TypeVar

import anyio

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 合法 SQLite 列名的正则：只允许字母、数字和下划线
_SAFE_COLUMN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_column_names(columns: list[str] | set[str], allowed: set[str] | None = None) -> list[str]:
    """
    校验动态 SQL 中的列名是否安全。

    - 所有列名必须匹配 ``[A-Za-z_][A-Za-z0-9_]*``。
    - 如果提供了 ``allowed`` 白名单，则所有列名必须在白名单中。
    - 任何校验失败都将抛出 ``ValueError``，从而阻止 SQL 注入。

    返回经过验证的列名列表（保持输入顺序）。
    """
    validated: list[str] = []
    for col in columns:
        if not _SAFE_COLUMN_RE.match(col):
            raise ValueError(f"非法列名: {col!r}")
        if allowed is not None and col not in allowed:
            raise ValueError(f"不允许的列名: {col!r}（允许值: {allowed}）")
        validated.append(col)
    return validated


class DatabaseConnectionPool:
    """
    SQLite 多路数据库连接池

    使用内存弹夹（List + Lock）模式替代有缺陷的 threading.local。
    每次请求通过 get_connection 签出 (pop) 一个独立连接，执行完毕后归还 (append)，
    确保并发请求的协程拥有各自独立的事务环境，避免事务覆盖和死锁。
    """

    def __init__(self, db_path: str = None, max_connections: int = 50):
        # Resolve against server base_dir so API/worker/CLI share one absolute DB
        # regardless of process CWD (Phase 4 ops hygiene).
        if db_path is None:
            try:
                from core.storage import APP_DB_PATH

                resolved = APP_DB_PATH
            except Exception:
                from core.config import settings

                resolved = str((settings.base_dir / "data" / "app.db").resolve())
        else:
            try:
                from core.storage import resolve_storage_path

                resolved = resolve_storage_path(db_path)
            except Exception:
                candidate = Path(db_path).expanduser()
                if not candidate.is_absolute():
                    from core.config import settings

                    candidate = settings.base_dir / candidate
                resolved = str(candidate.resolve())
        self._db_path = str(resolved)
        self._max_connections = max_connections
        self._connections: List[sqlite3.Connection] = []
        self._active_connections: set[int] = set()  # 追踪借出连接的 id
        self._connections_lock = threading.Lock()
        self._closed = False  # 池是否已关闭
        self._last_used = time.monotonic()
        logger.info(f"数据库多路连接池已初始化：{self._db_path} (Max: {self._max_connections})")

    def _create_connection(self) -> sqlite3.Connection:
        """创建一个优化的、允许跨线程的 SQLite 连接"""
        global _global_connection_count
        with _global_connection_lock:
            if _global_connection_count >= _MAX_GLOBAL_CONNECTIONS:
                raise RuntimeError(
                    f"全局 SQLite 连接数已达硬上限 ({_MAX_GLOBAL_CONNECTIONS})，"
                    "拒绝创建新连接以防止资源耗尽。"
                )
            _global_connection_count += 1
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            self._db_path,
            timeout=10.0, # 增加等待时间，减少 db is locked
            isolation_level=None,  # autocommit 模式，由我们自己管理事务
            check_same_thread=False, # 允许底层连接在不同线程/协程中穿梭
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL") # NORMAL 对于 WAL 模式性能最好且足够安全
        busy_timeout = int(os.environ.get("SQLITE_BUSY_TIMEOUT", "10000"))
        conn.execute(f"PRAGMA busy_timeout = {busy_timeout}")
        logger.debug(f"已新建真实的数据库物理连接 -> {self._db_path}")
        return conn

    def _check_connection(self, conn: sqlite3.Connection) -> bool:
        """检查连接是否仍然可用"""
        try:
            conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    def _return_connection(self, conn: sqlite3.Connection) -> None:
        """安全地将连接归还到池中，或在池满/连接损坏/池已关闭时物理关闭"""
        self._last_used = time.monotonic()
        conn_id = id(conn)
        with self._connections_lock:
            self._active_connections.discard(conn_id)
            if not self._closed and len(self._connections) < self._max_connections:
                self._connections.append(conn)
                return
        # 池满或池已关闭，物理关闭连接
        global _global_connection_count
        try:
            conn.close()
        except Exception as e:
            logger.warning(f"超编连接销毁失败: {e}")
        finally:
            with _global_connection_lock:
                _global_connection_count = max(0, _global_connection_count - 1)

    def _destroy_connection(self, conn: sqlite3.Connection) -> None:
        """物理关闭一个受损的连接，不归还池"""
        global _global_connection_count
        try:
            conn.close()
        except Exception as e:
            logger.warning(f"受损连接物理关闭失败: {e}")
        finally:
            with _global_connection_lock:
                _global_connection_count = max(0, _global_connection_count - 1)

    def _acquire_connection(self) -> sqlite3.Connection:
        """从池中签出一个经过健康检查的连接，或创建新连接"""
        self._last_used = time.monotonic()
        while True:
            conn = None
            with self._connections_lock:
                if self._closed:
                    raise RuntimeError("连接池已关闭，无法获取连接")
                if self._connections:
                    conn = self._connections.pop()
            if conn is None:
                conn = self._create_connection()
                with self._connections_lock:
                    self._active_connections.add(id(conn))
                return conn
            # 健康检查
            if self._check_connection(conn):
                with self._connections_lock:
                    self._active_connections.add(id(conn))
                return conn
            # 连接已损坏，物理关闭并继续尝试
            self._destroy_connection(conn)

    @contextmanager
    def get_connection(self):
        """
        获取数据库连接的上下文管理器 (池化借还模式)
        使用 BEGIN IMMEDIATE 开启写事务，避免 DEFERRED 模式下的锁升级死锁。

        用法：
            with db_pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO ...")
        """
        conn = self._acquire_connection()
        poisoned = False

        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
        except Exception as e:
            poisoned = True
            try:
                conn.rollback()
            except Exception as rb_err:
                logger.error(f"回滚失败，连接已污染：{rb_err}")
            logger.error(f"数据库操作失败，已回滚：{e}")
            raise
        else:
            try:
                conn.commit()
            except Exception as commit_err:
                poisoned = True
                logger.error(f"COMMIT 失败，连接已污染：{commit_err}")
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise commit_err
        finally:
            if poisoned:
                self._destroy_connection(conn)
            else:
                self._return_connection(conn)

    @contextmanager
    def get_readonly_connection(self):
        """
        获取只读连接的上下文管理器。
        不开启显式事务，适用于纯 SELECT 查询，避免占用写锁。

        用法：
            with db_pool.get_readonly_connection() as conn:
                rows = conn.execute("SELECT * FROM table").fetchall()
        """
        conn = self._acquire_connection()

        try:
            yield conn
        except Exception as e:
            logger.error(f"只读数据库操作失败：{e}")
            raise
        finally:
            self._return_connection(conn)

    def safe_execute_script(self, sql: str) -> None:
        """
        安全地执行包含多条 DDL 语句的 SQL 脚本。

        与 ``conn.executescript()`` 不同，本方法：
        1. 在独立的连接上执行，不干扰池中的其他事务。
        2. 使用显式 BEGIN/COMMIT 包裹整个脚本，确保多语句 DDL 的原子性。
           如果中途报错，已执行的 DDL 将被 ROLLBACK。
        3. 不会隐式 COMMIT 调用者的当前事务。

        注意：此方法主要用于 schema migration / ensure_schema。
        """
        conn = self._acquire_connection()
        try:
            # 使用显式事务包裹，确保多条 DDL 的原子性。
            # 不使用 executescript（它会隐式 COMMIT），改用逐条执行。
            conn.execute("BEGIN")
            for statement in sql.split(";"):
                statement = statement.strip()
                if statement:
                    conn.execute(statement)
            conn.execute("COMMIT")
        except Exception as e:
            logger.error(f"执行 SQL 脚本失败：{e}")
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            self._destroy_connection(conn)
            raise
        else:
            self._return_connection(conn)

    def close_all(self):
        """关闭所有闲置连接，并标记池为已关闭。

        标记 ``_closed = True`` 后，所有借出中的连接在归还时将被物理关闭
        而不是重新放入池中，从而防止资源泄漏。
        """
        global _global_connection_count
        with self._connections_lock:
            self._closed = True
            connections = self._connections[:]
            self._connections.clear()
            active_count = len(self._active_connections)

        if active_count > 0:
            logger.warning(
                "关闭连接池时仍有 %d 个借出中的活跃连接，"
                "它们将在归还时被物理关闭",
                active_count,
            )

        for conn in connections:
            try:
                conn.close()
            except Exception as e:
                logger.warning(f"关闭数据库闲置连接失败：{e}")

        with _global_connection_lock:
            _global_connection_count = max(0, _global_connection_count - len(connections))
        logger.debug("数据库连接池中所有闲置连接已物理关闭")

    @property
    def active_connection_count(self) -> int:
        with self._connections_lock:
            return len(self._active_connections)

    def execute_query(self, query: str, params: tuple = ()):
        """执行查询并返回所有结果"""
        with self.get_readonly_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()

    def execute_one(self, query: str, params: tuple = ()):
        """执行查询并返回单个结果"""
        with self.get_readonly_connection() as conn:
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


def _serialize_value(value: Any) -> Any:
    """将 dict/list 类型的值自动序列化为 JSON 字符串，防止 SQLite InterfaceError。"""
    if isinstance(value, (dict, list)):
        import json
        return json.dumps(value, ensure_ascii=False)
    return value


def dynamic_update(
    conn: "sqlite3.Connection",
    table: str,
    pk_col: str,
    pk_val: Any,
    fields: dict,
    allowed: set[str],
) -> int:
    """
    安全地执行动态 UPDATE 语句。

    - 列名经过 validate_column_names 白名单校验。
    - 值使用 ? 参数化占位符。
    - 表名和主键列名经过正则校验。
    - dict/list 类型的值会自动序列化为 JSON 字符串。

    返回受影响的行数。
    """
    if not _SAFE_COLUMN_RE.match(table):
        raise ValueError(f"非法表名: {table!r}")
    if not _SAFE_COLUMN_RE.match(pk_col):
        raise ValueError(f"非法主键列名: {pk_col!r}")
    validate_column_names(fields.keys(), allowed)
    assignments = ", ".join(f"{k} = ?" for k in fields)
    sql = f"UPDATE {table} SET {assignments} WHERE {pk_col} = ?"
    values = [_serialize_value(v) for v in fields.values()] + [pk_val]
    return conn.execute(sql, values).rowcount


_db_pools: dict[str, DatabaseConnectionPool] = {}
_pool_lock = threading.Lock()
_global_connection_count = 0
_global_connection_lock = threading.Lock()
_MAX_GLOBAL_CONNECTIONS = 100
_MAX_CACHED_POOLS = int(os.environ.get("MAX_SQLITE_POOLS", "32"))


def _evict_idle_pools_locked(exclude_path: str | None = None) -> list[DatabaseConnectionPool]:
    """Remove least-recently-used pools that have no checked-out connections.

    Caller must hold ``_pool_lock``. Returned pools are closed outside that
    lock to keep lock ordering simple.
    """
    overflow = len(_db_pools) - _MAX_CACHED_POOLS + 1
    if overflow <= 0:
        return []
    candidates = sorted(
        (
            (path, pool)
            for path, pool in _db_pools.items()
            if path != exclude_path and pool.active_connection_count == 0
        ),
        key=lambda item: item[1]._last_used,
    )
    evicted: list[DatabaseConnectionPool] = []
    for path, pool in candidates[:overflow]:
        if _db_pools.get(path) is pool:
            _db_pools.pop(path, None)
            evicted.append(pool)
    return evicted


def _resolve_pool_db_path(db_path: str | None) -> str:
    """Canonical absolute path used as the connection-pool cache key."""
    if db_path is None:
        try:
            from core.storage import APP_DB_PATH

            return APP_DB_PATH
        except Exception:
            from core.config import settings

            return str((settings.base_dir / "data" / "app.db").resolve())
    try:
        from core.storage import resolve_storage_path

        return resolve_storage_path(db_path)
    except Exception:
        candidate = Path(db_path).expanduser()
        if not candidate.is_absolute():
            from core.config import settings

            candidate = settings.base_dir / candidate
        return str(candidate.resolve())


def get_db_pool(db_path: str = None) -> DatabaseConnectionPool:
    """获取数据库连接池实例（按路径缓存）"""
    global _db_pools
    db_path = _resolve_pool_db_path(db_path)

    evicted: list[DatabaseConnectionPool] = []
    with _pool_lock:
        pool = _db_pools.get(db_path)
        if pool is None or getattr(pool, "_closed", False):
            evicted = _evict_idle_pools_locked(exclude_path=db_path)
            _db_pools[db_path] = DatabaseConnectionPool(db_path)
        result = _db_pools[db_path]
    for stale_pool in evicted:
        stale_pool.close_all()
    return result


def init_db_pool(db_path: str) -> DatabaseConnectionPool:
    """初始化数据库连接池"""
    global _db_pools
    db_path = _resolve_pool_db_path(db_path)
    evicted: list[DatabaseConnectionPool] = []
    with _pool_lock:
        previous = _db_pools.pop(db_path, None)
        if previous is not None:
            evicted.append(previous)
        evicted.extend(_evict_idle_pools_locked(exclude_path=db_path))
        _db_pools[db_path] = DatabaseConnectionPool(db_path)
        result = _db_pools[db_path]
    for stale_pool in evicted:
        stale_pool.close_all()
    return result


def close_all_pools():
    """关闭所有数据库连接池"""
    global _db_pools
    pools = list(_db_pools.items())
    _db_pools.clear()
    for db_path, pool in pools:
        pool.close_all()
        logger.info(f"已关闭数据库连接池：{db_path}")


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


async def run_sync(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """
    在线程池中运行同步函数，避免阻塞 asyncio 事件循环。

    用法（在 async 路由中）：
        result = await run_sync(repository.list_projects)
        result = await run_sync(repository.get_project, project_id)
        result = await run_sync(service.create_workflow, request)
    """
    return await anyio.to_thread.run_sync(lambda: func(*args, **kwargs))
