"""
结构化数据 - 查询引擎
支持 SQL 查询和自然语言转 SQL
"""
import json
import logging
import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from rag.structured.db_connector import DatabaseConnector, QueryResult
from rag.structured.table_store import TableStore, get_table_store

logger = logging.getLogger(__name__)


class NLQueryContext(BaseModel):
    """自然语言查询上下文"""
    question: str = Field(..., description="用户问题")
    tables: list[str] = Field(default_factory=list, description="相关表名")
    columns: dict[str, list[str]] = Field(default_factory=dict, description="相关列")
    filters: dict[str, Any] = Field(default_factory=dict, description="过滤条件")
    aggregations: list[str] = Field(default_factory=list, description="聚合函数")
    order_by: str | None = Field(default=None, description="排序字段")
    limit: int | None = Field(default=None, description="结果限制")


class SQLGenerationResult(BaseModel):
    """SQL 生成结果"""
    sql: str = Field(..., description="生成的 SQL")
    explanation: str = Field(default="", description="SQL 解释")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度")
    tables_used: list[str] = Field(default_factory=list, description="使用的表")
    warnings: list[str] = Field(default_factory=list, description="警告信息")


class QueryHistory(BaseModel):
    """查询历史"""
    query_id: str = Field(..., description="查询 ID")
    query_type: str = Field(..., description="查询类型：sql/nl")
    query_text: str = Field(..., description="查询文本")
    generated_sql: str | None = Field(default=None, description="生成的 SQL")
    executed_sql: str | None = Field(default=None, description="执行的 SQL")
    success: bool = Field(default=False, description="是否成功")
    row_count: int = Field(default=0, description="返回行数")
    execution_time_ms: float = Field(default=0.0, description="执行时间")
    error: str | None = Field(default=None, description="错误信息")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


