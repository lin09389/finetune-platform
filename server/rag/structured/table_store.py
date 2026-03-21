# -*- coding: utf-8 -*-
"""
结构化数据 - 表格存储
支持 CSV、Excel 文件导入和表格数据管理
"""
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
from pydantic import BaseModel, Field
from datetime import datetime
import logging
import json
import uuid
import sqlite3
import pandas as pd

logger = logging.getLogger(__name__)


class TableMetadata(BaseModel):
    """表格元数据"""
    table_id: str = Field(..., description="表格唯一标识")
    name: str = Field(..., description="表格名称")
    description: str = Field(default="", description="表格描述")
    source_file: Optional[str] = Field(default=None, description="源文件路径")
    source_type: str = Field(default="csv", description="源文件类型：csv/excel/manual")
    row_count: int = Field(default=0, description="行数")
    column_count: int = Field(default=0, description="列数")
    columns: List[Dict[str, Any]] = Field(default_factory=list, description="列信息")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    tags: List[str] = Field(default_factory=list, description="标签")


class TableStore:
    """表格存储管理器"""
    
    def __init__(self, storage_path: str = "data/tables"):
        """
        初始化表格存储
        
        Args:
            storage_path: 存储路径
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.metadata_path = self.storage_path / "metadata"
        self.metadata_path.mkdir(parents=True, exist_ok=True)
        
        self.db_path = self.storage_path / "tables.db"
        self._init_database()
        
        self._tables: Dict[str, TableMetadata] = {}
        self._load_metadata()
    
    def _init_database(self):
        """初始化 SQLite 数据库"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS table_registry (
                table_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                source_file TEXT,
                source_type TEXT,
                row_count INTEGER,
                column_count INTEGER,
                columns_json TEXT,
                created_at TEXT,
                updated_at TEXT,
                tags_json TEXT
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info(f"表格数据库已初始化：{self.db_path}")
    
    def _load_metadata(self):
        """加载所有表格元数据"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM table_registry")
        rows = cursor.fetchall()
        conn.close()
        
        for row in rows:
            table_id, name, description, source_file, source_type, row_count, column_count, columns_json, created_at, updated_at, tags_json = row
            
            metadata = TableMetadata(
                table_id=table_id,
                name=name,
                description=description or "",
                source_file=source_file,
                source_type=source_type or "csv",
                row_count=row_count or 0,
                column_count=column_count or 0,
                columns=json.loads(columns_json) if columns_json else [],
                created_at=datetime.fromisoformat(created_at) if created_at else datetime.now(),
                updated_at=datetime.fromisoformat(updated_at) if updated_at else datetime.now(),
                tags=json.loads(tags_json) if tags_json else []
            )
            self._tables[table_id] = metadata
        
        logger.info(f"已加载 {len(self._tables)} 个表格元数据")
    
    def _save_metadata(self, metadata: TableMetadata):
        """保存表格元数据"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO table_registry 
            (table_id, name, description, source_file, source_type, row_count, column_count, columns_json, created_at, updated_at, tags_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            metadata.table_id,
            metadata.name,
            metadata.description,
            metadata.source_file,
            metadata.source_type,
            metadata.row_count,
            metadata.column_count,
            json.dumps(metadata.columns, ensure_ascii=False),
            metadata.created_at.isoformat(),
            metadata.updated_at.isoformat(),
            json.dumps(metadata.tags, ensure_ascii=False)
        ))
        
        conn.commit()
        conn.close()
    
    def _get_table_name(self, table_id: str) -> str:
        """获取数据库表名"""
        return f"table_{table_id.replace('-', '_')}"
    
    def import_csv(
        self,
        file_path: Union[str, Path],
        name: Optional[str] = None,
        description: str = "",
        tags: Optional[List[str]] = None,
        encoding: str = "utf-8",
        delimiter: str = ","
    ) -> TableMetadata:
        """
        导入 CSV 文件
        
        Args:
            file_path: CSV 文件路径
            name: 表格名称（默认使用文件名）
            description: 表格描述
            tags: 标签列表
            encoding: 文件编码
            delimiter: 分隔符
            
        Returns:
            表格元数据
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在：{file_path}")
        
        try:
            df = pd.read_csv(file_path, encoding=encoding, delimiter=delimiter)
        except Exception as e:
            logger.error(f"读取 CSV 失败：{e}")
            raise ValueError(f"读取 CSV 失败：{e}")
        
        table_id = f"tbl_{uuid.uuid4().hex[:12]}"
        table_name = name or file_path.stem
        
        metadata = TableMetadata(
            table_id=table_id,
            name=table_name,
            description=description,
            source_file=str(file_path),
            source_type="csv",
            row_count=len(df),
            column_count=len(df.columns),
            columns=self._extract_column_info(df),
            tags=tags or []
        )
        
        self._create_table_from_df(table_id, df)
        self._save_metadata(metadata)
        self._tables[table_id] = metadata
        
        logger.info(f"CSV 导入成功：{table_name} ({len(df)} 行, {len(df.columns)} 列)")
        return metadata
    
    def import_excel(
        self,
        file_path: Union[str, Path],
        name: Optional[str] = None,
        description: str = "",
        tags: Optional[List[str]] = None,
        sheet_name: Optional[Union[str, int, List]] = None
    ) -> Union[TableMetadata, List[TableMetadata]]:
        """
        导入 Excel 文件
        
        Args:
            file_path: Excel 文件路径
            name: 表格名称（默认使用文件名）
            description: 表格描述
            tags: 标签列表
            sheet_name: 工作表名称/索引/列表，None 表示所有工作表
            
        Returns:
            单个表格元数据或列表
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在：{file_path}")
        
        try:
            if sheet_name is None:
                all_sheets = pd.read_excel(file_path, sheet_name=None)
                results = []
                base_name = name or file_path.stem
                
                for sheet_idx, (sheet_nm, df) in enumerate(all_sheets.items()):
                    table_id = f"tbl_{uuid.uuid4().hex[:12]}"
                    table_name = f"{base_name}_{sheet_nm}" if len(all_sheets) > 1 else base_name
                    
                    metadata = TableMetadata(
                        table_id=table_id,
                        name=table_name,
                        description=f"{description} (工作表: {sheet_nm})",
                        source_file=str(file_path),
                        source_type="excel",
                        row_count=len(df),
                        column_count=len(df.columns),
                        columns=self._extract_column_info(df),
                        tags=tags or []
                    )
                    
                    self._create_table_from_df(table_id, df)
                    self._save_metadata(metadata)
                    self._tables[table_id] = metadata
                    results.append(metadata)
                
                logger.info(f"Excel 导入成功：{len(results)} 个工作表")
                return results
            else:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                if isinstance(df, dict):
                    df = list(df.values())[0]
                
                table_id = f"tbl_{uuid.uuid4().hex[:12]}"
                table_name = name or file_path.stem
                
                metadata = TableMetadata(
                    table_id=table_id,
                    name=table_name,
                    description=description,
                    source_file=str(file_path),
                    source_type="excel",
                    row_count=len(df),
                    column_count=len(df.columns),
                    columns=self._extract_column_info(df),
                    tags=tags or []
                )
                
                self._create_table_from_df(table_id, df)
                self._save_metadata(metadata)
                self._tables[table_id] = metadata
                
                logger.info(f"Excel 导入成功：{table_name} ({len(df)} 行, {len(df.columns)} 列)")
                return metadata
                
        except Exception as e:
            logger.error(f"读取 Excel 失败：{e}")
            raise ValueError(f"读取 Excel 失败：{e}")
    
    def create_table(
        self,
        name: str,
        columns: List[Dict[str, str]],
        description: str = "",
        tags: Optional[List[str]] = None
    ) -> TableMetadata:
        """
        创建空表格
        
        Args:
            name: 表格名称
            columns: 列定义列表，如 [{"name": "id", "type": "INTEGER"}, ...]
            description: 表格描述
            tags: 标签列表
            
        Returns:
            表格元数据
        """
        table_id = f"tbl_{uuid.uuid4().hex[:12]}"
        db_table_name = self._get_table_name(table_id)
        
        column_defs = []
        for col in columns:
            col_name = col.get("name", "column")
            col_type = self._map_column_type(col.get("type", "TEXT"))
            column_defs.append(f"{col_name} {col_type}")
        
        create_sql = f"CREATE TABLE {db_table_name} ({', '.join(column_defs)})"
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(create_sql)
        conn.commit()
        conn.close()
        
        metadata = TableMetadata(
            table_id=table_id,
            name=name,
            description=description,
            source_type="manual",
            row_count=0,
            column_count=len(columns),
            columns=[{"name": c.get("name"), "type": c.get("type", "TEXT")} for c in columns],
            tags=tags or []
        )
        
        self._save_metadata(metadata)
        self._tables[table_id] = metadata
        
        logger.info(f"表格创建成功：{name}")
        return metadata
    
    def insert_rows(
        self,
        table_id: str,
        rows: List[Dict[str, Any]]
    ) -> int:
        """
        插入行数据
        
        Args:
            table_id: 表格 ID
            rows: 行数据列表
            
        Returns:
            插入的行数
        """
        if table_id not in self._tables:
            raise ValueError(f"表格不存在：{table_id}")
        
        if not rows:
            return 0
        
        db_table_name = self._get_table_name(table_id)
        columns = list(rows[0].keys())
        placeholders = ", ".join(["?" for _ in columns])
        column_names = ", ".join(columns)
        
        insert_sql = f"INSERT INTO {db_table_name} ({column_names}) VALUES ({placeholders})"
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        for row in rows:
            values = [row.get(col) for col in columns]
            cursor.execute(insert_sql, values)
        
        conn.commit()
        
        cursor.execute(f"SELECT COUNT(*) FROM {db_table_name}")
        new_count = cursor.fetchone()[0]
        conn.close()
        
        metadata = self._tables[table_id]
        metadata.row_count = new_count
        metadata.updated_at = datetime.now()
        self._save_metadata(metadata)
        
        logger.info(f"已插入 {len(rows)} 行到表格 {metadata.name}")
        return len(rows)
    
    def query(
        self,
        table_id: str,
        columns: Optional[List[str]] = None,
        where: Optional[str] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        查询表格数据
        
        Args:
            table_id: 表格 ID
            columns: 要查询的列（None 表示所有列）
            where: WHERE 条件
            order_by: 排序字段
            limit: 返回行数限制
            offset: 偏移量
            
        Returns:
            查询结果列表
        """
        if table_id not in self._tables:
            raise ValueError(f"表格不存在：{table_id}")
        
        db_table_name = self._get_table_name(table_id)
        
        select_cols = ", ".join(columns) if columns else "*"
        sql = f"SELECT {select_cols} FROM {db_table_name}"
        
        if where:
            sql += f" WHERE {where}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        if limit:
            sql += f" LIMIT {limit}"
        if offset:
            sql += f" OFFSET {offset}"
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        metadata = self._tables[table_id]
        col_names = [c["name"] for c in metadata.columns]
        
        cursor.execute(sql)
        rows = cursor.fetchall()
        conn.close()
        
        results = []
        for row in rows:
            results.append(dict(zip(col_names, row)))
        
        return results
    
    def execute_sql(
        self,
        table_id: str,
        sql: str
    ) -> List[Dict[str, Any]]:
        """
        在指定表格上执行 SQL 查询
        
        Args:
            table_id: 表格 ID
            sql: SQL 查询语句（使用 {table} 作为表名占位符）
            
        Returns:
            查询结果
        """
        if table_id not in self._tables:
            raise ValueError(f"表格不存在：{table_id}")
        
        db_table_name = self._get_table_name(table_id)
        actual_sql = sql.replace("{table}", db_table_name)
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        try:
            cursor.execute(actual_sql)
            
            if actual_sql.strip().upper().startswith("SELECT"):
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                results = [dict(zip(columns, row)) for row in rows]
            else:
                conn.commit()
                results = [{"affected_rows": cursor.rowcount}]
            
            return results
        except Exception as e:
            logger.error(f"SQL 执行失败：{e}")
            raise
        finally:
            conn.close()
    
    def get_table(self, table_id: str) -> Optional[TableMetadata]:
        """获取表格元数据"""
        return self._tables.get(table_id)
    
    def list_tables(
        self,
        tags: Optional[List[str]] = None,
        source_type: Optional[str] = None
    ) -> List[TableMetadata]:
        """
        列出表格
        
        Args:
            tags: 按标签过滤
            source_type: 按源类型过滤
            
        Returns:
            表格元数据列表
        """
        results = list(self._tables.values())
        
        if source_type:
            results = [t for t in results if t.source_type == source_type]
        
        if tags:
            results = [t for t in results if any(tag in t.tags for tag in tags)]
        
        return sorted(results, key=lambda x: x.updated_at, reverse=True)
    
    def delete_table(self, table_id: str) -> bool:
        """
        删除表格
        
        Args:
            table_id: 表格 ID
            
        Returns:
            是否成功
        """
        if table_id not in self._tables:
            return False
        
        db_table_name = self._get_table_name(table_id)
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute(f"DROP TABLE IF EXISTS {db_table_name}")
        cursor.execute("DELETE FROM table_registry WHERE table_id = ?", (table_id,))
        
        conn.commit()
        conn.close()
        
        del self._tables[table_id]
        logger.info(f"表格已删除：{table_id}")
        return True
    
    def get_schema(self, table_id: str) -> Dict[str, Any]:
        """
        获取表格结构
        
        Args:
            table_id: 表格 ID
            
        Returns:
            表格结构信息
        """
        metadata = self.get_table(table_id)
        if not metadata:
            raise ValueError(f"表格不存在：{table_id}")
        
        db_table_name = self._get_table_name(table_id)
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute(f"PRAGMA table_info({db_table_name})")
        columns_info = cursor.fetchall()
        conn.close()
        
        schema = {
            "table_id": table_id,
            "name": metadata.name,
            "description": metadata.description,
            "columns": []
        }
        
        for col in columns_info:
            schema["columns"].append({
                "name": col[1],
                "type": col[2],
                "not_null": bool(col[3]),
                "default": col[4],
                "primary_key": bool(col[5])
            })
        
        return schema
    
    def _extract_column_info(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """从 DataFrame 提取列信息"""
        columns = []
        for col_name in df.columns:
            dtype = str(df[col_name].dtype)
            col_type = self._infer_column_type(dtype)
            columns.append({
                "name": str(col_name),
                "type": col_type,
                "dtype": dtype,
                "nullable": bool(df[col_name].isna().any())
            })
        return columns
    
    def _infer_column_type(self, dtype: str) -> str:
        """推断列类型"""
        dtype_lower = dtype.lower()
        if "int" in dtype_lower:
            return "INTEGER"
        elif "float" in dtype_lower:
            return "REAL"
        elif "datetime" in dtype_lower or "date" in dtype_lower:
            return "TEXT"
        elif "bool" in dtype_lower:
            return "INTEGER"
        else:
            return "TEXT"
    
    def _map_column_type(self, type_str: str) -> str:
        """映射列类型到 SQLite 类型"""
        type_upper = type_str.upper()
        if type_upper in ("INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT"):
            return "INTEGER"
        elif type_upper in ("FLOAT", "DOUBLE", "REAL", "DECIMAL", "NUMERIC"):
            return "REAL"
        elif type_upper in ("TEXT", "VARCHAR", "CHAR", "STRING"):
            return "TEXT"
        elif type_upper in ("BLOB", "BINARY"):
            return "BLOB"
        else:
            return "TEXT"
    
    def _create_table_from_df(self, table_id: str, df: pd.DataFrame):
        """从 DataFrame 创建数据库表"""
        db_table_name = self._get_table_name(table_id)
        
        conn = sqlite3.connect(str(self.db_path))
        df.to_sql(db_table_name, conn, if_exists="replace", index=False)
        conn.close()


_store_instance: Optional[TableStore] = None


def get_table_store(storage_path: Optional[str] = None) -> TableStore:
    """获取表格存储实例"""
    global _store_instance
    if _store_instance is None:
        path = storage_path or "data/tables"
        _store_instance = TableStore(path)
    return _store_instance


def reset_table_store(storage_path: str) -> TableStore:
    """重置表格存储"""
    global _store_instance
    _store_instance = TableStore(storage_path)
    return _store_instance
