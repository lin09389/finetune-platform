# -*- coding: utf-8 -*-
"""
操作记忆管理模块

功能：
- 扩展操作记忆类型定义
- 操作历史持久化
- 操作模式识别
- 操作回滚支持
"""
import json
import logging
from typing import Dict, Any, Optional, List, Callable, Awaitable
from datetime import datetime
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
import uuid

logger = logging.getLogger(__name__)


class OperationType(str, Enum):
    """操作类型"""
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    COMMAND_EXECUTE = "command_execute"
    WEB_BROWSE = "web_browse"
    WEB_CLICK = "web_click"
    WEB_INPUT = "web_input"
    CODE_EDIT = "code_edit"
    CODE_RUN = "code_run"
    SKILL_EXECUTE = "skill_execute"
    AGENT_MESSAGE = "agent_message"
    MEMORY_STORE = "memory_store"
    MEMORY_RECALL = "memory_recall"
    CUSTOM = "custom"


class OperationStatus(str, Enum):
    """操作状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


@dataclass
class OperationRecord:
    """操作记录"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    operation_type: OperationType = OperationType.CUSTOM
    status: OperationStatus = OperationStatus.PENDING
    description: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    rollback_data: Optional[Dict[str, Any]] = None
    parent_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: str = "default"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["operation_type"] = self.operation_type.value
        data["status"] = self.status.value
        data["created_at"] = self.created_at.isoformat()
        data["started_at"] = self.started_at.isoformat() if self.started_at else None
        data["completed_at"] = self.completed_at.isoformat() if self.completed_at else None
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OperationRecord":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            operation_type=OperationType(data.get("operation_type", "custom")),
            status=OperationStatus(data.get("status", "pending")),
            description=data.get("description", ""),
            params=data.get("params", {}),
            result=data.get("result"),
            error=data.get("error"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            rollback_data=data.get("rollback_data"),
            parent_id=data.get("parent_id"),
            session_id=data.get("session_id"),
            user_id=data.get("user_id", "default"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class OperationPattern:
    """操作模式"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    operation_sequence: List[OperationType] = field(default_factory=list)
    frequency: int = 0
    last_matched: Optional[datetime] = None
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["operation_sequence"] = [op.value for op in self.operation_sequence]
        data["last_matched"] = self.last_matched.isoformat() if self.last_matched else None
        return data


class OperationMemoryManager:
    """
    操作记忆管理器
    
    功能：
    - 操作历史持久化
    - 操作模式识别
    - 操作回滚支持
    """
    
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path("data/operation_memory")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self._operations: Dict[str, OperationRecord] = {}
        self._patterns: Dict[str, OperationPattern] = {}
        self._rollback_handlers: Dict[OperationType, Callable] = {}
        
        self._max_history_size = 1000
        self._pattern_window_size = 10
    
    def register_rollback_handler(
        self, 
        operation_type: OperationType, 
        handler: Callable[[OperationRecord], Awaitable[bool]]
    ):
        """注册回滚处理器"""
        self._rollback_handlers[operation_type] = handler
        logger.info(f"注册回滚处理器: {operation_type.value}")
    
    async def record_operation(
        self,
        operation_type: OperationType,
        description: str,
        params: Dict[str, Any],
        session_id: Optional[str] = None,
        user_id: str = "default",
        parent_id: Optional[str] = None,
        rollback_data: Optional[Dict[str, Any]] = None,
    ) -> OperationRecord:
        """记录操作"""
        record = OperationRecord(
            operation_type=operation_type,
            description=description,
            params=params,
            session_id=session_id,
            user_id=user_id,
            parent_id=parent_id,
            rollback_data=rollback_data,
        )
        
        self._operations[record.id] = record
        self._persist_operation(record)
        
        logger.debug(f"记录操作: {record.id} ({operation_type.value})")
        
        return record
    
    async def start_operation(self, operation_id: str) -> bool:
        """开始操作"""
        record = self._operations.get(operation_id)
        if not record:
            return False
        
        record.status = OperationStatus.RUNNING
        record.started_at = datetime.now()
        self._persist_operation(record)
        
        return True
    
    async def complete_operation(
        self, 
        operation_id: str, 
        result: Dict[str, Any]
    ) -> bool:
        """完成操作"""
        record = self._operations.get(operation_id)
        if not record:
            return False
        
        record.status = OperationStatus.SUCCESS
        record.result = result
        record.completed_at = datetime.now()
        self._persist_operation(record)
        
        await self._update_patterns(record)
        
        return True
    
    async def fail_operation(
        self, 
        operation_id: str, 
        error: str
    ) -> bool:
        """标记操作失败"""
        record = self._operations.get(operation_id)
        if not record:
            return False
        
        record.status = OperationStatus.FAILED
        record.error = error
        record.completed_at = datetime.now()
        self._persist_operation(record)
        
        return True
    
    async def rollback_operation(self, operation_id: str) -> bool:
        """回滚操作"""
        record = self._operations.get(operation_id)
        if not record:
            logger.warning(f"操作不存在: {operation_id}")
            return False
        
        if record.status != OperationStatus.SUCCESS:
            logger.warning(f"操作状态不允许回滚: {record.status}")
            return False
        
        if not record.rollback_data:
            logger.warning(f"操作没有回滚数据: {operation_id}")
            return False
        
        handler = self._rollback_handlers.get(record.operation_type)
        if not handler:
            logger.warning(f"没有注册回滚处理器: {record.operation_type}")
            return False
        
        try:
            success = await handler(record)
            
            if success:
                record.status = OperationStatus.ROLLED_BACK
                record.completed_at = datetime.now()
                self._persist_operation(record)
                logger.info(f"操作已回滚: {operation_id}")
                return True
            else:
                logger.error(f"回滚失败: {operation_id}")
                return False
        
        except Exception as e:
            logger.error(f"回滚异常: {e}", exc_info=True)
            return False
    
    async def _update_patterns(self, new_record: OperationRecord):
        """更新操作模式"""
        recent_ops = self.get_recent_operations(
            user_id=new_record.user_id,
            limit=self._pattern_window_size
        )
        
        if len(recent_ops) < 3:
            return
        
        op_sequence = [op.operation_type for op in recent_ops[-5:]]
        
        matched = False
        for pattern in self._patterns.values():
            if self._match_sequence(op_sequence, pattern.operation_sequence):
                pattern.frequency += 1
                pattern.last_matched = datetime.now()
                pattern.confidence = min(1.0, pattern.confidence + 0.1)
                matched = True
                break
        
        if not matched and len(op_sequence) >= 3:
            pattern = OperationPattern(
                name=f"Pattern_{len(self._patterns)}",
                operation_sequence=op_sequence[-3:],
                frequency=1,
                last_matched=datetime.now(),
                confidence=0.3,
            )
            self._patterns[pattern.id] = pattern
    
    def _match_sequence(
        self, 
        sequence: List[OperationType], 
        pattern: List[OperationType]
    ) -> bool:
        """检查序列是否匹配模式"""
        if len(sequence) < len(pattern):
            return False
        
        for i in range(len(sequence) - len(pattern) + 1):
            if sequence[i:i+len(pattern)] == pattern:
                return True
        
        return False
    
    def get_operation(self, operation_id: str) -> Optional[OperationRecord]:
        """获取操作记录"""
        return self._operations.get(operation_id)
    
    def get_recent_operations(
        self,
        user_id: Optional[str] = None,
        operation_type: Optional[OperationType] = None,
        session_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[OperationRecord]:
        """获取最近的操作"""
        operations = list(self._operations.values())
        
        if user_id:
            operations = [op for op in operations if op.user_id == user_id]
        if operation_type:
            operations = [op for op in operations if op.operation_type == operation_type]
        if session_id:
            operations = [op for op in operations if op.session_id == session_id]
        
        operations.sort(key=lambda x: x.created_at, reverse=True)
        return operations[:limit]
    
    def get_patterns(self, min_frequency: int = 2) -> List[OperationPattern]:
        """获取操作模式"""
        return [
            pattern for pattern in self._patterns.values()
            if pattern.frequency >= min_frequency
        ]
    
    def _persist_operation(self, record: OperationRecord):
        """持久化操作记录"""
        file_path = self.storage_path / f"{record.id}.json"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(record.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"持久化操作失败: {e}")
    
    def load_operation(self, operation_id: str) -> Optional[OperationRecord]:
        """加载操作记录"""
        file_path = self.storage_path / f"{operation_id}.json"
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return OperationRecord.from_dict(data)
        except Exception as e:
            logger.error(f"加载操作失败: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        status_counts = {}
        for status in OperationStatus:
            status_counts[status.value] = sum(
                1 for op in self._operations.values() if op.status == status
            )
        
        type_counts = {}
        for op_type in OperationType:
            type_counts[op_type.value] = sum(
                1 for op in self._operations.values() if op.operation_type == op_type
            )
        
        return {
            "total_operations": len(self._operations),
            "total_patterns": len(self._patterns),
            "status_counts": status_counts,
            "type_counts": type_counts,
        }


_operation_manager: Optional[OperationMemoryManager] = None


def get_operation_manager() -> OperationMemoryManager:
    """获取操作记忆管理器单例"""
    global _operation_manager
    if _operation_manager is None:
        _operation_manager = OperationMemoryManager()
    return _operation_manager
