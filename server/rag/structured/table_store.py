"""
结构化数据 - 表格存储
支持 CSV、Excel 文件导入和表格数据管理
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_DDL_KEYWORDS = {"DROP", "ALTER", "CREATE", "VACUUM", "REINDEX", "ATTACH", "DETACH", "PRAGMA"}


class TableMetadata(BaseModel):
    """表格元数据"""
    table_id: str = Field(..., description="表格唯一标识")
    name: str = Field(..., description="表格名称")
    description: str = Field(default="", description="表格描述")
    source_file: str | None = Field(default=None, description="源文件路径")
    source_type: str = Field(default="csv", description="源文件类型：csv/excel/manual")
    row_count: int = Field(default=0, description="行数")
    column_count: int = Field(default=0, description="列数")
    columns: list[dict[str, Any]] = Field(default_factory=list, description="列信息")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    tags: list[str] = Field(default_factory=list, description="标签")


class TableStore:
    """表格存储管理器"""

    def __init__(self, storage_path: str = "data/tables", db_path: str | None = None):
        """
        初始化表格存储

        Args:
            storage_path: 元数据文件存储路径
            db_path: SQLite 数据库路径，默认使用主应用数据库 data/app.db
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.metadata_path = self.storage_path / "metadata"
        self.metadata_path.mkdir(parents=True, exist_ok=True)

        self.db_path = db_path or "data/app.db"
        self._init_database()
        self._migrate_legacy_database()

        self._tables: dict[str, TableMetadata] = {}
        self._load_metadata()

    def _get_connection(self):
        """获取数据库连接（使用主应用连接池）"""
        from core.db_manager import get_db_pool
        return get_db_pool(self.db_path).get_connection()

    @contextmanager
    def _db(self):
        """获取可写数据库连接（自动管理事务）"""
        from core.db_manager import get_db_pool
        with get_db_pool(self.db_path).get_connection() as conn:
            yield conn

    def _validate_identifier(self, name: str, context: str = "identifier") -> str:
        if not _SAFE_IDENTIFIER_RE.match(name):
            raise ValueError(f"Invalid {context}: {name!r}")
        return name

    def _init_database(self):
        """初始化 SQLite 数据库"""
        with self._db() as conn:
            conn.execute("""
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
        logger.info(f"表格数据库已初始化：{self.db_path}")

    def _migrate_legacy_database(self) -> None:
        """将旧 tables.db 中的数据一次性迁移到新的主库。"""
        legacy_db = self.storage_path / "tables.db"
        target_db = Path(self.db_path)
        if not legacy_db.exists() or legacy_db.resolve() == target_db.resolve():
            return

        with sqlite3.connect(str(legacy_db)) as legacy_conn:
            legacy_conn.row_factory = sqlite3.Row
            registry_exists = legacy_conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='table_registry'"
            ).fetchone()
            if not registry_exists:
                return
            rows = legacy_conn.execute("SELECT * FROM table_registry").fetchall()
            legacy_tables = {
                row["name"]
                for row in legacy_conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'table_%'"
                ).fetchall()
            }

            with self._db() as conn:
                for row in rows:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO table_registry
                        (table_id, name, description, source_file, source_type, row_count, column_count, columns_json, created_at, updated_at, tags_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        tuple(row),
                    )
                    source_table = self._get_table_name(row["table_id"])
                    if source_table not in legacy_tables:
                        continue
                    already_exists = conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
                        (source_table,),
                    ).fetchone()
                    if already_exists:
                        continue
                    create_sql = legacy_conn.execute(
                        "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?",
                        (source_table,),
                    ).fetchone()
                    if not create_sql or not create_sql["sql"]:
                        continue
                    conn.execute(create_sql["sql"])
                    legacy_rows = legacy_conn.execute(f'SELECT * FROM "{source_table}"').fetchall()
                    if not legacy_rows:
                        continue
                    columns = [desc[1] for desc in legacy_conn.execute(f'PRAGMA table_info("{source_table}")').fetchall()]
                    placeholders = ", ".join("?" for _ in columns)
                    quoted_columns = ", ".join(f'"{column}"' for column in columns)
                    conn.executemany(
                        f'INSERT INTO "{source_table}" ({quoted_columns}) VALUES ({placeholders})',
                        [tuple(item) for item in legacy_rows],
                    )
        logger.info("已从旧 tables.db 迁移结构化表格数据")

    def _load_metadata(self):
        """加载所有表格元数据"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM table_registry")
            rows = cursor.fetchall()

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
        with self._db() as conn:
            conn.execute("""
                INSERT INTO table_registry
                (table_id, name, description, source_file, source_type, row_count, column_count, columns_json, created_at, updated_at, tags_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(table_id) DO UPDATE SET
                    name=excluded.name,
                    description=excluded.description,
                    source_file=excluded.source_file,
                    source_type=excluded.source_type,
                    row_count=excluded.row_count,
                    column_count=excluded.column_count,
                    columns_json=excluded.columns_json,
                    updated_at=excluded.updated_at,
                    tags_json=excluded.tags_json
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

    def _get_table_name(self, table_id: str) -> str:
        """获取数据库表名，校验 table_id 仅含安全字符"""
        clean = table_id.replace("-", "_")
        return f"table_{self._validate_identifier(clean, 'table_id')}"

    def import_csv(
        self,
        file_path: str | Path,
        name: str | None = None,
        description: str = "",
        tags: list[str] | None = None,
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
            import pandas as pd

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
        file_path: str | Path,
        name: str | None = None,
        description: str = "",
        tags: list[str] | None = None,
        sheet_name: str | int | list | None = None
    ) -> TableMetadata | list[TableMetadata]:
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
            import pandas as pd

            if sheet_name is None:
                all_sheets = pd.read_excel(file_path, sheet_name=None)
                results = []
                base_name = name or file_path.stem

                for _sheet_idx, (sheet_nm, df) in enumerate(all_sheets.items()):
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
        columns: list[dict[str, str]],
        description: str = "",
        tags: list[str] | None = None
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
            self._validate_identifier(col_name, "column name")
            col_type = self._map_column_type(col.get("type", "TEXT"))
            column_defs.append(f"\"{col_name}\" {col_type}")

        create_sql = f"CREATE TABLE {db_table_name} ({', '.join(column_defs)})"

        with self._db() as conn:
            conn.execute(create_sql)

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
        rows: list[dict[str, Any]]
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
        for col in columns:
            self._validate_identifier(col, "column name")
        placeholders = ", ".join(["?" for _ in columns])
        column_names = ", ".join(f"\"{c}\"" for c in columns)

        insert_sql = f"INSERT INTO {db_table_name} ({column_names}) VALUES ({placeholders})"

        with self._db() as conn:
            all_values = [[row.get(col) for col in columns] for row in rows]
            conn.execute("BEGIN")
            try:
                conn.executemany(insert_sql, all_values)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

            row = conn.execute(f"SELECT COUNT(*) FROM {db_table_name}").fetchone()
            new_count = row["count"] if isinstance(row, sqlite3.Row) else row[0]

        metadata = self._tables[table_id]
        metadata.row_count = new_count
        metadata.updated_at = datetime.now()
        self._save_metadata(metadata)

        logger.info(f"已插入 {len(rows)} 行到表格 {metadata.name}")
        return len(rows)

    def query(
        self,
        table_id: str,
        columns: list[str] | None = None,
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int | None = None
    ) -> list[dict[str, Any]]:
        """
        查询表格数据

        Args:
            table_id: 表格 ID
            columns: 要查询的列（None 表示所有列）
            where: WHERE 条件，接受以下格式：
                - str: 纯列名条件（如 "age > 18"），列名经过校验，值使用 ? 参数化（需配合 params 使用）
                - list[tuple[str, str, Any]]: 结构化条件（如 [("age", ">", 18)]）
                - None: 无条件
            order_by: 排序字段，接受以下格式：
                - str: 纯列名（如 "name ASC"），列名经过校验
                - list[tuple[str, str]]: 结构化排序（如 [("name", "ASC")]）
                - None: 不排序
            limit: 返回行数限制
            offset: 偏移量

        Returns:
            查询结果列表
        """
        if table_id not in self._tables:
            raise ValueError(f"表格不存在：{table_id}")

        db_table_name = self._get_table_name(table_id)

        if columns:
            validated_cols = [self._validate_identifier(c, "column name") for c in columns]
            select_cols = ", ".join(f"\"{c}\"" for c in validated_cols)
        else:
            select_cols = "*"
        sql = f"SELECT {select_cols} FROM {db_table_name}"
        params: list[Any] = []

        if where is not None:
            where_clause, where_params = self._build_where_clause(where)
            sql += f" WHERE {where_clause}"
            params.extend(where_params)
        if order_by is not None:
            sql += f" ORDER BY {self._build_order_clause(order_by)}"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        if offset is not None:
            sql += f" OFFSET {int(offset)}"

        with self._get_connection() as conn:
            metadata = self._tables[table_id]
            col_names = [c["name"] for c in metadata.columns]

            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        results = []
        for row in rows:
            results.append(dict(zip(col_names, row, strict=False)))

        return results

    def _build_where_clause(self, where: str | list[tuple[str, str, Any]]) -> tuple[str, list[Any]]:
        """构建参数化 WHERE 子句，返回 (clause, params)。"""
        _ALLOWED_OPS = {"=", "!=", "<", ">", "<=", ">=", "LIKE", "NOT LIKE", "IN", "NOT IN", "IS", "IS NOT"}
        if isinstance(where, list):
            parts: list[str] = []
            params: list[Any] = []
            for col, op, val in where:
                col = self._validate_identifier(col, "WHERE column")
                op_upper = op.upper().strip()
                if op_upper not in _ALLOWED_OPS:
                    raise ValueError(f"不允许的运算符: {op!r}")
                if op_upper in ("IS", "IS NOT"):
                    parts.append(f"\"{col}\" {op_upper} ?")
                    params.append(val)
                else:
                    parts.append(f"\"{col}\" {op_upper} ?")
                    params.append(val)
            return " AND ".join(parts), params
        # str 模式已废弃，强制使用列表模式以确保参数化查询
        raise ValueError("WHERE 子句必须使用列表格式 [(column, operator, value), ...]，不支持原始字符串")

    def _build_order_clause(self, order_by: str | list[tuple[str, str]]) -> str:
        """构建安全的 ORDER BY 子句。"""
        _ALLOWED_DIR = {"ASC", "DESC"}
        if isinstance(order_by, list):
            parts: list[str] = []
            for col, direction in order_by:
                col = self._validate_identifier(col, "ORDER BY column")
                direction = direction.upper().strip()
                if direction not in _ALLOWED_DIR:
                    raise ValueError(f"不允许的排序方向: {direction!r}")
                parts.append(f"\"{col}\" {direction}")
            return ", ".join(parts)
        # str 模式：校验后直接使用
        if ";" in str(order_by):
            raise ValueError("Semicolon not allowed in ORDER BY clause")
        return str(order_by)

    def execute_sql(
        self,
        table_id: str,
        sql: str,
        params: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        在指定表格上执行参数化 SQL 查询

        Args:
            table_id: 表格 ID
            sql: SQL 查询语句（使用 {table} 作为表名占位符，使用 ? 作为参数占位符）
            params: 查询参数列表

        Returns:
            查询结果
        """
        if table_id not in self._tables:
            raise ValueError(f"表格不存在：{table_id}")

        db_table_name = self._get_table_name(table_id)

        # 验证表名安全性
        import re as _re
        if not _re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', db_table_name):
            raise ValueError(f"不安全的表名: {db_table_name}")

        actual_sql = sql.replace("{table}", db_table_name)

        sql_upper = actual_sql.strip().upper()
        for keyword in _DDL_KEYWORDS:
            if sql_upper.startswith(keyword) or f" {keyword} " in sql_upper:
                raise ValueError(f"DDL statement ({keyword}) not allowed in execute_sql, use dedicated methods")

        # 仅允许 SELECT 语句，阻止 INSERT/UPDATE/DELETE 等写操作
        # 使用 lstrip() 去除前导空白和注释
        sql_stripped = actual_sql.strip()
        while sql_stripped.startswith("--"):
            sql_stripped = sql_stripped.split("\n", 1)[-1].strip() if "\n" in sql_stripped else ""
        if not sql_stripped.upper().startswith("SELECT"):
            raise ValueError("Only SELECT statements are allowed in execute_sql")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(actual_sql, params or [])

            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            return [dict(zip(columns, row, strict=False)) for row in rows]

    def get_table(self, table_id: str) -> TableMetadata | None:
        """获取表格元数据"""
        return self._tables.get(table_id)

    def list_tables(
        self,
        tags: list[str] | None = None,
        source_type: str | None = None
    ) -> list[TableMetadata]:
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

        with self._db() as conn:
            conn.execute(f"DROP TABLE IF EXISTS {db_table_name}")
            conn.execute("DELETE FROM table_registry WHERE table_id = ?", (table_id,))

        del self._tables[table_id]
        logger.info(f"表格已删除：{table_id}")
        return True

    def get_schema(self, table_id: str) -> dict[str, Any]:
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

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({db_table_name})")
            columns_info = cursor.fetchall()

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

    def _extract_column_info(self, df: pd.DataFrame) -> list[dict[str, Any]]:
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

        with self._get_connection() as conn:
            df.to_sql(db_table_name, conn, if_exists="replace", index=False)


_store_instance: TableStore | None = None


def get_table_store(storage_path: str | None = None, db_path: str | None = None) -> TableStore:
    """获取表格存储实例"""
    global _store_instance
    if _store_instance is None:
        path = storage_path or "data/tables"
        _store_instance = TableStore(path, db_path=db_path)
    return _store_instance


def reset_table_store(storage_path: str) -> TableStore:
    """重置表格存储"""
    global _store_instance
    _store_instance = TableStore(storage_path)
    return _store_instance
