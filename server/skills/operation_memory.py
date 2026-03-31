import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class OperationRecord:
    operation_id: str
    operation_type: str
    skill_name: str
    parameters: dict[str, Any]
    result: dict[str, Any]
    success: bool
    timestamp: datetime
    duration_ms: float
    user_id: str = "default"
    session_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "skill_name": self.skill_name,
            "parameters": self.parameters,
            "result": self.result,
            "success": self.success,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OperationRecord":
        return cls(
            operation_id=data["operation_id"],
            operation_type=data["operation_type"],
            skill_name=data["skill_name"],
            parameters=data["parameters"],
            result=data["result"],
            success=data["success"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            duration_ms=data["duration_ms"],
            user_id=data.get("user_id", "default"),
            session_id=data.get("session_id"),
            context=data.get("context", {}),
        )


@dataclass
class UserPreference:
    key: str
    value: Any
    confidence: float
    learned_at: datetime
    source: str
    usage_count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
            "learned_at": self.learned_at.isoformat(),
            "source": self.source,
            "usage_count": self.usage_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserPreference":
        return cls(
            key=data["key"],
            value=data["value"],
            confidence=data["confidence"],
            learned_at=datetime.fromisoformat(data["learned_at"]),
            source=data["source"],
            usage_count=data.get("usage_count", 1),
        )


class OperationMemoryManager:
    def __init__(self, memory_service=None):
        self._memory_service = memory_service
        self._operation_history: dict[str, list[OperationRecord]] = defaultdict(list)
        self._user_preferences: dict[str, dict[str, UserPreference]] = defaultdict(dict)
        self._operation_patterns: dict[str, dict[str, Any]] = defaultdict(dict)
        self._max_history_per_user = 1000

    async def record_operation(self, record: OperationRecord) -> str:
        if not record.operation_id:
            record.operation_id = str(uuid.uuid4())

        user_history = self._operation_history[record.user_id]
        user_history.append(record)

        if len(user_history) > self._max_history_per_user:
            user_history.pop(0)

        await self._store_to_memory(record)
        await self.learn_from_operation(record)

        return record.operation_id

    async def _store_to_memory(self, record: OperationRecord) -> None:
        if self._memory_service:
            try:
                content = json.dumps(record.to_dict(), ensure_ascii=False)
                await self._memory_service.extract_and_store(
                    message=content,
                    role="assistant",
                    user_id=record.user_id,
                    metadata={
                        "type": "operation_record",
                        "skill_name": record.skill_name,
                        "success": record.success,
                    }
                )
            except Exception:
                pass

    async def get_operation_history(
        self,
        user_id: str = "default",
        skill_name: str | None = None,
        operation_type: str | None = None,
        limit: int = 100
    ) -> list[OperationRecord]:
        history = self._operation_history.get(user_id, [])

        filtered = history
        if skill_name:
            filtered = [r for r in filtered if r.skill_name == skill_name]
        if operation_type:
            filtered = [r for r in filtered if r.operation_type == operation_type]

        return filtered[-limit:]

    async def get_recent_operations(
        self,
        user_id: str = "default",
        count: int = 10
    ) -> list[OperationRecord]:
        history = self._operation_history.get(user_id, [])
        return history[-count:]

    async def store_preference(
        self,
        user_id: str,
        key: str,
        value: Any,
        source: str = "explicit"
    ) -> None:
        existing = self._user_preferences[user_id].get(key)

        if existing:
            existing.value = value
            existing.usage_count += 1
            existing.learned_at = datetime.now()
            if source == "explicit":
                existing.source = "explicit"
                existing.confidence = 1.0
            else:
                existing.confidence = min(1.0, existing.confidence + 0.1)
        else:
            self._user_preferences[user_id][key] = UserPreference(
                key=key,
                value=value,
                confidence=1.0 if source == "explicit" else 0.5,
                learned_at=datetime.now(),
                source=source,
            )

    async def get_preference(
        self,
        user_id: str,
        key: str
    ) -> Any | None:
        pref = self._user_preferences.get(user_id, {}).get(key)
        return pref.value if pref else None

    async def get_all_preferences(
        self,
        user_id: str = "default"
    ) -> dict[str, Any]:
        prefs = self._user_preferences.get(user_id, {})
        return {k: v.value for k, v in prefs.items()}

    async def learn_from_operation(self, record: OperationRecord) -> None:
        if not record.success:
            return

        for param_name, param_value in record.parameters.items():
            if isinstance(param_value, (str, int, float, bool)):
                pref_key = f"{record.skill_name}.{param_name}"
                await self.store_preference(
                    user_id=record.user_id,
                    key=pref_key,
                    value=param_value,
                    source="learned"
                )

        pattern_key = self._generate_pattern_key(record)
        pattern_data = self._operation_patterns[record.user_id].get(pattern_key, {
            "count": 0,
            "success_count": 0,
            "last_used": None,
            "parameters": record.parameters,
        })
        pattern_data["count"] += 1
        if record.success:
            pattern_data["success_count"] += 1
        pattern_data["last_used"] = datetime.now().isoformat()
        self._operation_patterns[record.user_id][pattern_key] = pattern_data

    def _generate_pattern_key(self, record: OperationRecord) -> str:
        param_str = json.dumps(record.parameters, sort_keys=True, ensure_ascii=False)
        return f"{record.skill_name}:{hash(param_str)}"

    async def detect_pattern(
        self,
        user_id: str = "default",
        skill_name: str | None = None
    ) -> dict[str, Any]:
        patterns = self._operation_patterns.get(user_id, {})

        result = {}
        for key, data in patterns.items():
            if skill_name and not key.startswith(skill_name):
                continue

            if data["count"] >= 2:
                success_rate = data["success_count"] / data["count"]
                result[key] = {
                    **data,
                    "success_rate": success_rate,
                }

        return result

    async def suggest_parameters(
        self,
        user_id: str,
        skill_name: str,
        current_params: dict[str, Any]
    ) -> dict[str, Any]:
        suggested = current_params.copy()

        prefs = self._user_preferences.get(user_id, {})
        for key, pref in prefs.items():
            if key.startswith(f"{skill_name}."):
                param_name = key.split(".", 1)[1]
                if param_name not in suggested or pref.confidence > 0.7:
                    suggested[param_name] = pref.value

        return suggested

    async def get_success_rate(
        self,
        user_id: str,
        skill_name: str | None = None
    ) -> float:
        history = self._operation_history.get(user_id, [])

        if skill_name:
            history = [r for r in history if r.skill_name == skill_name]

        if not history:
            return 0.0

        success_count = sum(1 for r in history if r.success)
        return success_count / len(history)

    async def clear_history(self, user_id: str = "default") -> None:
        self._operation_history[user_id] = []
        self._user_preferences[user_id] = {}
        self._operation_patterns[user_id] = {}

    async def get_statistics(self, user_id: str = "default") -> dict[str, Any]:
        history = self._operation_history.get(user_id, [])
        prefs = self._user_preferences.get(user_id, {})
        patterns = self._operation_patterns.get(user_id, {})

        skill_stats = defaultdict(lambda: {"count": 0, "success": 0})
        for record in history:
            skill_stats[record.skill_name]["count"] += 1
            if record.success:
                skill_stats[record.skill_name]["success"] += 1

        return {
            "total_operations": len(history),
            "total_preferences": len(prefs),
            "total_patterns": len(patterns),
            "skill_statistics": dict(skill_stats),
            "overall_success_rate": await self.get_success_rate(user_id),
        }


_operation_memory_manager: OperationMemoryManager | None = None


def get_operation_memory_manager() -> OperationMemoryManager:
    global _operation_memory_manager
    if _operation_memory_manager is None:
        _operation_memory_manager = OperationMemoryManager()
    return _operation_memory_manager


def reset_operation_memory_manager() -> OperationMemoryManager:
    global _operation_memory_manager
    _operation_memory_manager = OperationMemoryManager()
    return _operation_memory_manager
