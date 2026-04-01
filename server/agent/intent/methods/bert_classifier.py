"""
BERT intent detection adapter.

Wraps the legacy BERT classifier and normalizes it to the unified
`IntentResult` contract used by the detector pipeline.
"""

import logging
import threading

from ..bert_classifier import get_bert_classifier
from ..models import ConfidenceLevel, DetectionMethod, IntentCategory, IntentResult

logger = logging.getLogger(__name__)

_bert_classifier_instance = None
_classifier_lock = threading.Lock()


class BERTClassifierAdapter:
    """Adapter around the legacy BERT classifier singleton."""

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
                self._classifier = get_bert_classifier()
                if self._classifier and self._classifier.is_loaded():
                    logger.info("BERT intent classifier initialized")
                else:
                    logger.warning(
                        "BERT intent classifier model not loaded; using degraded mode"
                    )
            except Exception as exc:
                logger.warning(f"BERT intent classifier initialization failed: {exc}")
                self._classifier = None
            finally:
                self._initialized = True

    def is_available(self) -> bool:
        self._ensure_initialized()
        return self._classifier is not None and self._classifier.is_loaded()

    def predict(
        self,
        text: str,
        session_id: str | None = None,
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
                description=f"BERT classifier: {result.intent}",
                confidence=result.confidence,
                confidence_level=ConfidenceLevel.from_score(result.confidence),
                method=DetectionMethod.BERT,
                category=IntentCategory.UNKNOWN,
                need_confirm=False,
                alternatives=[],
                raw_match=text,
                session_id=session_id,
            )
        except Exception as exc:
            logger.error(f"BERT prediction failed: {exc}")
            return None

    def predict_top_k(
        self,
        text: str,
        k: int = 3,
        session_id: str | None = None,
    ) -> list[IntentResult]:
        self._ensure_initialized()
        if self._classifier is None or not self._classifier.is_loaded():
            return []

        try:
            top_k_results = self._classifier.get_top_k_intents(text, k=k)
        except Exception as exc:
            logger.error(f"BERT top-k prediction failed: {exc}")
            return []

        results: list[IntentResult] = []
        for intent_name, confidence in top_k_results:
            results.append(
                IntentResult(
                    detected=True,
                    intent_type=intent_name,
                    action=intent_name,
                    params={},
                    description=f"BERT classifier: {intent_name}",
                    confidence=confidence,
                    confidence_level=ConfidenceLevel.from_score(confidence),
                    method=DetectionMethod.BERT,
                    category=IntentCategory.UNKNOWN,
                    need_confirm=False,
                    alternatives=[],
                    raw_match=text,
                    session_id=session_id,
                )
            )
        return results


def get_bert_classifier_adapter() -> BERTClassifierAdapter:
    global _bert_classifier_instance
    if _bert_classifier_instance is None:
        _bert_classifier_instance = BERTClassifierAdapter()
    return _bert_classifier_instance


bert_classifier = BERTClassifierAdapter()
