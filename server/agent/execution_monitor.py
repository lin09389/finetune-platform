"""
执行监控模块
统计操作执行成功率、失败原因、响应时间等指标
"""
import time
import threading
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
from enum import Enum
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class ExecutionStatus(str, Enum):
    """执行状态"""
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    PENDING = "pending"


@dataclass
class ExecutionRecord:
    """执行记录"""
    action: str
    status: ExecutionStatus
    duration_ms: float
    timestamp: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None
    error_category: Optional[str] = None
    params_hash: Optional[str] = None
    session_id: Optional[str] = None


@dataclass
class ActionStats:
    """操作统计"""
    action: str
    total_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    timeout_count: int = 0
    total_duration_ms: float = 0.0
    avg_duration_ms: float = 0.0
    max_duration_ms: float = 0.0
    min_duration_ms: float = float('inf')
    last_execution: Optional[datetime] = None
    error_categories: Dict[str, int] = field(default_factory=dict)
    
    @property
    def success_rate(self) -> float:
        if self.total_count == 0:
            return 0.0
        return self.success_count / self.total_count * 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "total_count": self.total_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "timeout_count": self.timeout_count,
            "success_rate": round(self.success_rate, 2),
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "max_duration_ms": round(self.max_duration_ms, 2),
            "min_duration_ms": round(self.min_duration_ms, 2) if self.min_duration_ms != float('inf') else 0,
            "last_execution": self.last_execution.isoformat() if self.last_execution else None,
            "error_categories": self.error_categories
        }


