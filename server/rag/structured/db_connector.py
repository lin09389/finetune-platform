"""
结构化数�?- 数据库连接器
支持 SQLite、PostgreSQL 等数据库连接
"""
from typing import List, Dict, Any, Optional, Union, AsyncIterator
from pathlib import Path
from pydantic import BaseModel, Field
from abc import ABC, abstractmethod
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime
import logging
import asyncio
import json

logger = logging.getLogger(__name__)


class ConnectionConfig(BaseModel):
    """数据库连接配�?""
    db_type: str = Field(..., description="数据库类型：sqlite/postgresql/mysql")
    host: str = Field(default="localhost", description="主机地址")
    port: int = Field(default=5432, description="端口")
    database: str = Field(..., description="数据库名�?路径")
    username: Optional[str] = Field(default=None, description="用户�?)
    password: Optional[str] = Field(default=None, description="密码")
    schema_name: str = Field(default="public", description="Schema 名称")
    pool_size: int = Field(default=5, description="连接池大�?)
    connect_timeout: int = Field(default=30, description="连接超时（秒�?)


class TableSchema(BaseModel):
    """表结构信�?""
    table_name: str
    columns: List[Dict[str, Any]]
    primary_keys: List[str] = Field(default_factory=list)
    foreign_keys: List[Dict[str, str]] = Field(default_factory=list)
    indexes: List[Dict[str, Any]] = Field(default_factory=list)
    row_count: Optional[int] = None


class QueryResult(BaseModel):
    """查询结果"""
    success: bool = True
    columns: List[str] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    affected_rows: int = 0
    execution_time_ms: float = 0.0
    error: Optional[str] = None


