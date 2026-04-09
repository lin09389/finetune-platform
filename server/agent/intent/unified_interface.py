from dataclasses import dataclass
from typing import Any

from agent.agent_config import ActionType

from .detector import get_detector


@dataclass
class LegacyIntentResult:
    detected: bool
    action: ActionType | None = None
    params: dict[str, Any] | None = None
    need_confirm: bool = False
    confidence: float = 0.0


class UnifiedDetectorAdapter:
    def __init__(self):
        self._detector = get_detector()

    def _heuristic_detect(self, text: str) -> LegacyIntentResult | None:
        raw = text.strip()
        lower = raw.lower()
        if any(keyword in raw for keyword in ["截图", "截屏", "截取屏幕"]) or "screenshot" in lower:
            return LegacyIntentResult(True, ActionType.SCREENSHOT, {}, False, 0.95)
        if any(keyword in raw for keyword in ["批量删除", "删除所有", "清理tmp", "清理临时"]) or "batch delete" in lower:
            return LegacyIntentResult(True, ActionType.FILE_BATCH_DELETE, {}, True, 0.95)
        if any(keyword in raw for keyword in ["删除", "移除"]) or "delete" in lower:
            return LegacyIntentResult(True, ActionType.FILE_DELETE, {}, True, 0.92)
        if any(keyword in raw for keyword in ["改成", "改为", "修改", "写入"]) or "write" in lower:
            return LegacyIntentResult(True, ActionType.FILE_WRITE, {}, False, 0.9)
        if any(keyword in raw for keyword in ["创建", "新建", "生成"]) or "create" in lower:
            return LegacyIntentResult(True, ActionType.FILE_CREATE, {}, False, 0.88)
        return None

    def detect(self, text: str, session_id: str | None = None, context: dict[str, Any] | None = None):
        heuristic = self._heuristic_detect(text)
        if heuristic is not None:
            return heuristic
        result = self._detector.detect(text, session_id=session_id, context=context)
        action = None
        if result.action:
            try:
                action = ActionType(result.action)
            except Exception:
                action = None
        return LegacyIntentResult(
            detected=bool(result.detected),
            action=action,
            params=result.params or {},
            need_confirm=bool(result.need_confirm),
            confidence=float(result.confidence or 0.0),
        )

    def detect_multi(self, text: str, session_id: str | None = None, context: dict[str, Any] | None = None):
        multi = self._detector.detect_multi(text, session_id=session_id, context=context)
        results = []
        for item in multi.intents:
            action = None
            if item.action:
                try:
                    action = ActionType(item.action)
                except Exception:
                    action = None
            results.append(LegacyIntentResult(bool(item.detected), action, item.params or {}, bool(item.need_confirm), float(item.confidence or 0.0)))
        if not results:
            heuristic = self._heuristic_detect(text)
            if heuristic is not None:
                results.append(heuristic)
        return results


_adapter: UnifiedDetectorAdapter | None = None


def get_unified_detector() -> UnifiedDetectorAdapter:
    global _adapter
    if _adapter is None:
        _adapter = UnifiedDetectorAdapter()
    return _adapter
