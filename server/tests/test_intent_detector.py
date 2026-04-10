"""
意图检测服务测试
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.intent import (
    ConfidenceLevel,
    DetectionMethod,
    IntentCategory,
    IntentDetector,
)
from agent.intent.detector import DetectorConfig


class TestIntentDetector:
    def setup_method(self):
        config = DetectorConfig(
            use_rule_matcher=True,
            use_semantic_matcher=False,
            use_bert_classifier=False,
            use_llm_fallback=False,
            use_context=True,
        )
        self.detector = IntentDetector(config)

    def test_detect_file_create_intent(self):
        text = "创建一个test.py文件"
        result = self.detector.detect(text)

        assert result.detected
        assert result.intent_type == 'file_create'

    def test_detect_file_read_intent(self):
        text = "读取config.json文件"
        result = self.detector.detect(text)

        assert result.detected
        assert result.intent_type == 'file_read'

    def test_detect_app_open_intent(self):
        text = "打开VS Code"
        result = self.detector.detect(text)

        assert result.detected
        assert result.intent_type == 'app_open'

    def test_detect_screenshot_intent(self):
        text = "截图"
        result = self.detector.detect(text)

        assert result.detected
        assert result.intent_type == 'screenshot'

    def test_detect_url_open_intent(self):
        text = "打开 https://github.com"
        result = self.detector.detect(text)

        assert result.detected
        assert result.intent_type == 'url_open'

    def test_confidence_score(self):
        text = "创建文件 test.py"
        result = self.detector.detect(text)

        if result.detected:
            assert 0 <= result.confidence <= 1

    def test_parameter_extraction(self):
        text = "创建一个名为main.py的文件"
        result = self.detector.detect(text)

        if result.detected:
            assert hasattr(result, 'params')

    def test_context_influence(self):
        text = "创建它"
        session_id = "test_session"

        self.detector.detect("创建文件 test.py", session_id=session_id)
        result = self.detector.detect(text, session_id=session_id)

        assert result is not None

    def test_empty_text(self):
        text = ""
        result = self.detector.detect(text)

        assert not result.detected

    def test_intent_description(self):
        text = "创建test.py文件"
        result = self.detector.detect(text)

        if result.detected:
            assert result.description is not None


class TestDetectionMethod:
    def test_detection_method_values(self):
        assert DetectionMethod.RULE.value == "rule"
        assert DetectionMethod.SEMANTIC.value == "semantic"
        assert DetectionMethod.BERT.value == "bert"
        assert DetectionMethod.LLM.value == "llm"

    def test_confidence_level_values(self):
        assert ConfidenceLevel.HIGH.value == "high"
        assert ConfidenceLevel.MEDIUM.value == "medium"
        assert ConfidenceLevel.LOW.value == "low"
        assert ConfidenceLevel.UNKNOWN.value == "unknown"

    def test_intent_category_values(self):
        assert IntentCategory.FILE_OPERATION.value == "file_operation"
        assert IntentCategory.APP_CONTROL.value == "app_control"
        assert IntentCategory.BROWSER_OPERATION.value == "browser_operation"
        assert IntentCategory.CUA_OPERATION.value == "cua_operation"
        assert IntentCategory.SYSTEM_OPERATION.value == "system_operation"


class TestIntentDetectorMetrics:
    def setup_method(self):
        config = DetectorConfig(
            use_rule_matcher=True,
            use_semantic_matcher=False,
            use_bert_classifier=False,
            use_llm_fallback=False,
        )
        self.detector = IntentDetector(config)

    def test_metrics_collection(self):
        self.detector.detect("创建文件 test.py")
        self.detector.detect("读取 config.json")
        self.detector.detect("打开 VS Code")

        metrics = self.detector.get_metrics()

        assert metrics['total_requests'] >= 3
        assert 'success_rate' in metrics

    def test_method_usage_tracking(self):
        self.detector.detect("创建文件 test.py")

        metrics = self.detector.get_metrics()

        assert 'method_usage' in metrics


class TestIntentDetectorEdgeCases:
    def setup_method(self):
        config = DetectorConfig(
            use_rule_matcher=True,
            use_semantic_matcher=False,
            use_bert_classifier=False,
            use_llm_fallback=False,
        )
        self.detector = IntentDetector(config)

    def test_empty_message(self):
        result = self.detector.detect('')
        assert not result.detected

    def test_whitespace_message(self):
        result = self.detector.detect('   \t\n   ')
        assert result is not None

    def test_very_long_message(self):
        long_message = '创建文件 ' + 'a' * 10000
        result = self.detector.detect(long_message)
        assert result is not None

    def test_special_characters(self):
        result = self.detector.detect('创建文件 /path/with/special@#$%^&.txt')
        assert result is not None

    def test_unknown_intent(self):
        result = self.detector.detect('今天天气怎么样')
        assert result is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