class DatabaseConnector(ABC):
    """数据库连接器基类"""
    
    def __init__(self, config: ConnectionConfig):
        self.config = config
        self._connection = None
        self._pool = None
    
    @abstractmethod
    def connect(self) -> bool:
        """建立连接"""
        pass
    
    @abstractmethod
    def disconnect(self) -> bool:
        """断开连接"""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """检查连接状�?""
        pass
    
    @abstractmethod
    def execute(
        self,
        sql: str,
        params: Optional[Union[Dict[str, Any], tuple]] = None
    ) -> QueryResult:
        """执行 SQL"""
        pass
    
    @abstractmethod
    def query(
        self,
        sql: str,
        params: Optional[Union[Dict[str, Any], tuple]] = None,
        limit: Optional[int] = None
    ) -> QueryResult:
        """执行查询"""
        pass
    
    @abstractmethod
    def get_tables(self) -> List[str]:
        """获取所有表�?""
        pass
    
    @abstractmethod
    def get_table_schema(self, table_name: str) -> Optional[TableSchema]:
        """获取表结�?""
        pass
    
    @abstractmethod
    def get_table_sample(self, table_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """获取表数据样�?""
        pass
    
    @contextmanager
    def transaction(self):
        """事务上下文管理器"""
        try:
            yield self
        except Exception as e:
            logger.error(f"事务失败：{e}")
            raise
    
    def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        result = {
            "success": False,
            "db_type": self.config.db_type,
            "message": ""
        }
        
        try:
            if self.connect():
                tables = self.get_tables()
                result["success"] = True
                result["message"] = f"连接成功，发�?{len(tables)} 个表"
                result["table_count"] = len(tables)
            else:
                result["message"] = "连接失败"
        except Exception as e:
            result["message"] = str(e)
        
        return result
    
    def get_database_info(self) -> Dict[str, Any]:
        """获取数据库信�?""
        tables = self.get_tables()
        
        info = {
            "db_type": self.config.db_type,
            "database": self.config.database,
            "table_count": len(tables),
            "tables": []
        }
        
        for table_name in tables:
            schema = self.get_table_schema(table_name)
            if schema:
                info["tables"].append({
                    "name": table_name,
                    "columns": len(schema.columns),
                    "row_count": schema.row_count
                })
        
        return info


class SQLiteConnector(DatabaseConnector):
    """SQLite 数据库连接器"""
    
    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._db_path = Path(config.database)
    
    def connect(self) -> bool:
        """建立连接"""
        try:
            import sqlite3
            self._connection = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False
            )
            self._connection.row_factory = sqlite3.Row
            logger.info(f"SQLite 连接成功：{self._db_path}")
            return True
        except Exception as e:
            logger.error(f"SQLite 连接失败：{e}")
            return False
    
    def disconnect(self) -> bool:
        """断开连接"""
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.info("SQLite 连接已关�?)
        return True
    
    def is_connected(self) -> bool:
        """检查连接状�?""
        return self._connection is not None
    
    def execute(
        self,
        sql: str,
        params: Optional[Union[Dict[str, Any], tuple]] = None
    ) -> QueryResult:
        """执行 SQL"""
        import time
        
        start_time = time.time()
        result = QueryResult()
        
        try:
            if not self._connection:
                self.connect()
            
            cursor = self._connection.cursor()
            
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            
            self._connection.commit()
            
            result.success = True
            result.affected_rows = cursor.rowcount
            result.execution_time_ms = (time.time() - start_time) * 1000
            
        except Exception as e:
            result.success = False
            result.error = str(e)
            logger.error(f"SQL 执行失败：{e}")
        
        return result
    
    def query(
        self,
        sql: str,
        params: Optional[Union[Dict[str, Any], tuple]] = None,
        limit: Optional[int] = None
    ) -> QueryResult:
        """执行查询"""
        import time
        
        start_time = time.time()
        result = QueryResult()
        
        try:
            if not self._connection:
                self.connect()
            
            if limit:
                sql = f"{sql} LIMIT {limit}"
            
            cursor = self._connection.cursor()
            
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            
            result.success = True
            result.columns = columns
            result.rows = [dict(row) for row in rows]
            result.row_count = len(rows)
            result.execution_time_ms = (time.time() - start_time) * 1000
            
        except Exception as e:
            result.success = False
            result.error = str(e)
            logger.error(f"查询失败：{e}")
        
        return result
    
    def get_tables(self) -> List[str]:
        """获取所有表�?""
        result = self.query(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [row["name"] for row in result.rows]
    
    def get_table_schema(self, table_name: str) -> Optional[TableSchema]:
        """获取表结�?""
        try:
            cursor = self._connection.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns_info = cursor.fetchall()
            
            columns = []
            primary_keys = []
            
            for col in columns_info:
                col_dict = dict(col)
                columns.append({
                    "name": col_dict["name"],
                    "type": col_dict["type"],
                    "nullable": not col_dict["notnull"],
                    "default": col_dict["dflt_value"],
                    "primary_key": bool(col_dict["pk"])
                })
                if col_dict["pk"]:
                    primary_keys.append(col_dict["name"])
            
            cursor.execute(f"PRAGMA foreign_key_list({table_name})")
            fk_info = cursor.fetchall()
            foreign_keys = []
            for fk in fk_info:
                fk_dict = dict(fk)
                foreign_keys.append({
                    "column": fk_dict["from"],
                    "ref_table": fk_dict["table"],
                    "ref_column": fk_dict["to"]
                })
            
            cursor.execute(f"PRAGMA index_list({table_name})")
            idx_info = cursor.fetchall()
            indexes = []
            for idx in idx_info:
                idx_dict = dict(idx)
                indexes.append({
                    "name": idx_dict["name"],
                    "unique": bool(idx_dict["unique"])
                })
            
            cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
            row_count = cursor.fetchone()["count"]
            
            return TableSchema(
                table_name=table_name,
                columns=columns,
                primary_keys=primary_keys,
                foreign_keys=foreign_keys,
                indexes=indexes,
                row_count=row_count
            )
        except Exception as e:
            logger.error(f"获取表结构失败：{e}")
            return None
    
    def get_table_sample(self, table_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """获取表数据样�?""
        result = self.query(f"SELECT * FROM {table_name} LIMIT {limit}")
        return result.rows


class PostgreSQLConnector(DatabaseConnector):
    """PostgreSQL 数据库连接器"""
    
    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._pool = None
    
    def connect(self) -> bool:
        """建立连接"""
        try:
            import psycopg2
            from psycopg2 import pool
            
            self._pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=self.config.pool_size,
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.username,
                password=self.config.password,
                connect_timeout=self.config.connect_timeout
            )
            
            logger.info(f"PostgreSQL 连接池已创建：{self.config.host}:{self.config.port}/{self.config.database}")
            return True
            
        except ImportError:
            logger.error("psycopg2 未安装，请运行：pip install psycopg2-binary")
            return False
        except Exception as e:
            logger.error(f"PostgreSQL 连接失败：{e}")
            return False
    
    def disconnect(self) -> bool:
        """断开连接"""
        if self._pool:
            self._pool.closeall()
            self._pool = None
            logger.info("PostgreSQL 连接池已关闭")
        return True
    
    def is_connected(self) -> bool:
        """检查连接状�?""
        return self._pool is not None
    
    @contextmanager
    def _get_connection(self):
        """获取连接"""
        if not self._pool:
            self.connect()
        
        conn = None
        try:
            conn = self._pool.getconn()
            conn.autocommit = False
            yield conn
        finally:
            if conn:
                self._pool.putconn(conn)
    
    def execute(
        self,
        sql: str,
        params: Optional[Union[Dict[str, Any], tuple]] = None
    ) -> QueryResult:
        """执行 SQL"""
        import time
        
        start_time = time.time()
        result = QueryResult()
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                
                conn.commit()
                
                result.success = True
                result.affected_rows = cursor.rowcount
                result.execution_time_ms = (time.time() - start_time) * 1000
                
        except Exception as e:
            result.success = False
            result.error = str(e)
            logger.error(f"SQL 执行失败：{e}")
        
        return result
    
    def query(
        self,
        sql: str,
        params: Optional[Union[Dict[str, Any], tuple]] = None,
        limit: Optional[int] = None
    ) -> QueryResult:
        """执行查询"""
        import time
        
        start_time = time.time()
        result = QueryResult()
        
        try:
            if limit:
                sql = f"{sql} LIMIT {limit}"
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                from psycopg2.extras import RealDictCursor
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = cursor.fetchall()
                
                result.success = True
                result.columns = columns
                result.rows = [dict(row) for row in rows]
                result.row_count = len(rows)
                result.execution_time_ms = (time.time() - start_time) * 1000
                
        except Exception as e:
            result.success = False
            result.error = str(e)
            logger.error(f"查询失败：{e}")
        
        return result
    
    def get_tables(self) -> List[str]:
        """获取所有表�?""
        result = self.query(
            f"""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            params=(self.config.schema_name,)
        )
        return [row["table_name"] for row in result.rows]
    
    def get_table_schema(self, table_name: str) -> Optional[TableSchema]:
        """获取表结�?""
        try:
            columns_result = self.query(
                """
                SELECT 
                    column_name as name,
                    data_type as type,
                    is_nullable,
                    column_default as default
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
                """,
                params=(self.config.schema_name, table_name)
            )
            
            columns = []
            for row in columns_result.rows:
                columns.append({
                    "name": row["name"],
                    "type": row["type"],
                    "nullable": row["is_nullable"] == "YES",
                    "default": row["default"]
                })
            
            pk_result = self.query(
                """
                SELECT a.attname as column_name
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = %s::regclass AND i.indisprimary
                """,
                params=(f"{self.config.schema_name}.{table_name}",)
            )
            primary_keys = [row["column_name"] for row in pk_result.rows]
            
            count_result = self.query(f'SELECT COUNT(*) as count FROM "{table_name}"')
            row_count = count_result.rows[0]["count"] if count_result.rows else 0
            
            return TableSchema(
                table_name=table_name,
                columns=columns,
                primary_keys=primary_keys,
                row_count=row_count
            )
        except Exception as e:
            logger.error(f"获取表结构失败：{e}")
            return None
    
    def get_table_sample(self, table_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """获取表数据样�?""
        result = self.query(f'SELECT * FROM "{table_name}" LIMIT {limit}')
        return result.rows


