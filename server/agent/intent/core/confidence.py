"""
意图检测核心组件 - 统一置信度计算器

整合所有置信度计算逻辑，消除重复代码
"""
from dataclasses import dataclass
from typing import Any

from ..models import ConfidenceLevel, DetectionMethod


@dataclass
class ConfidenceFactors:
    rule_match: float = 0.0
    semantic_similarity: float = 0.0
    bert_confidence: float = 0.0
    llm_confidence: float = 0.0
    context_boost: float = 0.0
    param_completeness: float = 0.0
    keyword_match: float = 0.0


class ConfidenceCalculator:
    """统一置信度计算器"""

    WEIGHTS = {
        DetectionMethod.RULE: {
            "rule_match": 0.5,
            "keyword_match": 0.2,
            "param_completeness": 0.2,
            "context_boost": 0.1,
        },
        DetectionMethod.SEMANTIC: {
            "semantic_similarity": 0.6,
            "keyword_match": 0.15,
            "param_completeness": 0.15,
            "context_boost": 0.1,
        },
        DetectionMethod.BERT: {
            "bert_confidence": 0.6,
            "keyword_match": 0.15,
            "param_completeness": 0.15,
            "context_boost": 0.1,
        },
        DetectionMethod.LLM: {
            "llm_confidence": 0.7,
            "param_completeness": 0.2,
            "context_boost": 0.1,
        },
        DetectionMethod.CONTEXT: {
            "context_boost": 0.5,
            "keyword_match": 0.3,
            "param_completeness": 0.2,
        },
    }

    CONFIDENCE_THRESHOLDS = {
        ConfidenceLevel.HIGH: 0.85,
        ConfidenceLevel.MEDIUM: 0.65,
        ConfidenceLevel.LOW: 0.45,
    }

    def __init__(self):
        pass

    def calculate(
        self,
        method: DetectionMethod,
        factors: ConfidenceFactors,
        context_relevance: float = 0.0
    ) -> float:
        weights = self.WEIGHTS.get(method, self.WEIGHTS[DetectionMethod.RULE])

        confidence = 0.0

        if "rule_match" in weights:
            confidence += factors.rule_match * weights["rule_match"]

        if "semantic_similarity" in weights:
            confidence += factors.semantic_similarity * weights["semantic_similarity"]

        if "bert_confidence" in weights:
            confidence += factors.bert_confidence * weights["bert_confidence"]

        if "llm_confidence" in weights:
            confidence += factors.llm_confidence * weights["llm_confidence"]

        if "keyword_match" in weights:
            confidence += factors.keyword_match * weights["keyword_match"]

        if "param_completeness" in weights:
            confidence += factors.param_completeness * weights["param_completeness"]

        if "context_boost" in weights:
            context_factor = max(factors.context_boost, context_relevance)
            confidence += context_factor * weights["context_boost"]

        return min(1.0, max(0.0, confidence))

    def get_level(self, confidence: float) -> ConfidenceLevel:
        return ConfidenceLevel.from_score(confidence)

    def calculate_rule_confidence(
        self,
        pattern_match: bool,
        match_length: int,
        total_length: int,
        has_params: bool
    ) -> float:
        if not pattern_match:
            return 0.0

        base_confidence = 0.7

        length_ratio = min(1.0, match_length / max(1, total_length))
        length_boost = length_ratio * 0.15

        param_boost = 0.1 if has_params else 0.0

        return min(1.0, base_confidence + length_boost + param_boost)

    def calculate_semantic_confidence(
        self,
        similarity: float,
        has_keywords: bool,
        has_params: bool
    ) -> float:
        base_confidence = similarity * 0.8

        keyword_boost = 0.1 if has_keywords else 0.0
        param_boost = 0.1 if has_params else 0.0

        return min(1.0, base_confidence + keyword_boost + param_boost)

    def calculate_param_completeness(
        self,
        required_params: list[str],
        extracted_params: dict[str, Any]
    ) -> float:
        if not required_params:
            return 1.0

        provided_count = sum(
            1 for param in required_params
            if param in extracted_params and extracted_params[param] is not None
        )

        return provided_count / len(required_params)

    def calculate_context_boost(
        self,
        intent_type: str,
        recent_intents: list[str],
        mentioned_entities: dict[str, list[str]]
    ) -> float:
        boost = 0.0

        if intent_type in recent_intents:
            boost += 0.2

        if mentioned_entities:
            boost += min(0.2, len(mentioned_entities) * 0.05)

        return min(0.4, boost)

    def merge_confidences(
        self,
        confidences: dict[DetectionMethod, float],
        weights: dict[DetectionMethod, float] | None = None
    ) -> float:
        if not confidences:
            return 0.0

        if weights is None:
            default_weights = {
                DetectionMethod.RULE: 0.35,
                DetectionMethod.SEMANTIC: 0.25,
                DetectionMethod.BERT: 0.25,
                DetectionMethod.LLM: 0.15,
            }
            weights = default_weights

        total_weight = 0.0
        weighted_sum = 0.0

        for method, confidence in confidences.items():
            weight = weights.get(method, 0.1)
            weighted_sum += confidence * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0

        return weighted_sum / total_weight

    def should_use_llm_fallback(
        self,
        confidence: float,
        has_ambiguity: bool = False
    ) -> bool:
        if confidence < 0.45:
            return True

        if has_ambiguity and confidence < 0.65:
            return True

        return False

    def needs_clarification(
        self,
        confidence: float,
        param_completeness: float
    ) -> bool:
        if confidence < 0.65:
            return True

        if param_completeness < 0.5:
            return True

        return False


confidence_calculator = ConfidenceCalculator()
