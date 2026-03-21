# -*- coding: utf-8 -*-
"""
用户偏好学习模块

功能：
- 偏好提取算法
- 偏好存储和更新
- 偏好应用到技能参数
- 偏好冲突解决
"""
import json
import logging
import re
from typing import Dict, Any, Optional, List, Set, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from pathlib import Path
import uuid

logger = logging.getLogger(__name__)


@dataclass
class UserPreference:
    """用户偏好"""
    key: str
    value: Any
    confidence: float = 0.5
    source: str = "learned"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "access_count": self.access_count,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserPreference":
        return cls(
            key=data["key"],
            value=data["value"],
            confidence=data.get("confidence", 0.5),
            source=data.get("source", "learned"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(),
            access_count=data.get("access_count", 0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PreferenceConflict:
    """偏好冲突"""
    key: str
    existing_value: Any
    new_value: Any
    existing_confidence: float
    new_confidence: float
    resolution: Optional[str] = None
    resolved_value: Optional[Any] = None


class PreferenceExtractor:
    """
    偏好提取器
    
    从对话和操作中提取用户偏好
    """
    
    PATTERNS = [
        (r"我喜欢(.+?)(?:，|。|$)", "positive_preference"),
        (r"我不喜欢(.+?)(?:，|。|$)", "negative_preference"),
        (r"我偏好(.+?)(?:，|。|$)", "preference"),
        (r"我习惯(.+?)(?:，|。|$)", "habit"),
        (r"我不要|别(.+?)(?:，|。|$)", "negative_preference"),
        (r"用(.+?)(?:，|。|$)", "positive_preference"),
        (r"默认使用(.+?)(?:，|。|$)", "default_setting"),
        (r"设置(.+?)为(.+?)(?:，|。|$)", "setting"),
        (r"(.+?)用(.+?)(?:，|。|$)", "tool_preference"),
    ]
    
    @classmethod
    def extract_from_text(cls, text: str) -> List[Tuple[str, Any, float]]:
        """从文本中提取偏好"""
        preferences = []
        
        for pattern, pref_type in cls.PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                if pref_type == "setting":
                    key = match.group(1).strip()
                    value = match.group(2).strip()
                elif pref_type == "tool_preference":
                    key = f"tool_for_{match.group(1).strip()}"
                    value = match.group(2).strip()
                else:
                    key = match.group(1).strip()
                    value = True
                
                confidence = 0.7 if pref_type in ["setting", "default_setting"] else 0.5
                
                preferences.append((key, value, confidence))
        
        return preferences
    
    @classmethod
    def extract_from_operation(
        cls,
        operation_type: str,
        params: Dict[str, Any],
        result: Dict[str, Any]
    ) -> List[Tuple[str, Any, float]]:
        """从操作中提取偏好"""
        preferences = []
        
        if operation_type == "file_write":
            if "editor" in params:
                preferences.append(("preferred_editor", params["editor"], 0.6))
            if "style" in params:
                preferences.append(("code_style", params["style"], 0.5))
        
        elif operation_type == "web_browse":
            if "browser" in params:
                preferences.append(("preferred_browser", params["browser"], 0.6))
        
        elif operation_type == "command_execute":
            if "shell" in params:
                preferences.append(("preferred_shell", params["shell"], 0.6))
        
        if result.get("success") and result.get("user_feedback") == "positive":
            preferences.append((f"successful_{operation_type}", params, 0.7))
        
        return preferences


class PreferenceConflictResolver:
    """
    偏好冲突解决器
    """
    
    STRATEGIES = {
        "confidence": lambda old, new: old if old.confidence >= new.confidence else new,
        "recency": lambda old, new: new,
        "frequency": lambda old, new: old if old.access_count >= new.access_count else new,
        "merge": None,
    }
    
    @classmethod
    def resolve(
        cls,
        existing: UserPreference,
        new_pref: UserPreference,
        strategy: str = "confidence"
    ) -> UserPreference:
        """解决偏好冲突"""
        if strategy not in cls.STRATEGIES:
            strategy = "confidence"
        
        if strategy == "merge":
            if isinstance(existing.value, dict) and isinstance(new_pref.value, dict):
                merged_value = {**existing.value, **new_pref.value}
            elif isinstance(existing.value, list) and isinstance(new_pref.value, list):
                merged_value = list(set(existing.value + new_pref.value))
            else:
                merged_value = new_pref.value
            
            return UserPreference(
                key=existing.key,
                value=merged_value,
                confidence=max(existing.confidence, new_pref.confidence),
                source="merged",
                access_count=existing.access_count + 1,
            )
        
        resolver = cls.STRATEGIES[strategy]
        return resolver(existing, new_pref)


class UserPreferenceLearner:
    """
    用户偏好学习器
    
    功能：
    - 偏好提取
    - 偏好存储
    - 偏好更新
    - 偏好应用
    - 冲突解决
    """
    
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path("data/user_preferences")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self._preferences: Dict[str, Dict[str, UserPreference]] = {}
        self._conflict_strategy = "confidence"
        
        self._extractor = PreferenceExtractor()
        self._resolver = PreferenceConflictResolver()
    
    def set_conflict_strategy(self, strategy: str):
        """设置冲突解决策略"""
        self._conflict_strategy = strategy
    
    async def learn_from_text(
        self,
        text: str,
        user_id: str = "default"
    ) -> List[UserPreference]:
        """从文本学习偏好"""
        extracted = self._extractor.extract_from_text(text)
        
        learned = []
        for key, value, confidence in extracted:
            pref = await self._update_preference(user_id, key, value, confidence, "text")
            learned.append(pref)
        
        return learned
    
    async def learn_from_operation(
        self,
        operation_type: str,
        params: Dict[str, Any],
        result: Dict[str, Any],
        user_id: str = "default"
    ) -> List[UserPreference]:
        """从操作学习偏好"""
        extracted = self._extractor.extract_from_operation(
            operation_type, params, result
        )
        
        learned = []
        for key, value, confidence in extracted:
            pref = await self._update_preference(
                user_id, key, value, confidence, "operation"
            )
            learned.append(pref)
        
        return learned
    
    async def _update_preference(
        self,
        user_id: str,
        key: str,
        value: Any,
        confidence: float,
        source: str
    ) -> UserPreference:
        """更新偏好"""
        if user_id not in self._preferences:
            self._preferences[user_id] = {}
        
        existing = self._preferences[user_id].get(key)
        
        new_pref = UserPreference(
            key=key,
            value=value,
            confidence=confidence,
            source=source,
        )
        
        if existing:
            resolved = self._resolver.resolve(
                existing, new_pref, self._conflict_strategy
            )
            resolved.updated_at = datetime.now()
            self._preferences[user_id][key] = resolved
            self._persist_preference(user_id, resolved)
            return resolved
        else:
            self._preferences[user_id][key] = new_pref
            self._persist_preference(user_id, new_pref)
            return new_pref
    
    def get_preference(
        self,
        user_id: str,
        key: str,
        default: Any = None
    ) -> Any:
        """获取偏好值"""
        if user_id not in self._preferences:
            return default
        
        pref = self._preferences[user_id].get(key)
        if pref:
            pref.access_count += 1
            pref.updated_at = datetime.now()
            return pref.value
        
        return default
    
    def get_all_preferences(self, user_id: str) -> Dict[str, Any]:
        """获取用户所有偏好"""
        if user_id not in self._preferences:
            return {}
        
        return {
            key: pref.value
            for key, pref in self._preferences[user_id].items()
        }
    
    def get_preferences_by_prefix(self, user_id: str, prefix: str) -> Dict[str, Any]:
        """获取指定前缀的偏好"""
        if user_id not in self._preferences:
            return {}
        
        return {
            key: pref.value
            for key, pref in self._preferences[user_id].items()
            if key.startswith(prefix)
        }
    
    def apply_to_params(
        self,
        user_id: str,
        params: Dict[str, Any],
        param_mapping: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """将偏好应用到参数"""
        result = params.copy()
        
        if user_id not in self._preferences:
            return result
        
        mapping = param_mapping or {}
        
        for pref_key, pref in self._preferences[user_id].items():
            if pref_key in mapping:
                param_key = mapping[pref_key]
            else:
                param_key = pref_key
            
            if param_key not in result:
                result[param_key] = pref.value
        
        return result
    
    def delete_preference(self, user_id: str, key: str) -> bool:
        """删除偏好"""
        if user_id not in self._preferences:
            return False
        
        if key in self._preferences[user_id]:
            del self._preferences[user_id][key]
            self._delete_persisted_preference(user_id, key)
            return True
        
        return False
    
    def clear_preferences(self, user_id: str):
        """清除用户所有偏好"""
        if user_id in self._preferences:
            del self._preferences[user_id]
        
        user_file = self.storage_path / f"{user_id}.json"
        if user_file.exists():
            user_file.unlink()
    
    def _persist_preference(self, user_id: str, preference: UserPreference):
        """持久化偏好"""
        user_file = self.storage_path / f"{user_id}.json"
        
        try:
            data = {}
            if user_file.exists():
                with open(user_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            
            data[preference.key] = preference.to_dict()
            
            with open(user_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        
        except Exception as e:
            logger.error(f"持久化偏好失败: {e}")
    
    def _delete_persisted_preference(self, user_id: str, key: str):
        """删除持久化的偏好"""
        user_file = self.storage_path / f"{user_id}.json"
        
        try:
            if user_file.exists():
                with open(user_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                if key in data:
                    del data[key]
                    
                    with open(user_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
        
        except Exception as e:
            logger.error(f"删除持久化偏好失败: {e}")
    
    def load_preferences(self, user_id: str) -> int:
        """加载用户偏好"""
        user_file = self.storage_path / f"{user_id}.json"
        
        if not user_file.exists():
            return 0
        
        try:
            with open(user_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self._preferences[user_id] = {
                key: UserPreference.from_dict(pref_data)
                for key, pref_data in data.items()
            }
            
            return len(self._preferences[user_id])
        
        except Exception as e:
            logger.error(f"加载偏好失败: {e}")
            return 0
    
    def get_stats(self, user_id: str = "default") -> Dict[str, Any]:
        """获取统计信息"""
        prefs = self._preferences.get(user_id, {})
        
        return {
            "total_preferences": len(prefs),
            "by_source": self._count_by_attribute(prefs, "source"),
            "avg_confidence": sum(p.confidence for p in prefs.values()) / len(prefs) if prefs else 0,
            "total_access_count": sum(p.access_count for p in prefs.values()),
        }
    
    def _count_by_attribute(
        self,
        preferences: Dict[str, UserPreference],
        attr: str
    ) -> Dict[str, int]:
        """按属性统计"""
        counts = {}
        for pref in preferences.values():
            value = getattr(pref, attr, "unknown")
            counts[str(value)] = counts.get(str(value), 0) + 1
        return counts


_preference_learner: Optional[UserPreferenceLearner] = None


def get_preference_learner() -> UserPreferenceLearner:
    """获取偏好学习器单例"""
    global _preference_learner
    if _preference_learner is None:
        _preference_learner = UserPreferenceLearner()
    return _preference_learner