class MySQLConnector(DatabaseConnector):
    """MySQL 数据库连接器"""
    
    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._pool = None
    
    def connect(self) -> bool:
        """建立连接"""
        try:
            import pymysql
            from pymysql import pooling
            
            self._pool = pooling.ConnectionPool(
                pool_size=self.config.pool_size,
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.username,
                password=self.config.password,
                connect_timeout=self.config.connect_timeout,
                cursorclass=pymysql.cursors.DictCursor
            )
            
            logger.info(f"MySQL 连接池已创建：{self.config.host}:{self.config.port}/{self.config.database}")
            return True
            
        except ImportError:
            logger.error("pymysql 未安装，请运行：pip install pymysql")
            return False
        except Exception as e:
            logger.error(f"MySQL 连接失败：{e}")
            return False
    
    def disconnect(self) -> bool:
        """断开连接"""
        if self._pool:
            self._pool.close()
            self._pool = None
            logger.info("MySQL 连接池已关闭")
        return True
    
    def is_connected(self) -> bool:
        """检查连接状�?""
        return self._pool is not None
    
    @contextmanager
    def _get_connection(self):
        """获取连接"""
        if not self._pool:
            self.connect()
        
        conn = None
        try:
            conn = self._pool.get_connection()
            yield conn
        finally:
            if conn:
                conn.close()
    
    def execute(
        self,
        sql: str,
        params: Optional[Union[Dict[str, Any], tuple]] = None
    ) -> QueryResult:
        """执行 SQL"""
        import time
        
        start_time = time.time()
        result = QueryResult()
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                
                conn.commit()
                
                result.success = True
                result.affected_rows = cursor.rowcount
                result.execution_time_ms = (time.time() - start_time) * 1000
                
        except Exception as e:
            result.success = False
            result.error = str(e)
            logger.error(f"SQL 执行失败：{e}")
        
        return result
    
    def query(
        self,
        sql: str,
        params: Optional[Union[Dict[str, Any], tuple]] = None,
        limit: Optional[int] = None
    ) -> QueryResult:
        """执行查询"""
        import time
        
        start_time = time.time()
        result = QueryResult()
        
        try:
            if limit:
                sql = f"{sql} LIMIT {limit}"
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = cursor.fetchall()
                
                result.success = True
                result.columns = columns
                result.rows = rows
                result.row_count = len(rows)
                result.execution_time_ms = (time.time() - start_time) * 1000
                
        except Exception as e:
            result.success = False
            result.error = str(e)
            logger.error(f"查询失败：{e}")
        
        return result
    
    def get_tables(self) -> List[str]:
        """获取所有表�?""
        result = self.query(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
            params=(self.config.database,)
        )
        return [row["table_name"] for row in result.rows]
    
    def get_table_schema(self, table_name: str) -> Optional[TableSchema]:
        """获取表结�?""
        try:
            columns_result = self.query(
                """
                SELECT 
                    column_name as name,
                    data_type as type,
                    is_nullable,
                    column_default as `default`
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
                """,
                params=(self.config.database, table_name)
            )
            
            columns = []
            for row in columns_result.rows:
                columns.append({
                    "name": row["name"],
                    "type": row["type"],
                    "nullable": row["is_nullable"] == "YES",
                    "default": row["default"]
                })
            
            pk_result = self.query(
                """
                SELECT column_name
                FROM information_schema.key_column_usage
                WHERE table_schema = %s AND table_name = %s AND constraint_name = 'PRIMARY'
                """,
                params=(self.config.database, table_name)
            )
            primary_keys = [row["column_name"] for row in pk_result.rows]
            
            count_result = self.query(f"SELECT COUNT(*) as count FROM `{table_name}`")
            row_count = count_result.rows[0]["count"] if count_result.rows else 0
            
            return TableSchema(
                table_name=table_name,
                columns=columns,
                primary_keys=primary_keys,
                row_count=row_count
            )
        except Exception as e:
            logger.error(f"获取表结构失败：{e}")
            return None
    
    def get_table_sample(self, table_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """获取表数据样�?""
        result = self.query(f"SELECT * FROM `{table_name}` LIMIT {limit}")
        return result.rows


