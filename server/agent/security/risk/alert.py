"""
风险预警机制
"""
import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from .scorer import RiskLevel, RiskScore


class AlertSeverity(str, Enum):
    """告警严重程度"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class RiskAlert:
    """风险告警"""
    alert_id: str
    severity: AlertSeverity
    risk_score: RiskScore
    message: str
    user_id: str | None = None
    operation: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "alert_id": self.alert_id,
            "severity": self.severity.value,
            "risk_score": self.risk_score.to_dict(),
            "message": self.message,
            "user_id": self.user_id,
            "operation": self.operation,
            "created_at": self.created_at.isoformat(),
            "acknowledged": self.acknowledged,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by,
            "metadata": self.metadata,
        }


class RiskAlertManager:
    """风险告警管理器"""

    LEVEL_SEVERITY_MAP = {
        RiskLevel.LOW: AlertSeverity.INFO,
        RiskLevel.MEDIUM: AlertSeverity.WARNING,
        RiskLevel.HIGH: AlertSeverity.ERROR,
        RiskLevel.CRITICAL: AlertSeverity.CRITICAL,
    }

    def __init__(self):
        self._alerts: list[RiskAlert] = []
        self._callbacks: list[Callable[[RiskAlert], Any]] = []
        self._thresholds: dict[RiskLevel, float] = {
            RiskLevel.LOW: 25.0,
            RiskLevel.MEDIUM: 50.0,
            RiskLevel.HIGH: 75.0,
            RiskLevel.CRITICAL: 90.0,
        }
        self._max_alerts = 10000
        self._lock = asyncio.Lock()
        self._alert_counter = 0

    def _generate_alert_id(self) -> str:
        """生成告警ID"""
        self._alert_counter += 1
        return f"alert_{datetime.now().strftime('%Y%m%d%H%M%S')}_{self._alert_counter}"

    def register_callback(self, callback: Callable[[RiskAlert], Any]) -> None:
        """注册告警回调"""
        self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[RiskAlert], Any]) -> None:
        """注销告警回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def set_threshold(self, level: RiskLevel, threshold: float) -> None:
        """设置阈值"""
        self._thresholds[level] = threshold

    async def check_and_alert(
        self,
        risk_score: RiskScore,
        user_id: str | None = None,
        operation: str | None = None,
        metadata: dict | None = None,
    ) -> RiskAlert | None:
        """检查并生成告警"""
        if risk_score.total_score < self._thresholds.get(RiskLevel.MEDIUM, 50.0):
            return None

        severity = self.LEVEL_SEVERITY_MAP.get(risk_score.level, AlertSeverity.WARNING)

        message = self._generate_alert_message(risk_score, operation)

        alert = RiskAlert(
            alert_id=self._generate_alert_id(),
            severity=severity,
            risk_score=risk_score,
            message=message,
            user_id=user_id,
            operation=operation,
            metadata=metadata or {},
        )

        async with self._lock:
            self._alerts.append(alert)

            if len(self._alerts) > self._max_alerts:
                self._alerts = self._alerts[-self._max_alerts:]

        await self._notify_callbacks(alert)

        return alert

    def _generate_alert_message(self, risk_score: RiskScore, operation: str | None) -> str:
        """生成告警消息"""
        level_text = {
            RiskLevel.LOW: "低",
            RiskLevel.MEDIUM: "中",
            RiskLevel.HIGH: "高",
            RiskLevel.CRITICAL: "严重",
        }

        op_text = f"操作 '{operation}'" if operation else "操作"

        factors_text = "、".join(risk_score.contributing_factors[:3])
        if len(risk_score.contributing_factors) > 3:
            factors_text += "等"

        return f"{op_text}检测到{level_text[risk_score.level]}风险（评分: {risk_score.total_score:.1f}），风险因素: {factors_text}"

    async def _notify_callbacks(self, alert: RiskAlert) -> None:
        """通知回调"""
        for callback in self._callbacks:
            try:
                result = callback(alert)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

    async def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        """确认告警"""
        async with self._lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id:
                    alert.acknowledged = True
                    alert.acknowledged_at = datetime.now()
                    alert.acknowledged_by = acknowledged_by
                    return True
            return False

    def get_alerts(
        self,
        severity: AlertSeverity | None = None,
        acknowledged: bool | None = None,
        user_id: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[RiskAlert]:
        """获取告警"""
        alerts = self._alerts

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        if acknowledged is not None:
            alerts = [a for a in alerts if a.acknowledged == acknowledged]

        if user_id:
            alerts = [a for a in alerts if a.user_id == user_id]

        if since:
            alerts = [a for a in alerts if a.created_at >= since]

        return alerts[-limit:]

    def get_unacknowledged_count(self) -> int:
        """获取未确认告警数量"""
        return sum(1 for a in self._alerts if not a.acknowledged)

    def get_alerts_by_severity(self) -> dict[AlertSeverity, int]:
        """按严重程度统计告警"""
        counts = dict.fromkeys(AlertSeverity, 0)
        for alert in self._alerts:
            counts[alert.severity] += 1
        return counts

    def get_alerts_by_hour(self, hours: int = 24) -> dict[int, int]:
        """按小时统计告警"""
        now = datetime.now()
        start = now - timedelta(hours=hours)

        counts = {}
        for i in range(hours):
            hour_start = start + timedelta(hours=i)
            hour_end = hour_start + timedelta(hours=1)
            counts[i] = sum(
                1 for a in self._alerts
                if hour_start <= a.created_at < hour_end
            )

        return counts

    async def cleanup_old_alerts(self, days: int = 30) -> int:
        """清理旧告警"""
        async with self._lock:
            cutoff = datetime.now() - timedelta(days=days)
            old_count = len(self._alerts)
            self._alerts = [a for a in self._alerts if a.created_at >= cutoff]
            return old_count - len(self._alerts)

    def clear_all_alerts(self) -> None:
        """清除所有告警"""
        self._alerts.clear()


_alert_manager: RiskAlertManager | None = None


def get_alert_manager() -> RiskAlertManager:
    """获取告警管理器单例"""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = RiskAlertManager()
    return _alert_manager
