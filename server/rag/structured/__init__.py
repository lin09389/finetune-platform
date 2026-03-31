"""
结构化数据支持模块
支持表格数据存储、数据库连接和 SQL 查询
"""
from rag.structured.db_connector import (
    ConnectionConfig,
    DatabaseConnector,
    MySQLConnector,
    PostgreSQLConnector,
    QueryResult,
    SQLiteConnector,
    create_postgresql_connector,
    create_sqlite_connector,
    get_db_connector,
)
from rag.structured.query_engine import (
    QueryEngine,
    QueryHistory,
    SQLGenerationResult,
    get_query_engine,
)
from rag.structured.table_store import TableMetadata, TableStore, get_table_store

__all__ = [
    'TableStore',
    'TableMetadata',
    'get_table_store',
    'DatabaseConnector',
    'SQLiteConnector',
    'PostgreSQLConnector',
    'MySQLConnector',
    'ConnectionConfig',
    'QueryResult',
    'get_db_connector',
    'create_sqlite_connector',
    'create_postgresql_connector',
    'QueryEngine',
    'SQLGenerationResult',
    'QueryHistory',
    'get_query_engine',
]