_connectors: Dict[str, DatabaseConnector] = {}


def get_db_connector(
    db_type: str,
    database: str,
    host: str = "localhost",
    port: Optional[int] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    **kwargs
) -> DatabaseConnector:
    """
    获取数据库连接器
    
    Args:
        db_type: 数据库类型（sqlite/postgresql/mysql�?        database: 数据库名�?路径
        host: 主机地址
        port: 端口
        username: 用户�?        password: 密码
        
    Returns:
        数据库连接器实例
    """
    default_ports = {
        "sqlite": None,
        "postgresql": 5432,
        "mysql": 3306
    }
    
    config = ConnectionConfig(
        db_type=db_type,
        host=host,
        port=port or default_ports.get(db_type, 5432),
        database=database,
        username=username,
        password=password,
        **kwargs
    )
    
    cache_key = f"{db_type}:{host}:{port}:{database}"
    
    if cache_key not in _connectors:
        if db_type == "sqlite":
            _connectors[cache_key] = SQLiteConnector(config)
        elif db_type == "postgresql":
            _connectors[cache_key] = PostgreSQLConnector(config)
        elif db_type == "mysql":
            _connectors[cache_key] = MySQLConnector(config)
        else:
            raise ValueError(f"不支持的数据库类型：{db_type}")
    
    return _connectors[cache_key]


def create_sqlite_connector(db_path: str) -> SQLiteConnector:
    """快速创�?SQLite 连接�?""
    config = ConnectionConfig(
        db_type="sqlite",
        database=db_path
    )
    return SQLiteConnector(config)


def create_postgresql_connector(
    host: str,
    database: str,
    username: str,
    password: str,
    port: int = 5432,
    schema_name: str = "public"
) -> PostgreSQLConnector:
    """快速创�?PostgreSQL 连接�?""
    config = ConnectionConfig(
        db_type="postgresql",
        host=host,
        port=port,
        database=database,
        username=username,
        password=password,
        schema_name=schema_name
    )
    return PostgreSQLConnector(config)
