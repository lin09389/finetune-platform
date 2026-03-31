"""
审计日志模块

功能：
- 操作审计日志
- 敏感数据访问日志
- 审计日志查询
- 审计报告生成
"""
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """审计事件类型"""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    DATA_DELETION = "data_deletion"
    CONFIGURATION_CHANGE = "configuration_change"
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    ERROR = "error"
    SECURITY_VIOLATION = "security_violation"
    PERFORMANCE = "performance"
    API_CALL = "api_call"
    FILE_OPERATION = "file_operation"
    COMMAND_EXECUTION = "command_execution"
    SKILL_EXECUTION = "skill_execution"
    AGENT_ACTION = "agent_action"
    MEMORY_OPERATION = "memory_operation"


class AuditSeverity(str, Enum):
    """审计严重程度"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """审计事件"""
    event_type: AuditEventType
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    severity: AuditSeverity = AuditSeverity.INFO
    timestamp: datetime = field(default_factory=datetime.now)
    user_id: str | None = None
    session_id: str | None = None
    agent_id: str | None = None
    source_ip: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    action: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    result: str | None = None
    error_message: str | None = None
    duration_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "source_ip": self.source_ip,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "action": self.action,
            "details": self.details,
            "result": self.result,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


class AuditLogger:
    """
    审计日志记录器
    
    功能：
    - 记录审计事件
    - 查询审计日志
    - 生成审计报告
    - 敏感数据访问监控
    """

    def __init__(self, storage_path: Path | None = None):
        self.storage_path = storage_path or Path("data/audit_logs")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self._events: list[AuditEvent] = []
        self._max_events = 10000
        self._sensitive_resources: set[str] = {
            "password", "token", "api_key", "secret", "credential",
            "private_key", "ssh_key", "certificate",
        }

    def log_event(
        self,
        event_type: AuditEventType,
        severity: AuditSeverity = AuditSeverity.INFO,
        user_id: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        source_ip: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        action: str | None = None,
        details: dict[str, Any] | None = None,
        result: str | None = None,
        error_message: str | None = None,
        duration_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """记录审计事件"""
        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            source_ip=source_ip,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            details=details or {},
            result=result,
            error_message=error_message,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )

        self._events.append(event)

        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]

        self._persist_event(event)

        if severity in [AuditSeverity.ERROR, AuditSeverity.CRITICAL]:
            logger.warning(
                f"审计事件 [{event_type.value}]: {action or 'N/A'} - "
                f"{error_message or 'No error'}"
            )

        return event

    def log_authentication(
        self,
        user_id: str,
        success: bool,
        method: str,
        source_ip: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """记录认证事件"""
        return self.log_event(
            event_type=AuditEventType.AUTHENTICATION,
            severity=AuditSeverity.INFO if success else AuditSeverity.WARNING,
            user_id=user_id,
            source_ip=source_ip,
            action=f"authentication_{method}",
            details={
                "success": success,
                "method": method,
                **(details or {}),
            },
            result="success" if success else "failed",
        )

    def log_authorization(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        granted: bool,
        source_ip: str | None = None,
    ) -> AuditEvent:
        """记录授权事件"""
        return self.log_event(
            event_type=AuditEventType.AUTHORIZATION,
            severity=AuditSeverity.INFO if granted else AuditSeverity.WARNING,
            user_id=user_id,
            source_ip=source_ip,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            details={"granted": granted},
            result="granted" if granted else "denied",
        )

    def log_data_access(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        sensitive: bool = False,
        source_ip: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """记录数据访问事件"""
        return self.log_event(
            event_type=AuditEventType.DATA_ACCESS,
            severity=AuditSeverity.WARNING if sensitive else AuditSeverity.INFO,
            user_id=user_id,
            source_ip=source_ip,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            details={
                "sensitive": sensitive,
                **(details or {}),
            },
        )

    def log_api_call(
        self,
        user_id: str | None,
        endpoint: str,
        method: str,
        source_ip: str | None = None,
        duration_ms: float | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """记录 API 调用事件"""
        return self.log_event(
            event_type=AuditEventType.API_CALL,
            severity=AuditSeverity.INFO,
            user_id=user_id,
            source_ip=source_ip,
            action=f"{method} {endpoint}",
            details={
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                **(details or {}),
            },
            duration_ms=duration_ms,
        )

    def log_file_operation(
        self,
        user_id: str,
        file_path: str,
        operation: str,
        success: bool,
        source_ip: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """记录文件操作事件"""
        return self.log_event(
            event_type=AuditEventType.FILE_OPERATION,
            severity=AuditSeverity.INFO if success else AuditSeverity.WARNING,
            user_id=user_id,
            source_ip=source_ip,
            resource_type="file",
            resource_id=file_path,
            action=operation,
            details={
                "success": success,
                **(details or {}),
            },
            result="success" if success else "failed",
        )

    def log_command_execution(
        self,
        user_id: str,
        command: str,
        success: bool,
        source_ip: str | None = None,
        duration_ms: float | None = None,
        error_message: str | None = None,
    ) -> AuditEvent:
        """记录命令执行事件"""
        return self.log_event(
            event_type=AuditEventType.COMMAND_EXECUTION,
            severity=AuditSeverity.INFO if success else AuditSeverity.WARNING,
            user_id=user_id,
            source_ip=source_ip,
            action="execute_command",
            details={"command": command[:200]},
            result="success" if success else "failed",
            duration_ms=duration_ms,
            error_message=error_message,
        )

    def log_skill_execution(
        self,
        user_id: str,
        skill_name: str,
        success: bool,
        session_id: str | None = None,
        agent_id: str | None = None,
        duration_ms: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """记录技能执行事件"""
        return self.log_event(
            event_type=AuditEventType.SKILL_EXECUTION,
            severity=AuditSeverity.INFO if success else AuditSeverity.WARNING,
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            resource_type="skill",
            resource_id=skill_name,
            action="execute_skill",
            details={
                "skill_name": skill_name,
                **(details or {}),
            },
            result="success" if success else "failed",
            duration_ms=duration_ms,
        )

    def log_security_violation(
        self,
        violation_type: str,
        user_id: str | None,
        source_ip: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """记录安全违规事件"""
        return self.log_event(
            event_type=AuditEventType.SECURITY_VIOLATION,
            severity=AuditSeverity.CRITICAL,
            user_id=user_id,
            source_ip=source_ip,
            action=violation_type,
            details=details or {},
            result="violation_detected",
        )

    def query_events(
        self,
        user_id: str | None = None,
        event_type: AuditEventType | None = None,
        severity: AuditSeverity | None = None,
        resource_type: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """查询审计事件"""
        events = self._events

        if user_id:
            events = [e for e in events if e.user_id == user_id]
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if severity:
            events = [e for e in events if e.severity == severity]
        if resource_type:
            events = [e for e in events if e.resource_type == resource_type]
        if start_time:
            events = [e for e in events if e.timestamp >= start_time]
        if end_time:
            events = [e for e in events if e.timestamp <= end_time]

        return events[:limit]

    def get_recent_events(self, limit: int = 50) -> list[AuditEvent]:
        """获取最近的事件"""
        return self._events[-limit:]

    def generate_report(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """生成审计报告"""
        events = self.query_events(
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
            limit=1000,
        )

        event_type_counts: dict[str, int] = {}
        severity_counts: dict[str, int] = {}
        user_counts: dict[str, int] = {}

        for event in events:
            et = event.event_type.value
            event_type_counts[et] = event_type_counts.get(et, 0) + 1

            sev = event.severity.value
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

            if event.user_id:
                user_counts[event.user_id] = user_counts.get(event.user_id, 0) + 1

        return {
            "report_time": datetime.now().isoformat(),
            "time_range": {
                "start": start_time.isoformat() if start_time else None,
                "end": end_time.isoformat() if end_time else None,
            },
            "total_events": len(events),
            "event_type_distribution": event_type_counts,
            "severity_distribution": severity_counts,
            "unique_users": len(user_counts),
            "top_users": sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:10],
            "events": [e.to_dict() for e in events[:100]],
        }

    def _persist_event(self, event: AuditEvent):
        """持久化事件"""
        date_str = event.timestamp.strftime("%Y-%m-%d")
        file_path = self.storage_path / f"audit_{date_str}.jsonl"

        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"持久化审计事件失败: {e}")

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        severity_counts: dict[str, int] = {}
        for event in self._events:
            sev = event.severity.value
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        return {
            "total_events": len(self._events),
            "severity_distribution": severity_counts,
            "oldest_event": self._events[0].timestamp.isoformat() if self._events else None,
            "newest_event": self._events[-1].timestamp.isoformat() if self._events else None,
        }


_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """获取审计日志记录器单例"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


audit_logger = get_audit_logger()
