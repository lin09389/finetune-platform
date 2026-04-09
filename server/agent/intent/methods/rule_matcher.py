"""
意图检测方法 - 规则匹配器

基于正则表达式的规则匹配
"""
import logging

from ..core.confidence import confidence_calculator
from ..core.patterns import RULE_PATTERNS
from ..models import ConfidenceLevel, DetectionMethod, IntentCategory, IntentResult

logger = logging.getLogger(__name__)


class RuleMatcher:
    """规则匹配器"""

    def __init__(self):
        self._patterns = RULE_PATTERNS

    def match(self, text: str, session_id: str | None = None) -> IntentResult | None:
        for rule in self._patterns:
            if rule.compiled_pattern is None:
                continue

            match = rule.compiled_pattern.search(text)
            if match:
                if rule.category == IntentCategory.CONVERSATION:
                    return IntentResult(
                        detected=False,
                        intent_type="conversation",
                        action=None,
                        params={},
                        description=rule.description,
                        confidence=1.0,
                        confidence_level=ConfidenceLevel.HIGH,
                        method=DetectionMethod.RULE,
                        category=IntentCategory.CONVERSATION,
                        need_confirm=False,
                        alternatives=[],
                        raw_match=match.group(0),
                        session_id=session_id
                    )

                try:
                    params = rule.params_extractor(match)
                except Exception as e:
                    logger.debug(f"参数提取失败: {e}")
                    params = {}

                confidence = confidence_calculator.calculate_rule_confidence(
                    pattern_match=True,
                    match_length=len(match.group(0)),
                    total_length=len(text),
                    has_params=bool(params)
                )

                return IntentResult(
                    detected=True,
                    intent_type=rule.action,
                    action=rule.action,
                    params=params,
                    description=rule.description,
                    confidence=confidence,
                    confidence_level=ConfidenceLevel.from_score(confidence),
                    method=DetectionMethod.RULE,
                    category=rule.category,
                    need_confirm=rule.need_confirm,
                    alternatives=[],
                    raw_match=match.group(0),
                    session_id=session_id
                )

        return None

    def match_all(self, text: str, session_id: str | None = None) -> list[IntentResult]:
        results = []
        for rule in self._patterns:
            if rule.compiled_pattern is None:
                continue

            match = rule.compiled_pattern.search(text)
            if match:
                try:
                    params = rule.params_extractor(match)
                except Exception:
                    params = {}

                confidence = confidence_calculator.calculate_rule_confidence(
                    pattern_match=True,
                    match_length=len(match.group(0)),
                    total_length=len(text),
                    has_params=bool(params)
                )

                results.append(IntentResult(
                    detected=True,
                    intent_type=rule.action,
                    action=rule.action,
                    params=params,
                    description=rule.description,
                    confidence=confidence,
                    confidence_level=ConfidenceLevel.from_score(confidence),
                    method=DetectionMethod.RULE,
                    category=rule.category,
                    need_confirm=rule.need_confirm,
                    alternatives=[],
                    raw_match=match.group(0),
                    session_id=session_id
                ))

        results.sort(key=lambda x: x.confidence, reverse=True)
        return results


rule_matcher = RuleMatcher()
