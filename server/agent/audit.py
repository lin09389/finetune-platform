"""
审计日志模块 - 记录所有 Agent 操作

功能：
1. 结构化日志格式（JSON）
2. 日志持久化存储（文件 + SQLite）
3. 日志查询 API
4. 异常操作告警
5. 日志导出功能
"""
import asyncio
import csv
import io
import json
import logging
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from .config import ActionType

logger = logging.getLogger(__name__)


class AuditLogLevel(str, Enum):
    """审计日志级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditCategory(str, Enum):
    """审计日志分类"""
    FILE_OPERATION = "file_operation"
    SYSTEM_OPERATION = "system_operation"
    APPLICATION = "application"
    SECURITY = "security"
    ADMIN = "admin"
    OTHER = "other"


@dataclass
class AuditEntry:
    """审计日志条目"""
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    action: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    message: str = ""
    error: str | None = None
    duration: float = 0.0
    user_id: str | None = None
    user_ip: str | None = None
    session_id: str | None = None
    level: AuditLogLevel = AuditLogLevel.INFO
    category: AuditCategory = AuditCategory.OTHER
    client_info: dict[str, Any] = field(default_factory=dict)
    resource_path: str | None = None
    risk_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["level"] = self.level.value
        data["category"] = self.category.value
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class AnomalyRule:
    """异常规则定义"""

    def __init__(
        self,
        rule_id: str,
        name: str,
        check_func: Callable[[list[AuditEntry]], bool],
        severity: AuditLogLevel,
        message: str,
    ):
        self.rule_id = rule_id
        self.name = name
        self.check_func = check_func
        self.severity = severity
        self.message = message


class AuditLogger:
    """
    增强版审计日志记录器
    
    功能：
    1. 记录所有 Agent 操作
    2. 支持持久化存储（文件 + SQLite）
    3. 支持查询和统计
    4. 异常操作检测和告警
    5. 日志导出功能
    """

    DEFAULT_ANOMALY_RULES = [
        AnomalyRule(
            rule_id="high_failure_rate",
            name="高失败率",
            check_func=lambda entries: len(entries) >= 5 and sum(1 for e in entries if not e.success) / len(entries) > 0.5,
            severity=AuditLogLevel.WARNING,
            message="检测到高失败率操作",
        ),
        AnomalyRule(
            rule_id="rapid_operations",
            name="快速连续操作",
            check_func=lambda entries: len(entries) >= 10,
            severity=AuditLogLevel.WARNING,
            message="检测到快速连续操作",
        ),
        AnomalyRule(
            rule_id="sensitive_access",
            name="敏感资源访问",
            check_func=lambda entries: any(e.category == AuditCategory.SECURITY for e in entries),
            severity=AuditLogLevel.WARNING,
            message="检测到敏感资源访问",
        ),
    ]

    def __init__(
        self,
        log_dir: Path | None = None,
        max_entries: int = 10000,
        enable_db: bool = True,
        alert_callbacks: list[Callable] | None = None,
    ):
        self.log_dir = log_dir or Path("./logs/agent")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries
        self.enable_db = enable_db

        self._entries: list[AuditEntry] = []
        self._current_session: str | None = None
        self._alert_callbacks = alert_callbacks or []
        self._anomaly_rules = list(self.DEFAULT_ANOMALY_RULES)

        if enable_db:
            self._db_path = self.log_dir / "audit.db"
            self._init_db()

    def _init_db(self):
        """初始化数据库"""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    entry_id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    action TEXT,
                    params TEXT,
                    success INTEGER,
                    message TEXT,
                    error TEXT,
                    duration REAL,
                    user_id TEXT,
                    user_ip TEXT,
                    session_id TEXT,
                    level TEXT,
                    category TEXT,
                    client_info TEXT,
                    resource_path TEXT,
                    risk_score REAL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_logs(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_action ON audit_logs(action)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON audit_logs(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_id ON audit_logs(session_id)")
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"初始化审计数据库失败: {e}")
            self.enable_db = False

    def start_session(self, session_id: str | None = None) -> str:
        """开始新会话"""
        self._current_session = session_id or f"session_{uuid.uuid4().hex[:8]}"
        return self._current_session

    def end_session(self):
        """结束会话"""
        self._current_session = None

    def add_alert_callback(self, callback: Callable):
        """添加告警回调"""
        self._alert_callbacks.append(callback)

    def add_anomaly_rule(self, rule: AnomalyRule):
        """添加异常规则"""
        self._anomaly_rules.append(rule)

    async def _log_async(
        self,
        action: ActionType,
        params: dict[str, Any],
        result: Any,
        duration: float = 0.0,
        user_id: str | None = None,
        user_ip: str | None = None,
        client_info: dict | None = None,
        category: AuditCategory = AuditCategory.OTHER,
        risk_score: float | None = None,
    ):
        """记录操作日志"""
        success = result.success if hasattr(result, 'success') else True
        level = AuditLogLevel.ERROR if not success else AuditLogLevel.INFO

        resource_path = params.get("path") or params.get("file_path") or params.get("directory")

        entry = AuditEntry(
            timestamp=datetime.now().isoformat(),
            action=action.value if isinstance(action, ActionType) else str(action),
            params=self._sanitize_params(params),
            success=success,
            message=result.message if hasattr(result, 'message') else str(result),
            error=result.error if hasattr(result, 'error') else None,
            duration=duration,
            user_id=user_id,
            user_ip=user_ip,
            session_id=self._current_session,
            level=level,
            category=category,
            client_info=client_info or {},
            resource_path=resource_path,
            risk_score=risk_score,
        )

        self._entries.append(entry)

        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]

        await self._write_to_file(entry)

        if self.enable_db:
            await self._write_to_db(entry)

        await self._check_anomalies()

        log_msg = f"[AUDIT] {entry.action} - {'成功' if entry.success else '失败'} - {entry.duration:.2f}s"
        if entry.error:
            log_msg += f" - 错误: {entry.error}"
        logger.info(log_msg)

    def log(
        self,
        action: ActionType,
        params: dict[str, Any],
        result: Any,
        duration: float = 0.0,
        duration_ms: float | None = None,
        user_id: str | None = None,
        user_ip: str | None = None,
        client_info: dict | None = None,
        category: AuditCategory = AuditCategory.OTHER,
        risk_score: float | None = None,
    ):
        """Support both legacy sync callers and async contexts."""
        effective_duration = duration_ms if duration_ms is not None else duration
        coro = self._log_async(
            action=action,
            params=params,
            result=result,
            duration=effective_duration,
            user_id=user_id,
            user_ip=user_ip,
            client_info=client_info,
            category=category,
            risk_score=risk_score,
        )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coro)
            return None

        return loop.create_task(coro)

    def _sanitize_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """清理敏感参数"""
        sanitized = {}
        sensitive_keys = {'password', 'token', 'secret', 'key', 'credential', 'api_key', 'auth'}

        for k, v in params.items():
            if any(s in k.lower() for s in sensitive_keys):
                sanitized[k] = '***'
            elif isinstance(v, str) and len(v) > 500:
                sanitized[k] = v[:500] + '...(truncated)'
            else:
                sanitized[k] = v

        return sanitized

    async def _write_to_file(self, entry: AuditEntry):
        """写入日志文件"""
        try:
            date_str = datetime.now().strftime("%Y-%m-%d")
            log_file = self.log_dir / f"audit_{date_str}.jsonl"

            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(entry.to_json() + '\n')

        except Exception as e:
            logger.error(f"写入审计日志失败：{e}")

    async def _write_to_db(self, entry: AuditEntry):
        """写入数据库"""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.entry_id,
                entry.timestamp,
                entry.action,
                json.dumps(entry.params, ensure_ascii=False),
                1 if entry.success else 0,
                entry.message,
                entry.error,
                entry.duration,
                entry.user_id,
                entry.user_ip,
                entry.session_id,
                entry.level.value,
                entry.category.value,
                json.dumps(entry.client_info, ensure_ascii=False),
                entry.resource_path,
                entry.risk_score,
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"写入审计数据库失败: {e}")

    async def _check_anomalies(self):
        """检查异常操作"""
        recent_entries = self._entries[-20:]

        for rule in self._anomaly_rules:
            try:
                if rule.check_func(recent_entries):
                    await self._send_alert(rule, recent_entries)
            except Exception:
                pass

    async def _send_alert(self, rule: AnomalyRule, entries: list[AuditEntry]):
        """发送告警"""
        alert_data = {
            "rule_id": rule.rule_id,
            "rule_name": rule.name,
            "severity": rule.severity.value,
            "message": rule.message,
            "timestamp": datetime.now().isoformat(),
            "entry_count": len(entries),
        }

        for callback in self._alert_callbacks:
            try:
                result = callback(alert_data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"告警回调执行失败: {e}")

    def query(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        user_id: str | None = None,
        action: str | None = None,
        success: bool | None = None,
        category: AuditCategory | None = None,
        level: AuditLogLevel | None = None,
        session_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """查询日志"""
        if not self.enable_db:
            entries = self._entries
        else:
            entries = self._query_from_db(
                start_time, end_time, user_id, action, success, category, level, session_id, limit, offset
            )
            return entries

        if start_time:
            entries = [e for e in entries if datetime.fromisoformat(e.timestamp) >= start_time]
        if end_time:
            entries = [e for e in entries if datetime.fromisoformat(e.timestamp) <= end_time]
        if user_id:
            entries = [e for e in entries if e.user_id == user_id]
        if action:
            entries = [e for e in entries if e.action == action]
        if success is not None:
            entries = [e for e in entries if e.success == success]
        if category:
            entries = [e for e in entries if e.category == category]
        if level:
            entries = [e for e in entries if e.level == level]
        if session_id:
            entries = [e for e in entries if e.session_id == session_id]

        return [e.to_dict() for e in entries[offset:offset+limit]]

    def _query_from_db(
        self,
        start_time: datetime | None,
        end_time: datetime | None,
        user_id: str | None,
        action: str | None,
        success: bool | None,
        category: AuditCategory | None,
        level: AuditLogLevel | None,
        session_id: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        """从数据库查询"""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            sql = "SELECT * FROM audit_logs WHERE 1=1"
            params = []

            if start_time:
                sql += " AND timestamp >= ?"
                params.append(start_time.isoformat())
            if end_time:
                sql += " AND timestamp <= ?"
                params.append(end_time.isoformat())
            if user_id:
                sql += " AND user_id = ?"
                params.append(user_id)
            if action:
                sql += " AND action = ?"
                params.append(action)
            if success is not None:
                sql += " AND success = ?"
                params.append(1 if success else 0)
            if category:
                sql += " AND category = ?"
                params.append(category.value)
            if level:
                sql += " AND level = ?"
                params.append(level.value)
            if session_id:
                sql += " AND session_id = ?"
                params.append(session_id)

            sql += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(sql, params)
            rows = cursor.fetchall()
            conn.close()

            return [
                {
                    "entry_id": row[0],
                    "timestamp": row[1],
                    "action": row[2],
                    "params": json.loads(row[3]) if row[3] else {},
                    "success": bool(row[4]),
                    "message": row[5],
                    "error": row[6],
                    "duration": row[7],
                    "user_id": row[8],
                    "user_ip": row[9],
                    "session_id": row[10],
                    "level": row[11],
                    "category": row[12],
                    "client_info": json.loads(row[13]) if row[13] else {},
                    "resource_path": row[14],
                    "risk_score": row[15],
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"查询审计数据库失败: {e}")
            return []

    def export_json(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> str:
        """导出为 JSON"""
        entries = self.query(start_time, end_time, limit=10000)
        return json.dumps(entries, ensure_ascii=False, indent=2)

    def export_csv(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> str:
        """导出为 CSV"""
        entries = self.query(start_time, end_time, limit=10000)

        if not entries:
            return ""

        output = io.StringIO()
        fieldnames = ["timestamp", "action", "success", "message", "error", "duration", "user_id", "session_id", "level", "category"]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(entries)

        return output.getvalue()

    def get_recent_entries(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取最近的日志条目"""
        return [e.to_dict() for e in self._entries[-limit:]]

    def get_stats(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        """获取统计信息"""
        entries = self._entries

        if start_time:
            entries = [e for e in entries if datetime.fromisoformat(e.timestamp) >= start_time]
        if end_time:
            entries = [e for e in entries if datetime.fromisoformat(e.timestamp) <= end_time]

        if not entries:
            return {
                "total": 0,
                "success": 0,
                "failed": 0,
                "by_action": {},
                "by_category": {},
                "by_level": {},
                "avg_duration": 0.0,
            }

        stats = {
            "total": len(entries),
            "success": sum(1 for e in entries if e.success),
            "failed": sum(1 for e in entries if not e.success),
            "by_action": {},
            "by_category": {},
            "by_level": {},
            "avg_duration": sum(e.duration for e in entries) / len(entries),
        }

        for entry in entries:
            action = entry.action
            if action not in stats["by_action"]:
                stats["by_action"][action] = {"count": 0, "success": 0, "failed": 0}
            stats["by_action"][action]["count"] += 1
            if entry.success:
                stats["by_action"][action]["success"] += 1
            else:
                stats["by_action"][action]["failed"] += 1

            category = entry.category.value
            stats["by_category"][category] = stats["by_category"].get(category, 0) + 1

            level = entry.level.value
            stats["by_level"][level] = stats["by_level"].get(level, 0) + 1

        return stats

    def clear(self):
        """清空内存缓存"""
        self._entries.clear()
        logger.info("审计日志缓存已清空")

    async def cleanup_old_logs(self, days: int = 30) -> int:
        """清理旧日志"""
        cutoff = datetime.now() - timedelta(days=days)
        count = 0

        for log_file in self.log_dir.glob("audit_*.jsonl"):
            try:
                date_str = log_file.stem.replace("audit_", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                if file_date < cutoff:
                    log_file.unlink()
                    count += 1
            except Exception:
                pass

        if self.enable_db:
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM audit_logs WHERE timestamp < ?", (cutoff.isoformat(),))
                count += cursor.rowcount
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"清理数据库旧日志失败: {e}")

        return count


_audit_logger: AuditLogger | None = None


def get_audit_logger(log_dir: Path | None = None) -> AuditLogger:
    """获取全局审计日志实例"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger(log_dir)
    return _audit_logger
