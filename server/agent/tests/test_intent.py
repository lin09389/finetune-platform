"""
意图检测模块全面测试套件
测试范围:
1. 基础意图检测
2. 置信度评估
3. 语义匹配
4. 上下文感知
5. 意图消歧
6. 性能指标
7. 边界条件和异常处理
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List
import time

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.intent import IntentDetector, IntentResult
from agent.intent.data import (
    INTENT_TRAINING_DATA, 
    IntentSample, 
    get_intent_samples,
    get_keywords_weight,
    get_params_extractors,
    get_all_intent_names
)
from agent.intent.confidence import (
    ConfidenceLevel,
    ConfidenceResult,
    ConfidenceEvaluator
)
from agent.intent.semantic_matcher import SemanticMatcher, FuzzyMatcher
from agent.intent.context_aware import ContextManager, ContextAwareDetector
from agent.intent.disambiguator import IntentDisambiguator
from agent.intent.metrics import IntentMetrics, MetricsAggregator


class TestIntentData:
    """测试训练数据模块"""

    def test_intent_data_structure(self):
        """测试意图数据结构完整性"""
        assert isinstance(INTENT_TRAINING_DATA, dict)
        assert len(INTENT_TRAINING_DATA) > 0
        
        required_intents = [
            'file_create', 'file_read', 'file_write', 
            'file_delete', 'file_list', 'app_open', 'url_open'
        ]
        
        for intent in required_intents:
            assert intent in INTENT_TRAINING_DATA, f"缺少意图类型: {intent}"
            
    def test_intent_data_content(self):
        """测试意图数据内容有效性"""
        for intent_type, data in INTENT_TRAINING_DATA.items():
            assert 'samples' in data, f"{intent_type} 缺少 samples"
            assert 'keywords_weight' in data, f"{intent_type} 缺少 keywords_weight"
            assert 'params_extractors' in data, f"{intent_type} 缺少 params_extractors"
            
            assert len(data['samples']) > 0, f"{intent_type} samples 为空"
            assert isinstance(data['keywords_weight'], dict)
            
    def test_get_intent_samples(self):
        """测试获取意图样本"""
        samples = get_intent_samples('file_create')
        assert isinstance(samples, list)
        assert len(samples) > 0
        assert all(isinstance(s, IntentSample) for s in samples)
        
    def test_get_all_intent_names(self):
        """测试获取所有意图名称"""
        names = get_all_intent_names()
        assert isinstance(names, list)
        assert len(names) > 0
        
    def test_get_params_extractors(self):
        """测试参数提取器获取"""
        extractors = get_params_extractors('file_create')
        assert isinstance(extractors, dict)


class TestConfidenceEvaluator:
    """测试置信度评估模块"""

    def setup_method(self):
        self.evaluator = ConfidenceEvaluator()

    def test_evaluate_high_confidence(self):
        """测试高置信度评估"""
        result = self.evaluator.evaluate(
            intent_name='file_create',
            params={'file_path': '/test.txt'},
            message='创建一个新文件 /test.txt',
            keywords=['创建', '文件'],
            pattern=r"创建\s*(\S+)\s*文件"
        )
        
        assert isinstance(result, ConfidenceResult)
        assert 0 <= result.score <= 1
        assert len(result.factors) > 0

    def test_evaluate_low_confidence(self):
        """测试低置信度评估"""
        result = self.evaluator.evaluate(
            intent_name='file_create',
            message='随便说点什么'
        )
        
        assert result.level == ConfidenceLevel.LOW
        assert result.score < 0.7

    def test_confidence_factors(self):
        """测试置信度因素计算"""
        result = self.evaluator.evaluate(
            intent_name='file_read',
            params={'file_path': '/data.json'},
            message='读取 /data.json 文件内容',
            keywords=['读取', '文件']
        )
        
        assert 'match_coverage' in result.factors
        assert 'keyword_weight' in result.factors
        assert 'param_completeness' in result.factors

    def test_confidence_level_thresholds(self):
        """测试置信度级别阈值"""
        assert ConfidenceLevel.HIGH.value == "high"
        assert ConfidenceLevel.MEDIUM.value == "medium"
        assert ConfidenceLevel.LOW.value == "low"


class TestSemanticMatcher:
    """测试语义匹配模块"""

    def test_fuzzy_matcher_basic(self):
        """测试模糊匹配器基础功能"""
        matcher = FuzzyMatcher()
        
        result = matcher.fuzzy_match('创建一个新文件')
        
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(r, tuple) and len(r) == 2 for r in result)

    def test_fuzzy_matcher_synonyms(self):
        """测试同义词匹配"""
        matcher = FuzzyMatcher()
        
        result = matcher.fuzzy_match('删除这个文档')
        
        assert len(result) > 0
        assert any('file_delete' in r[0] for r in result)

    def test_semantic_matcher_similarity(self):
        """测试语义相似度计算"""
        matcher = SemanticMatcher(use_embedding=False)
        
        similarity = matcher.compute_similarity('创建新文件', '新建一个文档')
        
        assert isinstance(similarity, float)
        assert 0 <= similarity <= 1


class TestContextAwareDetector:
    """测试上下文感知检测"""

    def setup_method(self):
        self.context_manager = ContextManager()
        self.detector = ContextAwareDetector(self.context_manager)

    def test_context_manager_session(self):
        """测试会话管理"""
        session_id = "test_session_001"
        
        ctx = self.context_manager.get_or_create_session(session_id)
        
        assert ctx is not None
        assert ctx.session_id == session_id

    def test_intent_history_tracking(self):
        """测试意图历史追踪"""
        session_id = "test_session_002"
        
        self.context_manager.add_message(session_id, "user", "创建文件", intent="file_create")
        self.context_manager.add_message(session_id, "user", "写入内容", intent="file_write")
        
        ctx = self.context_manager.get_or_create_session(session_id)
        
        assert len(ctx.recent_intents) == 2
        assert ctx.recent_intents[0] == "file_create"
        assert ctx.recent_intents[1] == "file_write"

    def test_context_enhanced_detection(self):
        """测试上下文增强检测"""
        session_id = "test_session_003"
        
        self.context_manager.add_message(session_id, "user", "创建文件", intent="file_create")
        
        intent, params, boost = self.detector.detect_with_context(
            message="写入一些内容",
            session_id=session_id,
            base_intent="file_write",
            base_params={}
        )
        
        assert intent is not None
        assert isinstance(boost, float)


class TestIntentDisambiguator:
    """测试意图消歧模块"""

    def setup_method(self):
        self.disambiguator = IntentDisambiguator()

    def test_disambiguate_similar_intents(self):
        """测试相似意图消歧"""
        candidates = [
            ('file_read', 0.7, {}),
            ('file_write', 0.65, {})
        ]
        
        result = self.disambiguator.disambiguate(
            message='打开文件看看内容',
            candidates=candidates
        )
        
        assert result is not None
        assert result.resolved_intent in ['file_read', 'file_write']

    def test_distinguishing_keywords(self):
        """测试区分关键词"""
        result = self.disambiguator.disambiguate(
            message='列出这个目录的文件',
            candidates=[
                ('file_read', 0.5, {}),
                ('file_list', 0.5, {})
            ]
        )
        
        assert result.resolved_intent == 'file_list'

    def test_no_disambiguation_needed(self):
        """测试无需消歧情况"""
        candidates = [
            ('file_create', 0.9, {}),
            ('file_read', 0.3, {})
        ]
        
        result = self.disambiguator.disambiguate(
            message='创建新文件',
            candidates=candidates
        )
        
        assert result.resolved_intent == 'file_create'


class TestIntentMetrics:
    """测试性能指标模块"""

    def setup_method(self):
        self.metrics = IntentMetrics()

    def test_record_prediction(self):
        """测试预测记录"""
        self.metrics.record('file_create', 'file_create', confidence=0.9)
        self.metrics.record('file_create', 'file_read', confidence=0.7)
        self.metrics.record('file_read', 'file_read', confidence=0.8)
        
        assert self.metrics.total_predictions == 3
        assert self.metrics.correct_predictions == 2

    def test_precision_calculation(self):
        """测试精确率计算"""
        self.metrics.record('file_create', 'file_create')
        self.metrics.record('file_create', 'file_create')
        self.metrics.record('file_create', 'file_read')
        
        precision = self.metrics.precision('file_create')
        
        assert 0 <= precision <= 1

    def test_recall_calculation(self):
        """测试召回率计算"""
        self.metrics.record('file_create', 'file_create')
        self.metrics.record('file_read', 'file_create')
        self.metrics.record('file_write', 'file_write')
        
        recall = self.metrics.recall('file_create')
        
        assert 0 <= recall <= 1

    def test_f1_score(self):
        """测试F1分数计算"""
        self.metrics.record('file_create', 'file_create')
        self.metrics.record('file_create', 'file_create')
        self.metrics.record('file_create', 'file_read')
        self.metrics.record('file_read', 'file_create')
        
        f1 = self.metrics.f1_score('file_create')
        
        assert 0 <= f1 <= 1

    def test_accuracy(self):
        """测试准确率计算"""
        self.metrics.record('file_create', 'file_create')
        self.metrics.record('file_read', 'file_read')
        self.metrics.record('file_write', 'file_write')
        self.metrics.record('file_delete', 'file_read')
        
        accuracy = self.metrics.accuracy()
        
        assert accuracy == 0.75

    def test_metrics_report(self):
        """测试指标报告生成"""
        self.metrics.record('file_create', 'file_create')
        self.metrics.record('file_read', 'file_read')
        
        report = self.metrics.get_report()
        
        assert 'summary' in report
        assert 'accuracy' in report['summary']
        assert 'per_intent_metrics' in report


class TestMetricsAggregator:
    """测试指标聚合器"""

    def setup_method(self):
        self.aggregator = MetricsAggregator()

    def test_session_aggregation(self):
        """测试会话指标聚合"""
        self.aggregator.record('file_create', 'file_create', session_id='session1')
        self.aggregator.record('file_read', 'file_read', session_id='session1')
        
        self.aggregator.record('file_create', 'file_read', session_id='session2')
        self.aggregator.record('file_write', 'file_write', session_id='session2')
        
        global_report = self.aggregator.get_global_report()
        
        assert global_report['summary']['total_predictions'] == 4


class TestIntentDetector:
    """测试意图检测器主模块"""

    def setup_method(self):
        self.detector = IntentDetector(use_semantic=False)

    def test_detect_file_create(self):
        """测试文件创建意图检测"""
        result = self.detector.detect('创建一个新文件 /project/main.py')
        
        assert isinstance(result, IntentResult)
        assert result.action.value == 'file_create'
        assert result.confidence > 0.5

    def test_detect_file_read(self):
        """测试文件读取意图检测"""
        result = self.detector.detect('读取 /data/config.json 的内容')
        
        assert result.action.value == 'file_read'
        assert result.confidence > 0.5

    def test_detect_file_write(self):
        """测试文件写入意图检测"""
        result = self.detector.detect('把"Hello World"写入到/test.txt 文件')
        
        assert result.action.value == 'file_write'

    def test_detect_file_delete(self):
        """测试文件删除意图检测"""
        result = self.detector.detect('删除 /tmp/cache.tmp 文件')
        
        assert result.action.value == 'file_delete'
        assert 'file_path' in result.params

    def test_detect_file_list(self):
        """测试文件列表意图检测"""
        result = self.detector.detect('列出 /home/user 目录下的所有文件')
        
        assert result.action.value == 'file_list'

    def test_detect_app_open(self):
        """测试应用打开意图检测"""
        result = self.detector.detect('打开计算器')
        
        assert result.action.value == 'app_open'
        assert 'app_name' in result.params

    def test_detect_url_open(self):
        """测试URL打开意图检测"""
        result = self.detector.detect('打开网页 https://github.com')
        
        assert result.action.value == 'url_open'
        assert 'url' in result.params

    def test_detect_with_context(self):
        """测试带上下文的意图检测"""
        session_id = "context_test_session"
        
        result1 = self.detector.detect('创建文件 /test.txt', session_id=session_id)
        result2 = self.detector.detect('写入一些内容', session_id=session_id)
        
        assert result1.action.value == 'file_create'
        assert result2 is not None

    def test_detect_alternatives(self):
        """测试备选意图"""
        result = self.detector.detect('处理这个文件')
        
        assert hasattr(result, 'alternatives')
        assert isinstance(result.alternatives, list)

    def test_detect_confidence_level(self):
        """测试置信度级别"""
        result = self.detector.detect('创建新文件/test.py')
        
        assert hasattr(result, 'confidence_level')
        assert result.confidence_level in ['high', 'medium', 'low']

    def test_record_feedback(self):
        """测试反馈记录"""
        from agent.agent_config import ActionType
        session_id = "feedback_test"
        self.detector.detect('创建文件', session_id=session_id)
        
        self.detector.record_feedback(
            session_id=session_id,
            predicted_action=ActionType.FILE_CREATE,
            is_correct=True
        )
        
        report = self.detector.get_metrics_report()
        assert 'summary' in report

    def test_get_metrics_report(self):
        """测试获取指标报告"""
        report = self.detector.get_metrics_report()
        
        assert isinstance(report, dict)


class TestIntentDetectorEdgeCases:
    """测试边界条件和异常情况"""

    def setup_method(self):
        self.detector = IntentDetector(use_semantic=False)

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
        assert result.action.value == 'file_create'

    def test_chinese_english_mixed(self):
        """测试中英混合"""
        result = self.detector.detect('Create 一个new file 叫做 test.py')
        
        assert result is not None

    def test_ambiguous_intent(self):
        """测试模糊意图"""
        result = self.detector.detect('处理一下这个')
        
        assert result is not None
        assert hasattr(result, 'alternatives')

    def test_multiple_intents(self):
        """测试多意图消息"""
        result = self.detector.detect('创建文件并写入内容')
        
        assert result is not None

    def test_unknown_intent(self):
        """测试未知意图"""
        result = self.detector.detect('今天天气怎么样')
        
        assert result is not None


class TestIntentDetectorPerformance:
    """测试性能"""

    def setup_method(self):
        self.detector = IntentDetector(use_semantic=False)

    def test_detection_speed(self):
        """测试检测速度"""
        messages = [
            '创建文件 /test1.txt',
            '读取 /data.json',
            '删除临时文件',
            '打开浏览器',
            '列出目录内容'
        ]
        
        start_time = time.time()
        
        for msg in messages:
            self.detector.detect(msg)
        
        elapsed = time.time() - start_time
        
        assert elapsed < 1.0

    def test_batch_detection(self):
        """测试批量检测"""
        messages = [f'创建文件 /test{i}.txt' for i in range(100)]
        
        start_time = time.time()
        
        results = [self.detector.detect(msg) for msg in messages]
        
        elapsed = time.time() - start_time
        
        assert len(results) == 100
        assert elapsed < 5.0


class TestIntegration:
    """集成测试"""

    def test_full_detection_pipeline(self):
        """测试完整检测流水线"""
        detector = IntentDetector(use_semantic=False)
        
        test_cases = [
            ('创建新文件/app/main.py', 'file_create'),
            ('读取配置文件 /etc/config.yaml', 'file_read'),
            ('写入数据到output.json', 'file_write'),
            ('删除旧的日志文件', 'file_delete'),
            ('列出当前目录', 'file_list'),
            ('打开记事本', 'app_open'),
            ('访问 https://google.com', 'url_open'),
        ]
        
        correct = 0
        total = len(test_cases)
        
        for message, expected_intent in test_cases:
            result = detector.detect(message)
            if result.detected and result.action.value == expected_intent:
                correct += 1
        
        accuracy = correct / total
        assert accuracy >= 0.6

    def test_session_context_flow(self):
        """测试会话上下文流程"""
        detector = IntentDetector(use_semantic=False)
        session_id = "integration_session"
        
        result1 = detector.detect('创建文件 /project/app.py', session_id)
        assert result1.action.value == 'file_create'
        
        result2 = detector.detect('写入代码', session_id)
        assert result2 is not None
        
        result3 = detector.detect('保存', session_id)
        assert result3 is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
