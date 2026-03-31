"""
意图检测模块

统一意图检测入口，整合所有检测方法和处理器
"""
from .detector import (
    DetectorConfig,
    IntentDetector,
    create_detector,
    detector,
    get_detector,
)
from .models import (
    ConfidenceLevel,
    ConversationContext,
    DetectionMethod,
    DetectionMetrics,
    IntentCategory,
    IntentDefinition,
    IntentResult,
    MultiIntentResult,
)

UnifiedIntentDetector = IntentDetector

__all__ = [
    "IntentDetector",
    "DetectorConfig",
    "create_detector",
    "get_detector",
    "detector",
    "UnifiedIntentDetector",
    "IntentResult",
    "MultiIntentResult",
    "DetectionMethod",
    "ConfidenceLevel",
    "IntentCategory",
    "DetectionMetrics",
    "ConversationContext",
    "IntentDefinition",
]
