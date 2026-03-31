"""
意图检测模块 - 统一数据模型

整合所有检测器的数据模型定义，消除重复代码
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class DetectionMethod(str, Enum):
    """检测方法类型"""
    RULE = "rule"
    SEMANTIC = "semantic"
    BERT = "bert"
    LLM = "llm"
    CONTEXT = "context"
    FUZZY = "fuzzy"
    HYBRID = "hybrid"


class ConfidenceLevel(str, Enum):
    """置信度等级"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"

    @classmethod
    def from_score(cls, score: float) -> "ConfidenceLevel":
        if score >= 0.85:
            return cls.HIGH
        elif score >= 0.65:
            return cls.MEDIUM
        elif score >= 0.45:
            return cls.LOW
        return cls.UNKNOWN


class IntentCategory(str, Enum):
    """意图类别"""
    FILE_OPERATION = "file_operation"
    APP_CONTROL = "app_control"
    BROWSER_OPERATION = "browser_operation"
    CUA_OPERATION = "cua_operation"
    SYSTEM_OPERATION = "system_operation"
    INFORMATION_QUERY = "information_query"
    CONVERSATION = "conversation"
    UNKNOWN = "unknown"


@dataclass
class IntentResult:
    """意图检测结果 - 统一数据结构"""
    detected: bool = False
    intent_type: str = ""
    action: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    confidence: float = 0.0
    confidence_level: ConfidenceLevel = field(default_factory=lambda: ConfidenceLevel.UNKNOWN)
    method: DetectionMethod = field(default_factory=lambda: DetectionMethod.RULE)
    category: IntentCategory = field(default_factory=lambda: IntentCategory.UNKNOWN)
    need_confirm: bool = False
    alternatives: list[tuple[str, float]] = field(default_factory=list)
    clarification: dict[str, Any] | None = None
    raw_match: str = ""
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected": self.detected,
            "intent_type": self.intent_type,
            "action": self.action,
            "params": self.params,
            "description": self.description,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level.value if isinstance(self.confidence_level, ConfidenceLevel) else self.confidence_level,
            "method": self.method.value if isinstance(self.method, DetectionMethod) else self.method,
            "category": self.category.value if isinstance(self.category, IntentCategory) else self.category,
            "need_confirm": self.need_confirm,
            "alternatives": self.alternatives,
            "clarification": self.clarification,
            "raw_match": self.raw_match,
            "session_id": self.session_id
        }


@dataclass
class MultiIntentResult:
    """多意图检测结果"""
    detected: bool = False
    intents: list[IntentResult] = field(default_factory=list)
    has_ambiguity: bool = False
    clarification_dialog: dict[str, Any] | None = None
    chain: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected": self.detected,
            "intents": [i.to_dict() for i in self.intents],
            "has_ambiguity": self.has_ambiguity,
            "clarification_dialog": self.clarification_dialog,
            "chain": self.chain
        }


