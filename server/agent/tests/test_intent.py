"""
意图检测模块全面测试套件
测试范围:
1. 基础意图检测
2. 置信度评估
3. 语义匹配
4. 上下文感知
5. 性能指标
6. 边界条件和异常处理
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.intent import (
    ConfidenceLevel,
    DetectionMethod,
    IntentDetector,
    IntentResult,
)
from agent.intent.core.confidence import (
    ConfidenceCalculator,
    ConfidenceFactors,
)
from agent.intent.core.context import (
    ContextManager,
)
from agent.intent.core.param_extractor import (
    ParamExtractor,
)
from agent.intent.core.patterns import (
    INTENT_PATTERNS,
    RULE_PATTERNS,
    get_all_patterns,
    get_intent_definition,
)
from agent.intent.handlers.metrics import MetricsHandler


class TestIntentPatterns:
    """测试意图模式模块"""

    def test_intent_patterns_structure(self):
        """测试意图模式结构完整性"""
        assert isinstance(INTENT_PATTERNS, dict)
        assert len(INTENT_PATTERNS) > 0

        required_intents = [
            'file_create', 'file_read', 'file_write',
            'file_delete', 'file_list', 'app_open', 'url_open'
        ]

        for intent in required_intents:
            assert intent in INTENT_PATTERNS, f"缺少意图类型: {intent}"

    def test_rule_patterns_structure(self):
        """测试规则模式结构"""
        assert isinstance(RULE_PATTERNS, list)
        assert len(RULE_PATTERNS) > 0

        for rule in RULE_PATTERNS:
            assert hasattr(rule, 'pattern')
            assert hasattr(rule, 'action')
            assert hasattr(rule, 'category')

    def test_get_intent_definition(self):
        """测试获取意图定义"""
        definition = get_intent_definition('file_create')
        assert definition is not None
        assert definition.intent_type == 'file_create'

    def test_get_all_patterns(self):
        """测试获取所有模式"""
        patterns = get_all_patterns()
        assert isinstance(patterns, list)
        assert len(patterns) > 0


class TestConfidenceCalculator:
    """测试置信度计算模块"""

    def setup_method(self):
        self.calculator = ConfidenceCalculator()

    def test_calculate_rule_confidence(self):
        """测试规则置信度计算"""
        factors = ConfidenceFactors(
            rule_match=1.0,
            keyword_match=0.8,
            param_completeness=1.0,
        )

        confidence = self.calculator.calculate(
            method=DetectionMethod.RULE,
            factors=factors
        )

        assert 0 <= confidence <= 1
        assert confidence > 0.5

    def test_get_level(self):
        """测试置信度级别获取"""
        assert self.calculator.get_level(0.9) == ConfidenceLevel.HIGH
        assert self.calculator.get_level(0.7) == ConfidenceLevel.MEDIUM
        assert self.calculator.get_level(0.5) == ConfidenceLevel.LOW
        assert self.calculator.get_level(0.3) == ConfidenceLevel.UNKNOWN

    def test_param_completeness(self):
        """测试参数完整性计算"""
        required = ['file_path', 'content']
        extracted = {'file_path': '/test.txt'}

        completeness = self.calculator.calculate_param_completeness(required, extracted)

        assert completeness == 0.5


class TestParamExtractor:
    """测试参数提取模块"""

    def setup_method(self):
        self.extractor = ParamExtractor()

    def test_extract_path(self):
        """测试路径提取"""
        path = self.extractor.extract_path('创建文件 test.py')
        assert path == 'test.py'

    def test_extract_url(self):
        """测试URL提取"""
        url = self.extractor.extract_url('打开 https://example.com')
        assert url == 'https://example.com'

    def test_extract_app_name(self):
        """测试应用名提取"""
        app = self.extractor.extract_app_name('打开 VS Code')
        assert app == 'vscode'

    def test_extract_coordinate(self):
        """测试坐标提取"""
        coord = self.extractor.extract_coordinate('点击 100,200')
        assert coord == (100, 200)

    def test_extract_all(self):
        """测试全部提取"""
        params = self.extractor.extract_all('创建文件 /project/main.py')
        assert 'file_path' in params


class TestContextManager:
    """测试上下文管理模块"""

    def setup_method(self):
        self.manager = ContextManager()

    def test_get_or_create_session(self):
        """测试会话创建"""
        session_id = "test_session_001"

        ctx = self.manager.get_or_create(session_id)

        assert ctx is not None
        assert ctx.session_id == session_id

    def test_add_message(self):
        """测试消息添加"""
        session_id = "test_session_002"

        self.manager.add_message(session_id, "user", "创建文件", intent="file_create")
        self.manager.add_message(session_id, "user", "写入内容", intent="file_write")

        ctx = self.manager.get(session_id)

        assert ctx is not None
        assert len(ctx.recent_intents) == 2
        assert ctx.recent_intents[0] == "file_create"
        assert ctx.recent_intents[1] == "file_write"

    def test_resolve_reference(self):
        """测试引用解析"""
        session_id = "test_session_003"

        ctx = self.manager.get_or_create(session_id)
        ctx.mentioned_entities["file_path"] = ["/test.txt"]

        resolved = self.manager.resolve_reference(session_id, "它")
        assert resolved == "/test.txt"


class TestMetricsHandler:
    """测试性能指标模块"""

    def setup_method(self):
        self.metrics = MetricsHandler()

    def test_record_success(self):
        """测试成功记录"""
        self.metrics.record_success(
            method=DetectionMethod.RULE,
            intent_type='file_create',
            confidence=0.9,
            response_time_ms=10.0
        )

        metrics = self.metrics.get_metrics()
        assert metrics['total_requests'] == 1
        assert metrics['successful_detections'] == 1

    def test_record_failure(self):
        """测试失败记录"""
        self.metrics.record_failure(response_time_ms=5.0)

        metrics = self.metrics.get_metrics()
        assert metrics['total_requests'] == 1
        assert metrics['failed_detections'] == 1

    def test_get_success_rate(self):
        """测试成功率计算"""
        self.metrics.record_success(DetectionMethod.RULE, 'file_create', 0.9, 10.0)
        self.metrics.record_success(DetectionMethod.RULE, 'file_read', 0.8, 15.0)
        self.metrics.record_failure(5.0)

        rate = self.metrics.get_success_rate()
        assert rate == 2/3


class TestIntentDetector:
    """测试意图检测器主模块"""

    def setup_method(self):
        from agent.intent.detector import DetectorConfig
        config = DetectorConfig(
            use_rule_matcher=True,
            use_semantic_matcher=False,
            use_bert_classifier=False,
            use_llm_fallback=False,
            use_context=True,
        )
        self.detector = IntentDetector(config)

    def test_detect_file_create(self):
        """测试文件创建意图检测"""
        result = self.detector.detect('创建一个新文件 /project/main.py')

        assert isinstance(result, IntentResult)
        assert result.intent_type == 'file_create'
        assert result.confidence > 0.5

    def test_detect_file_read(self):
        """测试文件读取意图检测"""
        result = self.detector.detect('读取 /data/config.json 的内容')

        assert result.intent_type == 'file_read'
        assert result.confidence > 0.5

    def test_detect_file_write(self):
        """测试文件写入意图检测 - 使用匹配规则模式的输入"""
        result = self.detector.detect('向 /test.txt 中写入 "Hello World"')

        assert result.intent_type == 'file_write'

    def test_detect_file_delete(self):
        """测试文件删除意图检测"""
        result = self.detector.detect('删除 /tmp/cache.tmp 文件')

        assert result.intent_type == 'file_delete'
        assert 'file_path' in result.params

    def test_detect_file_list(self):
        """测试文件列表意图检测"""
        result = self.detector.detect('列出当前目录')

        assert result.intent_type == 'file_list'

    def test_detect_app_open(self):
        """测试应用打开意图检测"""
        result = self.detector.detect('打开 VS Code')

        assert result.intent_type == 'app_open'
        assert 'app_name' in result.params

    def test_detect_url_open(self):
        """测试URL打开意图检测"""
        result = self.detector.detect('打开网页 https://github.com')

        assert result.intent_type == 'url_open'
        assert 'url' in result.params

    def test_detect_screenshot(self):
        """测试截图意图检测"""
        result = self.detector.detect('截图')

        assert result.intent_type == 'screenshot'

    def test_detect_with_context(self):
        """测试带上下文的意图检测"""
        session_id = "context_test_session"

        result1 = self.detector.detect('创建文件 /test.txt', session_id=session_id)
        result2 = self.detector.detect('写入一些内容', session_id=session_id)

        assert result1.intent_type == 'file_create'
        assert result2 is not None

    def test_detect_confidence_level(self):
        """测试置信度级别"""
        result = self.detector.detect('创建新文件 test.py')

        assert hasattr(result, 'confidence_level')
        assert result.confidence_level in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW]

    def test_get_metrics(self):
        """测试获取指标"""
        self.detector.detect('创建文件 test.py')

        metrics = self.detector.get_metrics()
        assert isinstance(metrics, dict)
        assert 'total_requests' in metrics


class TestIntentDetectorEdgeCases:
    """测试边界条件和异常情况"""

    def setup_method(self):
        from agent.intent.detector import DetectorConfig
        config = DetectorConfig(
            use_rule_matcher=True,
            use_semantic_matcher=False,
            use_bert_classifier=False,
            use_llm_fallback=False,
        )
        self.detector = IntentDetector(config)

    def test_empty_message(self):
        """测试空消息"""
        result = self.detector.detect('')

        assert result is not None
        assert result.detected == False

    def test_whitespace_message(self):
        """测试纯空白消息"""
        result = self.detector.detect('   \t\n   ')

        assert result is not None

    def test_very_long_message(self):
        """测试超长消息"""
        long_message = '创建文件 ' + 'a' * 10000

        result = self.detector.detect(long_message)

        assert result is not None

    def test_special_characters(self):
        """测试特殊字符"""
        result = self.detector.detect('创建文件 /path/with/special@#$%^&.txt')

        assert result is not None

    def test_chinese_english_mixed(self):
        """测试中英混合"""
        result = self.detector.detect('Create 一个new file 叫做 test.py')

        assert result is not None

    def test_unknown_intent(self):
        """测试未知意图"""
        result = self.detector.detect('今天天气怎么样')

        assert result is not None


class TestIntentDetectorPerformance:
    """测试性能"""

    def setup_method(self):
        from agent.intent.detector import DetectorConfig
        config = DetectorConfig(
            use_rule_matcher=True,
            use_semantic_matcher=False,
            use_bert_classifier=False,
            use_llm_fallback=False,
        )
        self.detector = IntentDetector(config)

    def test_detection_speed(self):
        """测试检测速度"""
        messages = [
            '创建文件 /test1.txt',
            '读取 /data.json',
            '删除临时文件',
            '列出当前目录',
            '截图'
        ]

        start_time = time.time()

        for msg in messages:
            self.detector.detect(msg)

        elapsed = time.time() - start_time

        assert elapsed < 2.0

    def test_batch_detection(self):
        """测试批量检测"""
        messages = [f'创建文件 /test{i}.txt' for i in range(50)]

        start_time = time.time()

        results = [self.detector.detect(msg) for msg in messages]

        elapsed = time.time() - start_time

        assert len(results) == 50
        assert elapsed < 10.0


class TestIntegration:
    """集成测试"""

    def test_full_detection_pipeline(self):
        """测试完整检测流水线"""
        from agent.intent.detector import DetectorConfig
        config = DetectorConfig(
            use_rule_matcher=True,
            use_semantic_matcher=False,
            use_bert_classifier=False,
            use_llm_fallback=False,
        )
        detector = IntentDetector(config)

        test_cases = [
            ('创建新文件 app/main.py', 'file_create'),
            ('读取配置文件 config.json', 'file_read'),
            ('删除旧的日志文件', 'file_delete'),
            ('列出当前目录', 'file_list'),
            ('打开 VS Code', 'app_open'),
            ('访问 https://google.com', 'url_open'),
            ('截图', 'screenshot'),
        ]

        correct = 0
        total = len(test_cases)

        for message, expected_intent in test_cases:
            result = detector.detect(message)
            if result.detected and result.intent_type == expected_intent:
                correct += 1

        accuracy = correct / total
        assert accuracy >= 0.5

    def test_session_context_flow(self):
        """测试会话上下文流程"""
        from agent.intent.detector import DetectorConfig
        config = DetectorConfig(
            use_rule_matcher=True,
            use_semantic_matcher=False,
            use_bert_classifier=False,
            use_llm_fallback=False,
            use_context=True,
        )
        detector = IntentDetector(config)
        session_id = "integration_session"

        result1 = detector.detect('创建文件 /project/app.py', session_id)
        assert result1.intent_type == 'file_create'

        result2 = detector.detect('写入代码', session_id)
        assert result2 is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
