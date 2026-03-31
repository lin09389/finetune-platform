"""
意图检测方法 - 语义匹配器

基于语义相似度的意图匹配（适配统一数据模型）
"""
import logging
import threading

from ..core.confidence import confidence_calculator
from ..models import ConfidenceLevel, DetectionMethod, IntentCategory, IntentResult

logger = logging.getLogger(__name__)

_semantic_matcher_instance = None
_matcher_lock = threading.Lock()


class SemanticMatcherAdapter:
    """语义匹配器适配器"""

    def __init__(self):
        self._matcher = None
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return

        with _matcher_lock:
            if self._initialized:
                return

            try:
                import os
                import sys
                parent_dir = os.path.dirname(os.path.dirname(__file__))
                if parent_dir not in sys.path:
                    sys.path.insert(0, parent_dir)

                from semantic_matcher import get_semantic_matcher
                self._matcher = get_semantic_matcher()
                self._initialized = True
                logger.info("语义匹配器初始化成功")
            except Exception as e:
                logger.warning(f"语义匹配器初始化失败: {e}")
                self._initialized = True

    def match(
        self,
        text: str,
        top_k: int = 3,
        threshold: float = 0.5,
        session_id: str | None = None
    ) -> list[IntentResult]:
        self._ensure_initialized()

        results = []

        if self._matcher is None:
            return results

        try:
            match_results = self._matcher.match(text, top_k=top_k, threshold=threshold)

            for mr in match_results:
                confidence = confidence_calculator.calculate_semantic_confidence(
                    similarity=mr.similarity,
                    has_keywords=len(mr.matched_samples) > 0,
                    has_params=False
                )

                results.append(IntentResult(
                    detected=True,
                    intent_type=mr.intent_name,
                    action=mr.intent_name,
                    params={},
                    description=f"语义匹配: {mr.intent_name}",
                    confidence=confidence,
                    confidence_level=ConfidenceLevel.from_score(confidence),
                    method=DetectionMethod.SEMANTIC,
                    category=IntentCategory.UNKNOWN,
                    need_confirm=False,
                    alternatives=[],
                    raw_match=text,
                    session_id=session_id
                ))
        except Exception as e:
            logger.error(f"语义匹配失败: {e}")

        return results

    def warmup(self, intent_samples: dict[str, list[str]]):
        self._ensure_initialized()

        if self._matcher:
            try:
                self._matcher.warmup(intent_samples)
            except Exception as e:
                logger.warning(f"语义匹配器预热失败: {e}")

    def load_samples(self, intent_samples: dict[str, list[str]]):
        self._ensure_initialized()

        if self._matcher:
            try:
                self._matcher.load_intent_samples(intent_samples)
            except Exception as e:
                logger.warning(f"加载语义样本失败: {e}")


def get_semantic_matcher_adapter() -> SemanticMatcherAdapter:
    global _semantic_matcher_instance
    if _semantic_matcher_instance is None:
        _semantic_matcher_instance = SemanticMatcherAdapter()
    return _semantic_matcher_instance


semantic_matcher = SemanticMatcherAdapter()
