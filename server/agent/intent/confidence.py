"""
置信度评估模块
评估意图匹配置信度，支持多因素综合评估
"""
import re
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ConfidenceLevel(Enum):
    """置信度等级"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ConfidenceResult:
    """置信度评估结果"""
    score: float
    factors: dict[str, float] = field(default_factory=dict)
    need_confirm: bool = False
    level: ConfidenceLevel = field(default=None)

    def __post_init__(self):
        if self.level is None:
            self.level = self._compute_level()
        self.need_confirm = self.score < 0.7

    def _compute_level(self) -> ConfidenceLevel:
        if self.score >= 0.85:
            return ConfidenceLevel.HIGH
        elif self.score >= 0.65:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "factors": self.factors,
            "need_confirm": self.need_confirm,
            "level": self.level.value
        }


class MultiFactorScorer:
    """多因素评分器"""

    DEFAULT_WEIGHTS = {
        "match_coverage": 0.25,
        "keyword_weight": 0.25,
        "pattern_specificity": 0.20,
        "param_completeness": 0.15,
        "context_consistency": 0.15
    }

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self._normalize_weights()

    def _normalize_weights(self):
        total = sum(self.weights.values())
        if total > 0:
            self.weights = {k: v / total for k, v in self.weights.items()}

    def compute_score(
        self,
        match_coverage: float = 0.0,
        keyword_weight: float = 0.0,
        pattern_specificity: float = 0.0,
        param_completeness: float = 0.0,
        context_consistency: float = 0.0
    ) -> tuple[float, dict[str, float]]:
        factors = {
            "match_coverage": match_coverage,
            "keyword_weight": keyword_weight,
            "pattern_specificity": pattern_specificity,
            "param_completeness": param_completeness,
            "context_consistency": context_consistency
        }

        score = sum(
            factors.get(k, 0) * v
            for k, v in self.weights.items()
        )

        return score, factors


class ConfidenceEvaluator:
    """置信度评估器"""

    def __init__(self, scorer: MultiFactorScorer | None = None):
        self.scorer = scorer or MultiFactorScorer()
        self._history: list[dict[str, Any]] = []
        self._correct_counts: dict[str, int] = defaultdict(int)
        self._total_counts: dict[str, int] = defaultdict(int)

    def evaluate(
        self,
        message: str,
        params: dict[str, Any],
        intent_name: str,
        context: dict[str, Any] | None = None
    ) -> ConfidenceResult:
        match_coverage = self._compute_match_coverage(message, params)
        keyword_weight = self._compute_keyword_weight(message, intent_name)
        pattern_specificity = self._compute_pattern_specificity(message)
        param_completeness = self._compute_param_completeness(params, intent_name)
        context_consistency = self._compute_context_consistency(intent_name, context)

        score, factors = self.scorer.compute_score(
            match_coverage=match_coverage,
            keyword_weight=keyword_weight,
            pattern_specificity=pattern_specificity,
            param_completeness=param_completeness,
            context_consistency=context_consistency
        )

        historical_boost = self._get_historical_boost(intent_name)
        score = min(1.0, score + historical_boost)

        return ConfidenceResult(score=score, factors=factors)

    def _compute_match_coverage(self, message: str, params: dict[str, Any]) -> float:
        if not params:
            return 0.0

        param_values = [str(v) for v in params.values() if v]
        if not param_values:
            return 0.0

        matched_length = sum(len(v) for v in param_values)
        return min(1.0, matched_length / len(message) if message else 0)

    def _compute_keyword_weight(self, message: str, intent_name: str) -> float:
        intent_keywords = {
            "file_create": ["创建", "新建", "生成", "建立"],
            "file_read": ["读取", "查看", "打开", "显示"],
            "file_write": ["写入", "修改", "更新", "编辑"],
            "file_delete": ["删除", "移除", "清除"],
            "file_list": ["列出", "显示", "查看", "ls"],
            "app_open": ["打开", "启动", "运行"],
            "url_open": ["打开", "访问", "http", "https"],
            "screenshot": ["截图", "截屏"],
            "mouse_click": ["点击", "单击", "双击"],
            "keyboard_type": ["输入", "打字"]
        }

        keywords = intent_keywords.get(intent_name, [])
        if not keywords:
            return 0.5

        matched = sum(1 for kw in keywords if kw in message.lower())
        return matched / len(keywords) if keywords else 0.5

    def _compute_pattern_specificity(self, message: str) -> float:
        specificity = 0.0

        if re.search(r'\.\w+', message):
            specificity += 0.3
        if re.search(r'https?://', message):
            specificity += 0.4
        if re.search(r'\d+[,，]\d+', message):
            specificity += 0.3
        if re.search(r'["「『].*[」』"]', message):
            specificity += 0.2

        return min(1.0, specificity)

    def _compute_param_completeness(self, params: dict[str, Any], intent_name: str) -> float:
        required_params = {
            "file_create": ["file_path"],
            "file_read": ["file_path"],
            "file_write": ["file_path"],
            "file_delete": ["file_path"],
            "file_list": [],
            "app_open": ["app_name"],
            "url_open": ["url"],
            "screenshot": [],
            "mouse_click": ["x", "y"],
            "keyboard_type": ["text"]
        }

        required = required_params.get(intent_name, [])
        if not required:
            return 1.0

        filled = sum(1 for p in required if params.get(p))
        return filled / len(required)

    def _compute_context_consistency(self, intent_name: str, context: dict[str, Any] | None) -> float:
        if not context:
            return 0.5

        recent_intents = context.get("recent_intents", [])
        if not recent_intents:
            return 0.5

        intent_chains = {
            "file_create": ["file_write"],
            "file_read": ["file_write", "file_delete"],
            "file_list": ["file_read", "file_create"]
        }

        expected_next = intent_chains.get(recent_intents[-1], [])
        if intent_name in expected_next:
            return 0.8

        return 0.5

    def _get_historical_boost(self, intent_name: str) -> float:
        total = self._total_counts.get(intent_name, 0)
        if total < 5:
            return 0.0

        correct = self._correct_counts.get(intent_name, 0)
        accuracy = correct / total

        if accuracy >= 0.9:
            return 0.1
        elif accuracy >= 0.8:
            return 0.05

        return 0.0

    def record_result(self, intent_name: str, is_correct: bool):
        self._total_counts[intent_name] += 1
        if is_correct:
            self._correct_counts[intent_name] += 1


def create_confidence_evaluator(weights: dict[str, float] | None = None) -> ConfidenceEvaluator:
    """创建置信度评估器"""
    scorer = MultiFactorScorer(weights) if weights else None
    return ConfidenceEvaluator(scorer)


def create_multi_factor_scorer(weights: dict[str, float] | None = None) -> MultiFactorScorer:
    """创建多因素评分器"""
    return MultiFactorScorer(weights)