class QueryEngine:
    """查询引擎"""

    def __init__(
        self,
        table_store: TableStore | None = None,
        db_connector: DatabaseConnector | None = None,
        llm_client: Any | None = None
    ):
        """
        初始化查询引擎
        
        Args:
            table_store: 表格存储实例
            db_connector: 数据库连接器实例
            llm_client: LLM 客户端（用于自然语言转 SQL）
        """
        self.table_store = table_store or get_table_store()
        self.db_connector = db_connector
        self.llm_client = llm_client
        self._query_history: list[QueryHistory] = []
        self._schema_cache: dict[str, dict[str, Any]] = {}

    def execute_sql(
        self,
        sql: str,
        params: dict[str, Any] | tuple | None = None,
        limit: int | None = 1000
    ) -> QueryResult:
        """
        执行 SQL 查询
        
        Args:
            sql: SQL 语句
            params: 参数
            limit: 结果限制
            
        Returns:
            查询结果
        """
        if self.db_connector:
            return self.db_connector.query(sql, params, limit)
        else:
            result = QueryResult()
            result.success = False
            result.error = "未配置数据库连接器"
            return result

    def execute_table_query(
        self,
        table_id: str,
        sql: str
    ) -> list[dict[str, Any]]:
        """
        在表格存储上执行查询
        
        Args:
            table_id: 表格 ID
            sql: SQL 语句（使用 {table} 作为表名占位符）
            
        Returns:
            查询结果
        """
        return self.table_store.execute_sql(table_id, sql)

    def natural_language_to_sql(
        self,
        question: str,
        tables: list[str] | None = None,
        context: dict[str, Any] | None = None
    ) -> SQLGenerationResult:
        """
        自然语言转 SQL
        
        Args:
            question: 自然语言问题
            tables: 相关表名（可选，自动推断）
            context: 额外上下文
            
        Returns:
            SQL 生成结果
        """
        if self.llm_client:
            return self._llm_nl_to_sql(question, tables, context)
        else:
            return self._rule_based_nl_to_sql(question, tables, context)

    def _llm_nl_to_sql(
        self,
        question: str,
        tables: list[str] | None = None,
        context: dict[str, Any] | None = None
    ) -> SQLGenerationResult:
        """使用 LLM 进行自然语言转 SQL"""
        schema_info = self._get_schema_info(tables)

        prompt = f"""你是一个 SQL 专家。根据用户问题和数据库结构，生成合适的 SQL 查询。

数据库结构：
{json.dumps(schema_info, ensure_ascii=False, indent=2)}

用户问题：{question}

请生成 SQL 查询语句，并以 JSON 格式返回：
{{
    "sql": "SELECT ...",
    "explanation": "查询说明",
    "tables_used": ["表名"],
    "confidence": 0.9
}}

注意：
1. 只返回 JSON，不要有其他内容
2. 使用标准 SQL 语法
3. 表名和列名使用双引号
4. 只查询必要的数据，避免 SELECT *
"""

        try:
            response = self.llm_client.generate(prompt)

            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result_data = json.loads(json_match.group())

                return SQLGenerationResult(
                    sql=result_data.get("sql", ""),
                    explanation=result_data.get("explanation", ""),
                    confidence=result_data.get("confidence", 0.5),
                    tables_used=result_data.get("tables_used", [])
                )
        except Exception as e:
            logger.error(f"LLM SQL 生成失败：{e}")

        return self._rule_based_nl_to_sql(question, tables, context)

    def _rule_based_nl_to_sql(
        self,
        question: str,
        tables: list[str] | None = None,
        context: dict[str, Any] | None = None
    ) -> SQLGenerationResult:
        """基于规则的自然语言转 SQL"""
        question_lower = question.lower()

        if not tables:
            tables = self._infer_tables(question)

        if not tables:
            all_tables = self.table_store.list_tables()
            if all_tables:
                tables = [all_tables[0].name]

        if not tables:
            return SQLGenerationResult(
                sql="",
                explanation="无法确定查询的表",
                confidence=0.0,
                warnings=["未找到相关表"]
            )

        table_name = tables[0]

        select_columns = "*"
        where_clause = ""
        order_clause = ""
        limit_clause = ""

        if any(word in question_lower for word in ["多少", "数量", "总数", "count"]):
            select_columns = "COUNT(*) as count"
        elif any(word in question_lower for word in ["平均", "avg", "均值"]):
            numeric_cols = self._get_numeric_columns(table_name)
            if numeric_cols:
                select_columns = f"AVG({numeric_cols[0]}) as avg"
        elif any(word in question_lower for word in ["最大", "最高", "max"]):
            numeric_cols = self._get_numeric_columns(table_name)
            if numeric_cols:
                select_columns = f"MAX({numeric_cols[0]}) as max_value"
        elif any(word in question_lower for word in ["最小", "最低", "min"]):
            numeric_cols = self._get_numeric_columns(table_name)
            if numeric_cols:
                select_columns = f"MIN({numeric_cols[0]}) as min_value"
        elif any(word in question_lower for word in ["总和", "合计", "sum"]):
            numeric_cols = self._get_numeric_columns(table_name)
            if numeric_cols:
                select_columns = f"SUM({numeric_cols[0]}) as total"

        filter_patterns = [
            (r"等于\s*['\"]?(\w+)['\"]?", "= '{}'"),
            (r"是\s*['\"]?(\w+)['\"]?", "= '{}'"),
            (r"大于\s*(\d+)", "> {}"),
            (r"小于\s*(\d+)", "< {}"),
            (r"包含\s*['\"]?(\w+)['\"]?", "LIKE '%{}%'"),
        ]

        for pattern, template in filter_patterns:
            match = re.search(pattern, question_lower)
            if match:
                value = match.group(1)
                text_cols = self._get_text_columns(table_name)
                if text_cols:
                    where_clause = f" WHERE {text_cols[0]} {template.format(value)}"
                break

        if any(word in question_lower for word in ["排序", "排列", "order"]):
            sort_match = re.search(r"按\s*(\w+)\s*(升序|降序|asc|desc)?", question_lower)
            if sort_match:
                sort_col = sort_match.group(1)
                sort_dir = "DESC" if sort_match.group(2) in ["降序", "desc"] else "ASC"
                order_clause = f" ORDER BY {sort_col} {sort_dir}"

        limit_match = re.search(r"前\s*(\d+)\s*(条|个)?", question_lower)
        if limit_match:
            limit_clause = f" LIMIT {limit_match.group(1)}"
        elif "前" in question_lower or "top" in question_lower:
            limit_clause = " LIMIT 10"

        sql = f"SELECT {select_columns} FROM {table_name}{where_clause}{order_clause}{limit_clause}"

        return SQLGenerationResult(
            sql=sql,
            explanation=f"基于规则生成的查询，查询表 {table_name}",
            confidence=0.6,
            tables_used=[table_name],
            warnings=["使用规则引擎生成，建议验证 SQL 正确性"]
        )

    def _infer_tables(self, question: str) -> list[str]:
        """从问题推断相关表"""
        question_lower = question.lower()
        tables = self.table_store.list_tables()

        matched = []
        for table in tables:
            if table.name.lower() in question_lower:
                matched.append(table.name)
            for tag in table.tags:
                if tag.lower() in question_lower:
                    matched.append(table.name)
                    break

        return matched

    def _get_numeric_columns(self, table_name: str) -> list[str]:
        """获取表的数值列"""
        tables = self.table_store.list_tables()
        for table in tables:
            if table.name == table_name:
                return [
                    c["name"] for c in table.columns
                    if c.get("type") in ["INTEGER", "REAL"] or "int" in c.get("dtype", "").lower() or "float" in c.get("dtype", "").lower()
                ]
        return []

    def _get_text_columns(self, table_name: str) -> list[str]:
        """获取表的文本列"""
        tables = self.table_store.list_tables()
        for table in tables:
            if table.name == table_name:
                return [
                    c["name"] for c in table.columns
                    if c.get("type") == "TEXT" or "str" in c.get("dtype", "").lower() or "object" in c.get("dtype", "").lower()
                ]
        return []

    def _get_schema_info(self, tables: list[str] | None = None) -> dict[str, Any]:
        """获取数据库结构信息"""
        if tables:
            table_list = [t for t in self.table_store.list_tables() if t.name in tables]
        else:
            table_list = self.table_store.list_tables()

        schema_info = {}
        for table in table_list:
            schema_info[table.name] = {
                "columns": [
                    {"name": c["name"], "type": c.get("type", "TEXT")}
                    for c in table.columns
                ],
                "row_count": table.row_count,
                "description": table.description
            }

        return schema_info

    def query(
        self,
        query_text: str,
        query_type: str = "auto",
        tables: list[str] | None = None,
        context: dict[str, Any] | None = None,
        execute: bool = True
    ) -> dict[str, Any]:
        """
        执行查询（支持 SQL 和自然语言）
        
        Args:
            query_text: 查询文本（SQL 或自然语言）
            query_type: 查询类型（sql/nl/auto）
            tables: 相关表名
            context: 额外上下文
            execute: 是否执行查询
            
        Returns:
            查询结果
        """
        import time
        import uuid

        query_id = f"qry_{uuid.uuid4().hex[:12]}"
        start_time = time.time()

        result = {
            "query_id": query_id,
            "query_type": query_type,
            "query_text": query_text,
            "success": False,
            "sql": None,
            "explanation": None,
            "data": [],
            "row_count": 0,
            "execution_time_ms": 0.0,
            "error": None
        }

        if query_type == "auto":
            query_type = "sql" if self._is_sql(query_text) else "nl"

        result["query_type"] = query_type

        try:
            if query_type == "sql":
                sql = query_text
                result["sql"] = sql
                result["explanation"] = "直接执行 SQL 查询"
            else:
                nl_result = self.natural_language_to_sql(query_text, tables, context)
                sql = nl_result.sql
                result["sql"] = sql
                result["explanation"] = nl_result.explanation
                result["confidence"] = nl_result.confidence
                result["warnings"] = nl_result.warnings

                if not sql:
                    result["error"] = "无法生成有效的 SQL 查询"
                    return result

            if execute and sql:
                if self.db_connector:
                    query_result = self.execute_sql(sql)
                    result["success"] = query_result.success
                    result["data"] = query_result.rows
                    result["row_count"] = query_result.row_count
                    result["error"] = query_result.error
                else:
                    result["data"] = []
                    result["success"] = True
                    result["row_count"] = 0
                    result["warnings"] = result.get("warnings", []) + ["未配置数据库连接器，仅返回生成的 SQL"]

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"查询执行失败：{e}")

        result["execution_time_ms"] = (time.time() - start_time) * 1000

        history = QueryHistory(
            query_id=query_id,
            query_type=query_type,
            query_text=query_text,
            generated_sql=result.get("sql"),
            executed_sql=result.get("sql") if execute else None,
            success=result.get("success", False),
            row_count=result.get("row_count", 0),
            execution_time_ms=result["execution_time_ms"],
            error=result.get("error")
        )
        self._query_history.append(history)

        return result

    def _is_sql(self, text: str) -> bool:
        """判断是否是 SQL 语句"""
        sql_keywords = ["SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "WITH"]
        text_upper = text.strip().upper()
        return any(text_upper.startswith(kw) for kw in sql_keywords)

    def get_query_history(
        self,
        limit: int = 100,
        query_type: str | None = None,
        success_only: bool = False
    ) -> list[QueryHistory]:
        """
        获取查询历史
        
        Args:
            limit: 返回数量限制
            query_type: 按类型过滤
            success_only: 只返回成功的查询
            
        Returns:
            查询历史列表
        """
        history = self._query_history

        if query_type:
            history = [h for h in history if h.query_type == query_type]

        if success_only:
            history = [h for h in history if h.success]

        return history[-limit:]

    def suggest_queries(
        self,
        table_name: str | None = None,
        limit: int = 5
    ) -> list[str]:
        """
        建议查询示例
        
        Args:
            table_name: 表名（可选）
            limit: 返回数量
            
        Returns:
            查询示例列表
        """
        suggestions = []

        tables = self.table_store.list_tables()
        if not tables:
            return ["请先导入数据"]

        target_table = None
        if table_name:
            target_table = next((t for t in tables if t.name == table_name), None)

        if not target_table:
            target_table = tables[0]

        suggestions.append(f"查询 {target_table.name} 的所有数据")
        suggestions.append(f"统计 {target_table.name} 的记录数")

        numeric_cols = self._get_numeric_columns(target_table.name)
        if numeric_cols:
            suggestions.append(f"计算 {target_table.name} 中 {numeric_cols[0]} 平均值")
            suggestions.append(f"查找 {target_table.name} 中 {numeric_cols[0]} 最大的记录")

        text_cols = self._get_text_columns(target_table.name)
        if text_cols:
            suggestions.append(f"在 {target_table.name} 中搜索包含特定关键词的记录")

        return suggestions[:limit]

    def validate_sql(self, sql: str) -> dict[str, Any]:
        """
        验证 SQL 语法
        
        Args:
            sql: SQL 语句
            
        Returns:
            验证结果
        """
        result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "tables": [],
            "columns": []
        }

        dangerous_patterns = [
            r"DROP\s+TABLE",
            r"DROP\s+DATABASE",
            r"TRUNCATE",
            r"DELETE\s+FROM",
            r";\s*DROP",
            r"--",
            r"/\*"
        ]

        sql_upper = sql.upper()
        for pattern in dangerous_patterns:
            if re.search(pattern, sql_upper):
                result["warnings"].append(f"检测到潜在危险操作：{pattern}")

        table_pattern = r"(?:FROM|JOIN)\s+(\w+)"
        tables = re.findall(table_pattern, sql_upper, re.IGNORECASE)
        result["tables"] = tables

        column_pattern = r"SELECT\s+(.*?)\s+FROM"
        column_match = re.search(column_pattern, sql, re.IGNORECASE)
        if column_match:
            columns_str = column_match.group(1)
            if columns_str.strip() != "*":
                columns = [c.strip() for c in columns_str.split(",")]
                result["columns"] = columns

        return result

    def explain_query(self, sql: str) -> dict[str, Any]:
        """
        解释 SQL 查询
        
        Args:
            sql: SQL 语句
            
        Returns:
            解释结果
        """
        explanation = {
            "sql": sql,
            "type": None,
            "tables": [],
            "columns": [],
            "conditions": [],
            "joins": [],
            "group_by": None,
            "order_by": None,
            "limit": None,
            "description": ""
        }

        sql_upper = sql.upper().strip()

        if sql_upper.startswith("SELECT"):
            explanation["type"] = "SELECT"
            explanation["description"] = "这是一个查询语句，用于检索数据"
        elif sql_upper.startswith("INSERT"):
            explanation["type"] = "INSERT"
            explanation["description"] = "这是一个插入语句，用于添加新数据"
        elif sql_upper.startswith("UPDATE"):
            explanation["type"] = "UPDATE"
            explanation["description"] = "这是一个更新语句，用于修改数据"
        elif sql_upper.startswith("DELETE"):
            explanation["type"] = "DELETE"
            explanation["description"] = "这是一个删除语句，用于移除数据"
        else:
            explanation["type"] = "OTHER"
            explanation["description"] = "其他类型的 SQL 语句"

        table_pattern = r"(?:FROM|JOIN|INTO|UPDATE)\s+(\w+)"
        explanation["tables"] = re.findall(table_pattern, sql, re.IGNORECASE)

        if explanation["type"] == "SELECT":
            column_match = re.search(r"SELECT\s+(.*?)\s+FROM", sql, re.IGNORECASE | re.DOTALL)
            if column_match:
                columns_str = column_match.group(1)
                if columns_str.strip() != "*":
                    explanation["columns"] = [c.strip() for c in columns_str.split(",")]
                else:
                    explanation["columns"] = ["* (所有列)"]

        where_match = re.search(r"WHERE\s+(.*?)(?:GROUP BY|ORDER BY|LIMIT|$)", sql, re.IGNORECASE | re.DOTALL)
        if where_match:
            explanation["conditions"] = [where_match.group(1).strip()]

        join_pattern = r"(LEFT|RIGHT|INNER|OUTER)?\s*JOIN\s+(\w+)\s+ON\s+(.*?)(?:WHERE|GROUP BY|ORDER BY|LIMIT|JOIN|$)"
        joins = re.findall(join_pattern, sql, re.IGNORECASE)
        for join in joins:
            explanation["joins"].append({
                "type": join[0] or "INNER",
                "table": join[1],
                "condition": join[2].strip()
            })

        group_match = re.search(r"GROUP BY\s+(.*?)(?:HAVING|ORDER BY|LIMIT|$)", sql, re.IGNORECASE)
        if group_match:
            explanation["group_by"] = group_match.group(1).strip()

        order_match = re.search(r"ORDER BY\s+(.*?)(?:LIMIT|$)", sql, re.IGNORECASE)
        if order_match:
            explanation["order_by"] = order_match.group(1).strip()

        limit_match = re.search(r"LIMIT\s+(\d+)", sql, re.IGNORECASE)
        if limit_match:
            explanation["limit"] = int(limit_match.group(1))

        return explanation


_engine_instance: QueryEngine | None = None


def get_query_engine(
    table_store: TableStore | None = None,
    db_connector: DatabaseConnector | None = None,
    llm_client: Any | None = None
) -> QueryEngine:
    """获取查询引擎实例"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = QueryEngine(table_store, db_connector, llm_client)
    return _engine_instance


def reset_query_engine(
    table_store: TableStore | None = None,
    db_connector: DatabaseConnector | None = None,
    llm_client: Any | None = None
) -> QueryEngine:
    """重置查询引擎"""
    global _engine_instance
    _engine_instance = QueryEngine(table_store, db_connector, llm_client)
    return _engine_instance
