"""
意图检测器 - 统一入口

整合所有检测方法和处理器，提供统一的意图检测接口
"""
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from .core.context import context_manager
from .handlers.clarification import clarification_handler
from .handlers.error_handler import error_handler
from .handlers.metrics import metrics_handler
from .methods.bert_classifier import bert_classifier
from .methods.llm_detector import llm_detector
from .methods.llm_intent_understanding import llm_intent_understanding
from .methods.rule_matcher import rule_matcher
from .methods.semantic_matcher import semantic_matcher
from .models import (
    ConfidenceLevel,
    DetectionMethod,
    DetectionMetrics,
    IntentCategory,
    IntentResult,
    MultiIntentResult,
)

logger = logging.getLogger(__name__)

try:
    from agent.agent_config import ActionType as LegacyActionType
except Exception:  # pragma: no cover
    LegacyActionType = None


@dataclass
class DetectorConfig:
    use_rule_matcher: bool = True
    use_semantic_matcher: bool = True
    use_bert_classifier: bool = True
    use_llm_fallback: bool = True
    use_context: bool = True
    parallel_detection: bool = True
    confidence_threshold: float = 0.45
    high_confidence_threshold: float = 0.85


class IntentDetector:
    """统一意图检测器"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, config: DetectorConfig | None = None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, config: DetectorConfig | None = None):
        if self._initialized:
            return

        self._config = config or DetectorConfig()
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._metrics = DetectionMetrics()
        self._initialized = True

        logger.info("意图检测器初始化完成")

    @classmethod
    def get_instance(cls) -> "IntentDetector":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def detect(
        self,
        text: str,
        session_id: str | None = None,
        context: dict[str, Any] | None = None
    ) -> IntentResult:
        # 定期检查规则热更新
        from .core.patterns import check_reload
        if check_reload():
            logger.info("检测到意图规则文件变动，正在重新加载...")
            # 在真实的动态加载系统中，这里需要刷新 rule_matcher 的 patterns
            pass

        start_time = time.time()

        try:
            text = text.strip()
            if not text:
                return self._create_empty_result(session_id)

            fast_result = self._detect_fast_action(text, session_id)
            if fast_result is not None:
                self._record_success(fast_result, start_time)
                return fast_result

            if self._config.use_context and session_id:
                self._update_context(session_id, "user", text)

            conversation_result = self._detect_conversation_intent(text, session_id)
            if conversation_result:
                self._record_success(conversation_result, start_time)
                if self._config.use_context and session_id:
                    self._update_context(session_id, "assistant", str(conversation_result.to_dict()), conversation_result.intent_type)
                return conversation_result

            results = self._run_detection_methods(text, session_id)

            if not results:
                if self._config.use_llm_fallback:
                    llm_results = llm_intent_understanding.understand(text, session_id)
                    if llm_results:
                        results.extend(llm_results)

            if not results:
                return self._create_unknown_result(text, session_id)

            best_result = self._select_best_result(results, text, session_id)
            self._coerce_action_enum(best_result)

            # 低置信度降级策略：如果置信度低于 0.6，触发二次确认或高级 LLM 校验
            if best_result.confidence < 0.6 and self._config.use_llm_fallback:
                logger.info(f"置信度过低 ({best_result.confidence})，正在尝试 LLM 降级校验")
                refined_results = llm_intent_understanding.understand(text, session_id)
                if refined_results and refined_results[0].confidence > best_result.confidence:
                    best_result = refined_results[0]

            if self._config.use_context and session_id:
                self._resolve_context_references(best_result, session_id)

            if clarification_handler.needs_clarification(best_result):
                best_result.clarification = clarification_handler.create_clarification(
                    best_result,
                    results[1:3] if len(results) > 1 else None
                )

            self._record_success(best_result, start_time)

            if self._config.use_context and session_id:
                self._update_context(session_id, "assistant", str(best_result.to_dict()), best_result.intent_type)

            return best_result

        except Exception as e:
            logger.error(f"意图检测失败: {e}")
            self._record_failure(start_time)
            return error_handler.create_error_result("detection_failed", text, session_id)

    def detect_multi(
        self,
        text: str,
        session_id: str | None = None,
        context: dict[str, Any] | None = None
    ) -> MultiIntentResult:
        """多意图检测入口"""
        if self._config.use_llm_fallback:
            # 对于 detect_multi，优先使用 LLM 理解其复杂结构
            llm_results = llm_intent_understanding.understand(text, session_id)
            if llm_results and len(llm_results) > 1:
                return MultiIntentResult(
                    detected=True,
                    intents=llm_results,
                    has_ambiguity=any(r.confidence < 0.65 for r in llm_results),
                    clarification_dialog=None,
                    chain=[]
                )

        # 否则回退到单意图检测逻辑
        result = self.detect(text, session_id, context)

        return MultiIntentResult(
            detected=result.detected,
            intents=[result],
            has_ambiguity=result.confidence < 0.65,
            clarification_dialog=result.clarification,
            chain=[]
        )

    def _detect_fast_action(self, text: str, session_id: str | None) -> IntentResult | None:
        compact = text.strip().lower().replace(" ", "")

        if any(token in compact for token in ["天气", "写一首诗", "写首诗"]):
            return self._create_unknown_result(text, session_id)

        fast_rules: list[tuple[tuple[str, ...], str, IntentCategory, str]] = [
            (("当前活动窗口",), "window_active", IntentCategory.CUA_OPERATION, "Get active window"),
            (("截图", "截屏", "屏幕照片", "屏幕截图"), "screenshot", IntentCategory.CUA_OPERATION, "Capture the screen"),
            (("鼠标在哪", "鼠标位置", "获取鼠标位置", "当前位置鼠标"), "mouse_position", IntentCategory.CUA_OPERATION, "Get current mouse position"),
            (("列出窗口", "所有窗口", "打开的窗口", "活动窗口", "显示窗口"), "window_list", IntentCategory.CUA_OPERATION, "List windows"),
            (("创建文件", "新建文件", "创建readme", "新建readme"), "file_create", IntentCategory.FILE_OPERATION, "Create a file"),
            (("读取", "查看", "打开readme"), "file_read", IntentCategory.FILE_OPERATION, "Read a file"),
            (("列出目录", "显示目录", "当前目录文件", "目录内容"), "file_list", IntentCategory.FILE_OPERATION, "List directory contents"),
        ]

        for keywords, action_name, category, description in fast_rules:
            if any(keyword in compact for keyword in keywords):
                return self._build_fast_result(action_name, category, description, text, session_id)

        if compact.startswith("创建") or compact.startswith("新建"):
            return self._build_fast_result("file_create", IntentCategory.FILE_OPERATION, "Create a file", text, session_id)
        if compact.startswith("读取") or compact.startswith("查看"):
            return self._build_fast_result("file_read", IntentCategory.FILE_OPERATION, "Read a file", text, session_id)

        return None

    def _build_fast_result(
        self,
        action_name: str,
        category: IntentCategory,
        description: str,
        text: str,
        session_id: str | None,
    ) -> IntentResult:
        params = self._extract_fast_params(action_name, text)
        result = IntentResult(
            detected=True,
            intent_type=action_name,
            action=action_name,
            params=params,
            description=description,
            confidence=0.98,
            confidence_level=ConfidenceLevel.HIGH,
            method=DetectionMethod.RULE,
            category=category,
            need_confirm=False,
            alternatives=[],
            raw_match=text,
            session_id=session_id,
        )
        self._coerce_action_enum(result)
        return result

    def _extract_fast_params(self, action_name: str, text: str) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if action_name not in {"file_create", "file_read", "file_delete", "file_write"}:
            return params

        match = re.search(r"([A-Za-z0-9_./\-]+\.[A-Za-z0-9_]+)", text)
        if match:
            params["file_path"] = match.group(1)
        return params

    def _coerce_action_enum(self, result: IntentResult) -> IntentResult:
        if not result or not getattr(result, "action", None) or LegacyActionType is None:
            return result

        action_value = result.action.value if hasattr(result.action, "value") else str(result.action)
        try:
            result.action = LegacyActionType(action_value)
        except Exception:
            result.action = action_value
        return result

    def _run_detection_methods(
        self,
        text: str,
        session_id: str | None
    ) -> list[IntentResult]:
        results = []

        if self._config.parallel_detection:
            futures = []

            if self._config.use_rule_matcher:
                futures.append(
                    self._executor.submit(rule_matcher.match, text, session_id)
                )

            if self._config.use_bert_classifier:
                futures.append(
                    self._executor.submit(bert_classifier.predict, text, session_id)
                )

            for future in futures:
                try:
                    result = future.result(timeout=5.0)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.warning(f"检测方法执行失败: {e}")

            if self._config.use_semantic_matcher:
                try:
                    semantic_results = semantic_matcher.match(text, session_id=session_id)
                    results.extend(semantic_results)
                except Exception as e:
                    logger.warning(f"语义匹配失败: {e}")
        else:
            if self._config.use_rule_matcher:
                result = rule_matcher.match(text, session_id)
                if result:
                    results.append(result)

            if self._config.use_bert_classifier:
                result = bert_classifier.predict(text, session_id)
                if result:
                    results.append(result)

            if self._config.use_semantic_matcher:
                semantic_results = semantic_matcher.match(text, session_id=session_id)
                results.extend(semantic_results)

        return results

    CONVERSATION_PATTERNS = [
        r'^(你好|您好|hi|hello|hey|嗨|哈喽|早上好|下午好|晚上好)[\s!！.。]*$',
        r'^(谢谢|感谢|多谢|thanks|thank\s*you)[\s!！.。]*$',
        r'^(再见|拜拜|bye|goodbye|下次见)[\s!！.。]*$',
        r'^(你是谁|你叫什么|你的名字|自我介绍)',
        r'^(你能做什么|你会什么|你的功能|你能帮我)',
        r'^(我想问|请问|问一下|请教)',
        r'^(好的|明白|收到|ok|okay|嗯|哦)[\s!！.。]*$',
        r'^(不是|不对|错|no)[\s!！.。]*$',
        r'^(怎么样|如何|什么情况|怎么了|什么事)[\?？]*$',
    ]

    def _detect_conversation_intent(self, text: str, session_id: str | None) -> IntentResult | None:
        """快速检测对话意图"""
        text_lower = text.lower().strip()

        for pattern in self.CONVERSATION_PATTERNS:
            if re.match(pattern, text_lower, re.IGNORECASE):
                return IntentResult(
                    detected=True,
                    intent_type="conversation",
                    action=None,
                    params={},
                    description="对话意图",
                    confidence=1.0,
                    confidence_level=ConfidenceLevel.HIGH,
                    method=DetectionMethod.RULE,
                    category=IntentCategory.CONVERSATION,
                    need_confirm=False,
                    alternatives=[],
                    raw_match=text,
                    session_id=session_id
                )

        return None

    def _select_best_result(
        self,
        results: list[IntentResult],
        text: str,
        session_id: str | None
    ) -> IntentResult:
        if not results:
            return self._create_unknown_result(text, session_id)

        if len(results) == 1:
            return results[0]

        method_weights = {
            DetectionMethod.RULE: 0.35,
            DetectionMethod.BERT: 0.30,
            DetectionMethod.SEMANTIC: 0.20,
            DetectionMethod.LLM: 0.15,
        }

        def score_result(r: IntentResult) -> float:
            method_weight = method_weights.get(r.method, 0.1)
            return r.confidence * method_weight

        sorted_results = sorted(results, key=score_result, reverse=True)
        best = sorted_results[0]

        best.alternatives = [
            (r.intent_type, r.confidence)
            for r in sorted_results[1:4]
            if r.intent_type != best.intent_type
        ]

        return best

    def _resolve_context_references(
        self,
        result: IntentResult,
        session_id: str
    ):
        for param_name, param_value in list(result.params.items()):
            if isinstance(param_value, str) and param_value in ["它", "这个", "那个", "继续", "刚才"]:
                resolved = context_manager.resolve_reference(session_id, param_value)
                if resolved:
                    result.params[param_name] = resolved

    def _update_context(
        self,
        session_id: str,
        role: str,
        content: str,
        intent: str | None = None
    ):
        context_manager.add_message(session_id, role, content, intent)

    def _record_success(self, result: IntentResult, start_time: float):
        elapsed_ms = (time.time() - start_time) * 1000
        metrics_handler.record_success(
            method=result.method,
            intent_type=result.intent_type,
            confidence=result.confidence,
            response_time_ms=elapsed_ms
        )

    def _record_failure(self, start_time: float):
        elapsed_ms = (time.time() - start_time) * 1000
        metrics_handler.record_failure(elapsed_ms)

    def _create_empty_result(self, session_id: str | None) -> IntentResult:
        return IntentResult(
            detected=False,
            intent_type="empty",
            action="",
            params={},
            description="输入为空",
            confidence=0.0,
            confidence_level=ConfidenceLevel.UNKNOWN,
            method=DetectionMethod.RULE,
            category=IntentCategory.UNKNOWN,
            need_confirm=False,
            alternatives=[],
            raw_match="",
            session_id=session_id
        )

    def _create_unknown_result(self, text: str, session_id: str | None) -> IntentResult:
        return IntentResult(
            detected=False,
            intent_type="unknown",
            action="",
            params={},
            description="无法识别意图",
            confidence=0.0,
            confidence_level=ConfidenceLevel.UNKNOWN,
            method=DetectionMethod.RULE,
            category=IntentCategory.UNKNOWN,
            need_confirm=False,
            alternatives=[],
            raw_match=text,
            session_id=session_id
        )

    def get_metrics(self) -> dict[str, Any]:
        return metrics_handler.get_metrics()

    def reset_metrics(self):
        metrics_handler.reset()

    def set_llm_client(self, client: Any):
        llm_detector.set_llm_client(client)
        llm_intent_understanding.set_llm_client(client)

    def warmup(self):
        logger.info("预热意图检测器...")

        if self._config.use_bert_classifier:
            bert_classifier._ensure_initialized()

        logger.info("意图检测器预热完成")


def create_detector(config: DetectorConfig | None = None) -> IntentDetector:
    return IntentDetector(config)


def get_detector() -> IntentDetector:
    return IntentDetector.get_instance()


detector = IntentDetector()
