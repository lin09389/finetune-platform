# -*- coding: utf-8 -*-
"""
结构化数据支持模块
支持表格数据存储、数据库连接和 SQL 查询
"""
from rag.structured.table_store import (
    TableStore,
    TableMetadata,
    get_table_store
)
from rag.structured.db_connector import (
    DatabaseConnector,
    SQLiteConnector,
    PostgreSQLConnector,
    MySQLConnector,
    ConnectionConfig,
    QueryResult,
    get_db_connector,
    create_sqlite_connector,
    create_postgresql_connector
)
from rag.structured.query_engine import (
    QueryEngine,
    SQLGenerationResult,
    QueryHistory,
    get_query_engine
)

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