@dataclass
class DetectionMetrics:
    """检测性能指标"""
    total_requests: int = 0
    successful_detections: int = 0
    failed_detections: int = 0
    total_response_time_ms: float = 0.0
    method_usage: dict[str, int] = field(default_factory=dict)
    intent_distribution: dict[str, int] = field(default_factory=dict)
    confidence_distribution: dict[str, int] = field(default_factory=lambda: {"high": 0, "medium": 0, "low": 0, "unknown": 0})
    
    # 评估指标
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    
    last_reset: datetime = field(default_factory=datetime.now)

    def record_detection(
        self,
        method: DetectionMethod,
        intent_type: str,
        confidence: float,
        response_time_ms: float,
        is_correct: bool | None = None
    ):
        self.total_requests += 1
        self.successful_detections += 1
        self.total_response_time_ms = (
            self.total_response_time_ms * (self.total_requests - 1) + response_time_ms
        ) / self.total_requests

        method_key = method.value if isinstance(method, DetectionMethod) else str(method)
        self.method_usage[method_key] = self.method_usage.get(method_key, 0) + 1
        self.intent_distribution[intent_type] = self.intent_distribution.get(intent_type, 0) + 1

        if confidence >= 0.85:
            self.confidence_distribution["high"] += 1
        elif confidence >= 0.65:
            self.confidence_distribution["medium"] += 1
        elif confidence >= 0.45:
            self.confidence_distribution["low"] += 1
        else:
            self.confidence_distribution["unknown"] += 1
            
        # 记录评估指标
        if is_correct is True:
            self.true_positives += 1
        elif is_correct is False:
            self.false_positives += 1

    def record_failure(self, response_time_ms: float, is_false_negative: bool = True):
        self.total_requests += 1
        self.failed_detections += 1
        self.total_response_time_ms = (
            self.total_response_time_ms * (self.total_requests - 1) + response_time_ms
        ) / self.total_requests
        
        if is_false_negative:
            self.false_negatives += 1

    def get_report(self) -> dict[str, Any]:
        success_rate = (
            self.successful_detections / self.total_requests
            if self.total_requests > 0 else 0
        )
        
        # 计算精度、召回率、F1
        precision = self.true_positives / (self.true_positives + self.false_positives) if (self.true_positives + self.false_positives) > 0 else 0
        recall = self.true_positives / (self.true_positives + self.false_negatives) if (self.true_positives + self.false_negatives) > 0 else 0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        return {
            "total_requests": self.total_requests,
            "successful_detections": self.successful_detections,
            "failed_detections": self.failed_detections,
            "success_rate": success_rate,
            "precision": precision,
            "recall": recall,
            "f1_score": f1_score,
            "average_response_time_ms": self.total_response_time_ms,
            "method_usage": self.method_usage,
            "intent_distribution": self.intent_distribution,
            "confidence_distribution": self.confidence_distribution,
            "uptime_seconds": (datetime.now() - self.last_reset).total_seconds()
        }

    def reset(self):
        self.total_requests = 0
        self.successful_detections = 0
        self.failed_detections = 0
        self.total_response_time_ms = 0.0
        self.method_usage.clear()
        self.intent_distribution.clear()
        self.confidence_distribution = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
        self.true_positives = 0
        self.false_positives = 0
        self.false_negatives = 0
        self.last_reset = datetime.now()