class ExecutionMonitor:
    """
    执行监控器
    
    统计操作执行成功率、失败原因、响应时间等指标
    """
    
    MAX_RECORDS = 10000
    ALERT_THRESHOLD_SUCCESS_RATE = 80.0
    ALERT_THRESHOLD_AVG_DURATION = 5000.0
    
    def __init__(self, storage_path: str = None):
        self._lock = threading.RLock()
        self._records: List[ExecutionRecord] = []
        self._stats: Dict[str, ActionStats] = defaultdict(lambda: ActionStats(action="unknown"))
        self._hourly_stats: Dict[str, Dict[int, ActionStats]] = defaultdict(dict)
        self._alerts: List[Dict[str, Any]] = []
        self._storage_path = Path(storage_path) if storage_path else None
        
        if self._storage_path:
            self._load_from_storage()
    
    def record(
        self,
        action: str,
        status: ExecutionStatus,
        duration_ms: float,
        error: str = None,
        error_category: str = None,
        session_id: str = None
    ) -> None:
        """
        记录执行结果
        
        Args:
            action: 操作类型
            status: 执行状态
            duration_ms: 执行耗时(毫秒)
            error: 错误信息
            error_category: 错误类别
            session_id: 会话ID
        """
        with self._lock:
            record = ExecutionRecord(
                action=action,
                status=status,
                duration_ms=duration_ms,
                error=error,
                error_category=error_category,
                session_id=session_id
            )
            
            self._records.append(record)
            
            if len(self._records) > self.MAX_RECORDS:
                self._records = self._records[-self.MAX_RECORDS:]
            
            self._update_stats(record)
            self._check_alerts(record)
            
            if self._storage_path:
                self._save_to_storage()
    
    def _update_stats(self, record: ExecutionRecord) -> None:
        """更新统计数据"""
        stats = self._stats[record.action]
        stats.action = record.action
        stats.total_count += 1
        stats.total_duration_ms += record.duration_ms
        stats.avg_duration_ms = stats.total_duration_ms / stats.total_count
        stats.max_duration_ms = max(stats.max_duration_ms, record.duration_ms)
        stats.min_duration_ms = min(stats.min_duration_ms, record.duration_ms)
        stats.last_execution = record.timestamp
        
        if record.status == ExecutionStatus.SUCCESS:
            stats.success_count += 1
        elif record.status == ExecutionStatus.FAILURE:
            stats.failure_count += 1
            if record.error_category:
                stats.error_categories[record.error_category] = \
                    stats.error_categories.get(record.error_category, 0) + 1
        elif record.status == ExecutionStatus.TIMEOUT:
            stats.timeout_count += 1
        
        hour = record.timestamp.hour
        if hour not in self._hourly_stats[record.action]:
            self._hourly_stats[record.action][hour] = ActionStats(action=record.action)
        
        hourly = self._hourly_stats[record.action][hour]
        hourly.total_count += 1
        hourly.total_duration_ms += record.duration_ms
        hourly.avg_duration_ms = hourly.total_duration_ms / hourly.total_count
        if record.status == ExecutionStatus.SUCCESS:
            hourly.success_count += 1
    
    def _check_alerts(self, record: ExecutionRecord) -> None:
        """检查告警条件"""
        stats = self._stats[record.action]
        
        if stats.total_count >= 10 and stats.success_rate < self.ALERT_THRESHOLD_SUCCESS_RATE:
            alert = {
                "type": "low_success_rate",
                "action": record.action,
                "success_rate": stats.success_rate,
                "threshold": self.ALERT_THRESHOLD_SUCCESS_RATE,
                "timestamp": datetime.now().isoformat(),
                "message": f"操作 {record.action} 成功率过低: {stats.success_rate:.1f}%"
            }
            self._alerts.append(alert)
            logger.warning(alert["message"])
        
        if stats.avg_duration_ms > self.ALERT_THRESHOLD_AVG_DURATION:
            alert = {
                "type": "high_latency",
                "action": record.action,
                "avg_duration_ms": stats.avg_duration_ms,
                "threshold": self.ALERT_THRESHOLD_AVG_DURATION,
                "timestamp": datetime.now().isoformat(),
                "message": f"操作 {record.action} 平均延迟过高: {stats.avg_duration_ms:.1f}ms"
            }
            self._alerts.append(alert)
            logger.warning(alert["message"])
    
    def get_stats(self, action: str = None) -> Dict[str, Any]:
        """
        获取统计数据
        
        Args:
            action: 操作类型，为None时返回所有统计
            
        Returns:
            Dict: 统计数据
        """
        with self._lock:
            if action:
                return self._stats.get(action, ActionStats(action=action)).to_dict()
            
            return {
                "actions": {k: v.to_dict() for k, v in self._stats.items()},
                "summary": self._get_summary()
            }
    
    def _get_summary(self) -> Dict[str, Any]:
        """获取总体摘要"""
        total_count = sum(s.total_count for s in self._stats.values())
        total_success = sum(s.success_count for s in self._stats.values())
        total_failure = sum(s.failure_count for s in self._stats.values())
        total_timeout = sum(s.timeout_count for s in self._stats.values())
        
        return {
            "total_executions": total_count,
            "total_success": total_success,
            "total_failure": total_failure,
            "total_timeout": total_timeout,
            "overall_success_rate": round(total_success / total_count * 100, 2) if total_count > 0 else 0,
            "actions_count": len(self._stats),
            "alerts_count": len(self._alerts)
        }
    
    def get_hourly_stats(self, action: str = None) -> Dict[str, Any]:
        """获取按小时统计的数据"""
        with self._lock:
            if action:
                return {
                    str(hour): stats.to_dict() 
                    for hour, stats in self._hourly_stats.get(action, {}).items()
                }
            
            return {
                action: {str(hour): stats.to_dict() for hour, stats in hourly.items()}
                for action, hourly in self._hourly_stats.items()
            }
    
    def get_alerts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取告警列表"""
        with self._lock:
            return self._alerts[-limit:]
    
    def get_recent_records(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近的执行记录"""
        with self._lock:
            return [
                {
                    "action": r.action,
                    "status": r.status.value,
                    "duration_ms": r.duration_ms,
                    "timestamp": r.timestamp.isoformat(),
                    "error": r.error,
                    "error_category": r.error_category
                }
                for r in self._records[-limit:]
            ]
    
    def get_error_analysis(self) -> Dict[str, Any]:
        """获取错误分析"""
        with self._lock:
            error_counts: Dict[str, int] = defaultdict(int)
            error_by_action: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
            
            for record in self._records:
                if record.status == ExecutionStatus.FAILURE and record.error_category:
                    error_counts[record.error_category] += 1
                    error_by_action[record.action][record.error_category] += 1
            
            return {
                "error_categories": dict(error_counts),
                "errors_by_action": {
                    action: dict(errors) 
                    for action, errors in error_by_action.items()
                }
            }
    
    def clear_alerts(self) -> None:
        """清除告警"""
        with self._lock:
            self._alerts.clear()
    
    def reset_stats(self) -> None:
        """重置统计"""
        with self._lock:
            self._records.clear()
            self._stats.clear()
            self._hourly_stats.clear()
            self._alerts.clear()
    
    def _save_to_storage(self) -> None:
        """保存到存储"""
        if not self._storage_path:
            return
        
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "stats": {k: v.to_dict() for k, v in self._stats.items()},
                "alerts": self._alerts[-100:],
                "last_updated": datetime.now().isoformat()
            }
            with open(self._storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存监控数据失败: {e}")
    
    def _load_from_storage(self) -> None:
        """从存储加载"""
        if not self._storage_path or not self._storage_path.exists():
            return
        
        try:
            with open(self._storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for action, stats_dict in data.get("stats", {}).items():
                stats = ActionStats(action=action)
                stats.total_count = stats_dict.get("total_count", 0)
                stats.success_count = stats_dict.get("success_count", 0)
                stats.failure_count = stats_dict.get("failure_count", 0)
                stats.timeout_count = stats_dict.get("timeout_count", 0)
                stats.avg_duration_ms = stats_dict.get("avg_duration_ms", 0)
                stats.max_duration_ms = stats_dict.get("max_duration_ms", 0)
                stats.min_duration_ms = stats_dict.get("min_duration_ms", 0) or float('inf')
                stats.error_categories = stats_dict.get("error_categories", {})
                self._stats[action] = stats
            
            self._alerts = data.get("alerts", [])
            logger.info(f"从 {self._storage_path} 加载监控数据")
        except Exception as e:
            logger.error(f"加载监控数据失败: {e}")


_execution_monitor: Optional[ExecutionMonitor] = None


def get_execution_monitor() -> ExecutionMonitor:
    """获取执行监控器单例"""
    global _execution_monitor
    if _execution_monitor is None:
        storage_path = Path.home() / ".finetune" / "execution_monitor.json"
        _execution_monitor = ExecutionMonitor(storage_path=str(storage_path))
    return _execution_monitor


def record_execution(
    action: str,
    success: bool,
    duration_ms: float,
    error: str = None,
    error_category: str = None,
    session_id: str = None
) -> None:
    """记录执行结果"""
    status = ExecutionStatus.SUCCESS if success else ExecutionStatus.FAILURE
    get_execution_monitor().record(
        action=action,
        status=status,
        duration_ms=duration_ms,
        error=error,
        error_category=error_category,
        session_id=session_id
    )


def get_execution_stats(action: str = None) -> Dict[str, Any]:
    """获取执行统计"""
    return get_execution_monitor().get_stats(action)


def get_execution_alerts(limit: int = 100) -> List[Dict[str, Any]]:
    """获取执行告警"""
    return get_execution_monitor().get_alerts(limit)
