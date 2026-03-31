"""
意图检测方法 - BERT分类器

基于BERT模型的意图分类（适配统一数据模型）
"""
import logging
import threading

from ..models import ConfidenceLevel, DetectionMethod, IntentCategory, IntentResult

logger = logging.getLogger(__name__)

_bert_classifier_instance = None
_classifier_lock = threading.Lock()


class BERTClassifierAdapter:
    """BERT分类器适配器"""

    def __init__(self):
        self._classifier = None
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return

        with _classifier_lock:
            if self._initialized:
                return

            try:
                import os
                import sys
                parent_dir = os.path.dirname(os.path.dirname(__file__))
                if parent_dir not in sys.path:
                    sys.path.insert(0, parent_dir)

                from bert_classifier import get_bert_classifier
                self._classifier = get_bert_classifier()
                self._initialized = True

                if self._classifier.is_loaded():
                    logger.info("BERT分类器初始化成功")
                else:
                    logger.warning("BERT分类器模型未加载")
            except Exception as e:
                logger.warning(f"BERT分类器初始化失败: {e}")
                self._initialized = True

    def is_available(self) -> bool:
        self._ensure_initialized()
        return self._classifier is not None and self._classifier.is_loaded()

    def predict(
        self,
        text: str,
        session_id: str | None = None
    ) -> IntentResult | None:
        self._ensure_initialized()

        if self._classifier is None or not self._classifier.is_loaded():
            return None

        try:
            result = self._classifier.predict_with_params(text)

            return IntentResult(
                detected=True,
                intent_type=result.intent,
                action=result.intent,
                params=result.params,
                description=f"BERT分类: {result.intent}",
                confidence=result.confidence,
                confidence_level=ConfidenceLevel.from_score(result.confidence),
                method=DetectionMethod.BERT,
                category=IntentCategory.UNKNOWN,
                need_confirm=False,
                alternatives=[],
                raw_match=text,
                session_id=session_id
            )
        except Exception as e:
            logger.error(f"BERT预测失败: {e}")
            return None

    def predict_top_k(
        self,
        text: str,
        k: int = 3,
        session_id: str | None = None
    ) -> list[IntentResult]:
        self._ensure_initialized()

        results = []

        if self._classifier is None or not self._classifier.is_loaded():
            return results

        try:
            top_k_results = self._classifier.get_top_k_intents(text, k=k)

            for intent_name, confidence in top_k_results:
                results.append(IntentResult(
                    detected=True,
                    intent_type=intent_name,
                    action=intent_name,
                    params={},
                    description=f"BERT分类: {intent_name}",
                    confidence=confidence,
                    confidence_level=ConfidenceLevel.from_score(confidence),
                    method=DetectionMethod.BERT,
                    category=IntentCategory.UNKNOWN,
                    need_confirm=False,
                    alternatives=[],
                    raw_match=text,
                    session_id=session_id
                ))
        except Exception as e:
            logger.error(f"BERT Top-K预测失败: {e}")

        return results


def get_bert_classifier_adapter() -> BERTClassifierAdapter:
    global _bert_classifier_instance
    if _bert_classifier_instance is None:
        _bert_classifier_instance = BERTClassifierAdapter()
    return _bert_classifier_instance


bert_classifier = BERTClassifierAdapter()