@dataclass
class ConversationContext:
    """对话上下文 - 统一会话管理"""
    session_id: str
    history: list[dict[str, Any]] = field(default_factory=list)
    recent_intents: list[str] = field(default_factory=list)
    mentioned_entities: dict[str, list[str]] = field(default_factory=dict)
    user_preferences: dict[str, Any] = field(default_factory=dict)
    current_task: str | None = None
    expecting_action: str | None = None
    last_intent: str | None = None
    last_params: dict[str, Any] = field(default_factory=dict)
    last_generated_content: str | None = None
    last_generated_type: str | None = None
    last_updated: datetime = field(default_factory=datetime.now)
    drift_rate: float = 0.0

    def __post_init__(self):
        if not self.history:
            self.history = []
        if not self.recent_intents:
            self.recent_intents = []
        if not self.mentioned_entities:
            self.mentioned_entities = {}
        if not self.user_preferences:
            self.user_preferences = {}
        if not self.last_params:
            self.last_params = {}

    def add_message(
        self,
        role: str,
        content: str,
        intent: str | None = None,
        entities: dict[str, Any] | None = None
    ):
        self.history.append({
            "role": role,
            "content": content,
            "intent": intent,
            "entities": entities or {},
            "timestamp": datetime.now().isoformat()
        })

        if len(self.history) > 20:
            self.history = self.history[-20:]

        if intent:
            self.recent_intents.append(intent)
            if len(self.recent_intents) > 10:
                self.recent_intents = self.recent_intents[-10:]
            self.last_intent = intent

        if entities:
            for key, value in entities.items():
                if isinstance(value, str):
                    if key not in self.mentioned_entities:
                        self.mentioned_entities[key] = []
                    self.mentioned_entities[key].append(value)
                    if len(self.mentioned_entities[key]) > 10:
                        self.mentioned_entities[key] = self.mentioned_entities[key][-10:]

        if role == "assistant" and content:
            self._extract_generated_content(content)

        if role == "user" and intent:
            self._update_drift(intent)

        self.last_updated = datetime.now()

    def _update_drift(self, current_intent: str):
        """计算意图漂移率"""
        if not self.recent_intents or len(self.recent_intents) < 2:
            return

        # 简单的漂移检测：如果当前意图与前两个意图均不同，则认为发生了漂移
        recent = self.recent_intents[-3:]
        if current_intent not in recent[:-1]:
            # 记录漂移点，计算滑动平均漂移率
            self.drift_rate = (self.drift_rate * 0.9) + (0.1 * 1.0)
        else:
            self.drift_rate = (self.drift_rate * 0.9) + (0.1 * 0.0)

    def _extract_generated_content(self, content: str):
        import re
        code_blocks = re.findall(r'```[\w]*\n(.*?)```', content, re.DOTALL)
        if code_blocks:
            self.last_generated_content = code_blocks[-1].strip()
            lang_match = re.search(r'```(\w+)', content)
            self.last_generated_type = lang_match.group(1) if lang_match else "code"
            self.user_preferences["last_generated_content"] = self.last_generated_content
            self.user_preferences["last_generated_type"] = self.last_generated_type

    def resolve_reference(self, reference: str) -> str | None:
        reference_map = {
            "它": "file_path",
            "这个": "file_path",
            "那个": "file_path",
            "这个文件": "file_path",
            "那个文件": "file_path",
            "这个目录": "directory",
            "那个目录": "directory",
            "这个应用": "app_name",
            "那个应用": "app_name",
            "这个网址": "url",
            "那个网址": "url",
            "刚才": "intent",
            "继续": "intent",
            "重复": "intent"
        }

        entity_type = reference_map.get(reference)
        if entity_type:
            if entity_type == "intent":
                if self.recent_intents:
                    return self.recent_intents[-1]
            elif entity_type in self.mentioned_entities:
                entities = self.mentioned_entities[entity_type]
                if entities:
                    if reference in ["那个", "刚才"]:
                        return entities[-2] if len(entities) > 1 else entities[-1]
                    return entities[-1]

        if reference in ["它", "这个", "那个"]:
            for entity_type in ["file_path", "directory", "app_name", "url"]:
                if entity_type in self.mentioned_entities and self.mentioned_entities[entity_type]:
                    return self.mentioned_entities[entity_type][-1]

        if reference in ["继续", "重复", "刚才"]:
            if self.recent_intents:
                return self.recent_intents[-1]

        return None


    def get_recent_intents(self, n: int = 5) -> list[str]:
        intents = []
        for msg in reversed(self.history[-n:]):
            if msg.get("intent"):
                intents.append(msg["intent"])
        return intents


    def set_generated_content(self, content: str, content_type: str = "text"):
        self.last_generated_content = content
        self.last_generated_type = content_type
        self.user_preferences["last_generated_content"] = content
        self.user_preferences["last_generated_type"] = content_type

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "history_count": len(self.history),
            "recent_intents": self.recent_intents[-5:],
            "mentioned_entities": dict(self.mentioned_entities),
            "last_intent": self.last_intent,
            "last_params": self.last_params,
            "current_task": self.current_task,
            "expecting_action": self.expecting_action
        }


@dataclass
class IntentDefinition:
    """意图定义 - 描述一个意图的元数据"""
    intent_type: str
    action: str
    description: str
    category: IntentCategory
    required_params: list[str] = field(default_factory=list)
    optional_params: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    dangerous: bool = False
    priority: int = 1
