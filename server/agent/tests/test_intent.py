"""
æå¾æ£æµæ¨¡åå¨é¢æµè¯å¥ä»?
æµè¯èå´:
1. åºç¡æå¾æ£æµ?2. ç½®ä¿¡åº¦è¯ä¼?3. è¯­ä¹å¹é
4. ä¸ä¸ææç?5. æå¾æ¶æ­§
6. æ§è½ææ 
7. è¾¹çæ¡ä»¶åå¼å¸¸å¤ç?"""

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
    """æµè¯è®­ç»æ°æ®æ¨¡å"""

    def test_intent_data_structure(self):
        """æµè¯æå¾æ°æ®ç»æå®æ´æ?""
        assert isinstance(INTENT_TRAINING_DATA, dict)
        assert len(INTENT_TRAINING_DATA) > 0
        
        required_intents = [
            'file_create', 'file_read', 'file_write', 
            'file_delete', 'file_list', 'app_open', 'url_open'
        ]
        
        for intent in required_intents:
            assert intent in INTENT_TRAINING_DATA, f"ç¼ºå°æå¾ç±»å: {intent}"
            
    def test_intent_data_content(self):
        """æµè¯æå¾æ°æ®åå®¹æææ?""
        for intent_type, data in INTENT_TRAINING_DATA.items():
            assert 'samples' in data, f"{intent_type} ç¼ºå° samples"
            assert 'keywords_weight' in data, f"{intent_type} ç¼ºå° keywords_weight"
            assert 'params_extractors' in data, f"{intent_type} ç¼ºå° params_extractors"
            
            assert len(data['samples']) > 0, f"{intent_type} samples ä¸ºç©º"
            assert isinstance(data['keywords_weight'], dict)
            
    def test_get_intent_samples(self):
        """æµè¯è·åæå¾æ ·æ¬"""
        samples = get_intent_samples('file_create')
        assert isinstance(samples, list)
        assert len(samples) > 0
        assert all(isinstance(s, IntentSample) for s in samples)
        
    def test_get_all_intent_names(self):
        """æµè¯è·åæææå¾åç§?""
        names = get_all_intent_names()
        assert isinstance(names, list)
        assert len(names) > 0
        
    def test_get_params_extractors(self):
        """æµè¯åæ°æåå¨è·å?""
        extractors = get_params_extractors('file_create')
        assert isinstance(extractors, dict)


class TestConfidenceEvaluator:
    """æµè¯ç½®ä¿¡åº¦è¯ä¼°æ¨¡å?""

    def setup_method(self):
        self.evaluator = ConfidenceEvaluator()

    def test_evaluate_high_confidence(self):
        """æµè¯é«ç½®ä¿¡åº¦è¯ä¼°"""
        result = self.evaluator.evaluate(
            intent_name='file_create',
            params={'file_path': '/test.txt'},
            message='åå»ºä¸ä¸ªæ°æä»¶ /test.txt',
            keywords=['åå»º', 'æä»¶'],
            pattern=r"åå»º\s*(\S+)\s*æä»¶"
        )
        
        assert isinstance(result, ConfidenceResult)
        assert 0 <= result.score <= 1
        assert len(result.factors) > 0

    def test_evaluate_low_confidence(self):
        """æµè¯ä½ç½®ä¿¡åº¦è¯ä¼°"""
        result = self.evaluator.evaluate(
            intent_name='file_create',
            message='éä¾¿è¯´ç¹ä»ä¹?
        )
        
        assert result.level == ConfidenceLevel.LOW
        assert result.score < 0.7

    def test_confidence_factors(self):
        """æµè¯ç½®ä¿¡åº¦å ç´ è®¡ç®?""
        result = self.evaluator.evaluate(
            intent_name='file_read',
            params={'file_path': '/data.json'},
            message='è¯»å /data.json æä»¶åå®¹',
            keywords=['è¯»å', 'æä»¶']
        )
        
        assert 'match_coverage' in result.factors
        assert 'keyword_weight' in result.factors
        assert 'param_completeness' in result.factors

    def test_confidence_level_thresholds(self):
        """æµè¯ç½®ä¿¡åº¦çº§å«éå?""
        assert ConfidenceLevel.HIGH.value == "high"
        assert ConfidenceLevel.MEDIUM.value == "medium"
        assert ConfidenceLevel.LOW.value == "low"


class TestSemanticMatcher:
    """æµè¯è¯­ä¹å¹éæ¨¡å"""

    def test_fuzzy_matcher_basic(self):
        """æµè¯æ¨¡ç³å¹éå¨åºç¡åè½"""
        matcher = FuzzyMatcher()
        
        result = matcher.fuzzy_match('åå»ºä¸ä¸ªæ°æä»¶')
        
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(r, tuple) and len(r) == 2 for r in result)

    def test_fuzzy_matcher_synonyms(self):
        """æµè¯åä¹è¯å¹é?""
        matcher = FuzzyMatcher()
        
        result = matcher.fuzzy_match('å é¤è¿ä¸ªææ¡£')
        
        assert len(result) > 0
        assert any('file_delete' in r[0] for r in result)

    def test_semantic_matcher_similarity(self):
        """æµè¯è¯­ä¹ç¸ä¼¼åº¦è®¡ç®?""
        matcher = SemanticMatcher(use_embedding=False)
        
        similarity = matcher.compute_similarity('åå»ºæ°æä»?, 'æ°å»ºä¸ä¸ªææ¡?)
        
        assert isinstance(similarity, float)
        assert 0 <= similarity <= 1


class TestContextAwareDetector:
    """æµè¯ä¸ä¸ææç¥æ£æµ?""

    def setup_method(self):
        self.context_manager = ContextManager()
        self.detector = ContextAwareDetector(self.context_manager)

    def test_context_manager_session(self):
        """æµè¯ä¼è¯ç®¡ç"""
        session_id = "test_session_001"
        
        ctx = self.context_manager.get_or_create_session(session_id)
        
        assert ctx is not None
        assert ctx.session_id == session_id

    def test_intent_history_tracking(self):
        """æµè¯æå¾åå²è¿½è¸ª"""
        session_id = "test_session_002"
        
        self.context_manager.add_message(session_id, "user", "åå»ºæä»¶", intent="file_create")
        self.context_manager.add_message(session_id, "user", "åå¥åå®¹", intent="file_write")
        
        ctx = self.context_manager.get_or_create_session(session_id)
        
        assert len(ctx.recent_intents) == 2
        assert ctx.recent_intents[0] == "file_create"
        assert ctx.recent_intents[1] == "file_write"

    def test_context_enhanced_detection(self):
        """æµè¯ä¸ä¸æå¢å¼ºæ£æµ?""
        session_id = "test_session_003"
        
        self.context_manager.add_message(session_id, "user", "åå»ºæä»¶", intent="file_create")
        
        intent, params, boost = self.detector.detect_with_context(
            message="åå¥ä¸äºåå®?,
            session_id=session_id,
            base_intent="file_write",
            base_params={}
        )
        
        assert intent is not None
        assert isinstance(boost, float)


class TestIntentDisambiguator:
    """æµè¯æå¾æ¶æ­§æ¨¡å"""

    def setup_method(self):
        self.disambiguator = IntentDisambiguator()

    def test_disambiguate_similar_intents(self):
        """æµè¯ç¸ä¼¼æå¾æ¶æ­§"""
        candidates = [
            ('file_read', 0.7, {}),
            ('file_write', 0.65, {})
        ]
        
        result = self.disambiguator.disambiguate(
            message='æå¼æä»¶ççåå®¹',
            candidates=candidates
        )
        
        assert result is not None
        assert result.resolved_intent in ['file_read', 'file_write']

    def test_distinguishing_keywords(self):
        """æµè¯åºåå³é®è¯?""
        result = self.disambiguator.disambiguate(
            message='ååºè¿ä¸ªç®å½çæä»?,
            candidates=[
                ('file_read', 0.5, {}),
                ('file_list', 0.5, {})
            ]
        )
        
        assert result.resolved_intent == 'file_list'

    def test_no_disambiguation_needed(self):
        """æµè¯æ éæ¶æ­§æåµ"""
        candidates = [
            ('file_create', 0.9, {}),
            ('file_read', 0.3, {})
        ]
        
        result = self.disambiguator.disambiguate(
            message='åå»ºæ°æä»?,
            candidates=candidates
        )
        
        assert result.resolved_intent == 'file_create'


class TestIntentMetrics:
    """æµè¯æ§è½ææ æ¨¡å"""

    def setup_method(self):
        self.metrics = IntentMetrics()

    def test_record_prediction(self):
        """æµè¯é¢æµè®°å½"""
        self.metrics.record('file_create', 'file_create', confidence=0.9)
        self.metrics.record('file_create', 'file_read', confidence=0.7)
        self.metrics.record('file_read', 'file_read', confidence=0.8)
        
        assert self.metrics.total_predictions == 3
        assert self.metrics.correct_predictions == 2

    def test_precision_calculation(self):
        """æµè¯ç²¾ç¡®çè®¡ç®?""
        self.metrics.record('file_create', 'file_create')
        self.metrics.record('file_create', 'file_create')
        self.metrics.record('file_create', 'file_read')
        
        precision = self.metrics.precision('file_create')
        
        assert 0 <= precision <= 1

    def test_recall_calculation(self):
        """æµè¯å¬åçè®¡ç®?""
        self.metrics.record('file_create', 'file_create')
        self.metrics.record('file_read', 'file_create')
        self.metrics.record('file_write', 'file_write')
        
        recall = self.metrics.recall('file_create')
        
        assert 0 <= recall <= 1

    def test_f1_score(self):
        """æµè¯F1åæ°è®¡ç®"""
        self.metrics.record('file_create', 'file_create')
        self.metrics.record('file_create', 'file_create')
        self.metrics.record('file_create', 'file_read')
        self.metrics.record('file_read', 'file_create')
        
        f1 = self.metrics.f1_score('file_create')
        
        assert 0 <= f1 <= 1

    def test_accuracy(self):
        """æµè¯åç¡®çè®¡ç®?""
        self.metrics.record('file_create', 'file_create')
        self.metrics.record('file_read', 'file_read')
        self.metrics.record('file_write', 'file_write')
        self.metrics.record('file_delete', 'file_read')
        
        accuracy = self.metrics.accuracy()
        
        assert accuracy == 0.75

    def test_metrics_report(self):
        """æµè¯ææ æ¥åçæ"""
        self.metrics.record('file_create', 'file_create')
        self.metrics.record('file_read', 'file_read')
        
        report = self.metrics.get_report()
        
        assert 'summary' in report
        assert 'accuracy' in report['summary']
        assert 'per_intent_metrics' in report


class TestMetricsAggregator:
    """æµè¯ææ èåå?""

    def setup_method(self):
        self.aggregator = MetricsAggregator()

    def test_session_aggregation(self):
        """æµè¯ä¼è¯ææ èå"""
        self.aggregator.record('file_create', 'file_create', session_id='session1')
        self.aggregator.record('file_read', 'file_read', session_id='session1')
        
        self.aggregator.record('file_create', 'file_read', session_id='session2')
        self.aggregator.record('file_write', 'file_write', session_id='session2')
        
        global_report = self.aggregator.get_global_report()
        
        assert global_report['summary']['total_predictions'] == 4


class TestIntentDetector:
    """æµè¯æå¾æ£æµå¨ä¸»æ¨¡å?""

    def setup_method(self):
        self.detector = IntentDetector(use_semantic=False)

    def test_detect_file_create(self):
        """æµè¯æä»¶åå»ºæå¾æ£æµ?""
        result = self.detector.detect('åå»ºä¸ä¸ªæ°æä»¶ /project/main.py')
        
        assert isinstance(result, IntentResult)
        assert result.action.value == 'file_create'
        assert result.confidence > 0.5

    def test_detect_file_read(self):
        """æµè¯æä»¶è¯»åæå¾æ£æµ?""
        result = self.detector.detect('è¯»å /data/config.json çåå®?)
        
        assert result.action.value == 'file_read'
        assert result.confidence > 0.5

    def test_detect_file_write(self):
        """æµè¯æä»¶åå¥æå¾æ£æµ?""
        result = self.detector.detect('æ?"Hello World" åå¥å?/test.txt æä»¶')
        
        assert result.action.value == 'file_write'

    def test_detect_file_delete(self):
        """æµè¯æä»¶å é¤æå¾æ£æµ?""
        result = self.detector.detect('å é¤ /tmp/cache.tmp æä»¶')
        
        assert result.action.value == 'file_delete'
        assert 'file_path' in result.params

    def test_detect_file_list(self):
        """æµè¯æä»¶åè¡¨æå¾æ£æµ?""
        result = self.detector.detect('ååº /home/user ç®å½ä¸çæææä»?)
        
        assert result.action.value == 'file_list'

    def test_detect_app_open(self):
        """æµè¯åºç¨æå¼æå¾æ£æµ?""
        result = self.detector.detect('æå¼è®¡ç®å?)
        
        assert result.action.value == 'app_open'
        assert 'app_name' in result.params

    def test_detect_url_open(self):
        """æµè¯URLæå¼æå¾æ£æµ?""
        result = self.detector.detect('æå¼ç½é¡µ https://github.com')
        
        assert result.action.value == 'url_open'
        assert 'url' in result.params

    def test_detect_with_context(self):
        """æµè¯å¸¦ä¸ä¸æçæå¾æ£æµ?""
        session_id = "context_test_session"
        
        result1 = self.detector.detect('åå»ºæä»¶ /test.txt', session_id=session_id)
        result2 = self.detector.detect('åå¥ä¸äºåå®?, session_id=session_id)
        
        assert result1.action.value == 'file_create'
        assert result2 is not None

    def test_detect_alternatives(self):
        """æµè¯å¤éæå?""
        result = self.detector.detect('å¤çè¿ä¸ªæä»¶')
        
        assert hasattr(result, 'alternatives')
        assert isinstance(result.alternatives, list)

    def test_detect_confidence_level(self):
        """æµè¯ç½®ä¿¡åº¦çº§å?""
        result = self.detector.detect('åå»ºæ°æä»?/test.py')
        
        assert hasattr(result, 'confidence_level')
        assert result.confidence_level in ['high', 'medium', 'low']

    def test_record_feedback(self):
        """æµè¯åé¦è®°å½"""
        from agent.agent_config import ActionType
        session_id = "feedback_test"
        self.detector.detect('åå»ºæä»¶', session_id=session_id)
        
        self.detector.record_feedback(
            session_id=session_id,
            predicted_action=ActionType.FILE_CREATE,
            is_correct=True
        )
        
        report = self.detector.get_metrics_report()
        assert 'summary' in report

    def test_get_metrics_report(self):
        """æµè¯è·åææ æ¥å"""
        report = self.detector.get_metrics_report()
        
        assert isinstance(report, dict)


class TestIntentDetectorEdgeCases:
    """æµè¯è¾¹çæ¡ä»¶åå¼å¸¸æå?""

    def setup_method(self):
        self.detector = IntentDetector(use_semantic=False)

    def test_empty_message(self):
        """æµè¯ç©ºæ¶æ?""
        result = self.detector.detect('')
        
        assert result is not None
        assert result.detected == False

    def test_whitespace_message(self):
        """æµè¯çº¯ç©ºç½æ¶æ?""
        result = self.detector.detect('   \t\n   ')
        
        assert result is not None

    def test_very_long_message(self):
        """æµè¯è¶é¿æ¶æ¯"""
        long_message = 'åå»ºæä»¶ ' + 'a' * 10000
        
        result = self.detector.detect(long_message)
        
        assert result is not None

    def test_special_characters(self):
        """æµè¯ç¹æ®å­ç¬¦"""
        result = self.detector.detect('åå»ºæä»¶ /path/with/special@#$%^&.txt')
        
        assert result is not None
        assert result.action.value == 'file_create'

    def test_chinese_english_mixed(self):
        """æµè¯ä¸­è±æ··å"""
        result = self.detector.detect('Create ä¸ä¸?new file å«å test.py')
        
        assert result is not None

    def test_ambiguous_intent(self):
        """æµè¯æ¨¡ç³æå¾"""
        result = self.detector.detect('å¤çä¸ä¸è¿ä¸?)
        
        assert result is not None
        assert hasattr(result, 'alternatives')

    def test_multiple_intents(self):
        """æµè¯å¤æå¾æ¶æ?""
        result = self.detector.detect('åå»ºæä»¶å¹¶åå¥åå®?)
        
        assert result is not None

    def test_unknown_intent(self):
        """æµè¯æªç¥æå¾"""
        result = self.detector.detect('ä»å¤©å¤©æ°æä¹æ ?)
        
        assert result is not None


class TestIntentDetectorPerformance:
    """æµè¯æ§è½"""

    def setup_method(self):
        self.detector = IntentDetector(use_semantic=False)

    def test_detection_speed(self):
        """æµè¯æ£æµéåº¦"""
        messages = [
            'åå»ºæä»¶ /test1.txt',
            'è¯»å /data.json',
            'å é¤ä¸´æ¶æä»¶',
            'æå¼æµè§å?,
            'ååºç®å½åå®¹'
        ]
        
        start_time = time.time()
        
        for msg in messages:
            self.detector.detect(msg)
        
        elapsed = time.time() - start_time
        
        assert elapsed < 1.0

    def test_batch_detection(self):
        """æµè¯æ¹éæ£æµ?""
        messages = [f'åå»ºæä»¶ /test{i}.txt' for i in range(100)]
        
        start_time = time.time()
        
        results = [self.detector.detect(msg) for msg in messages]
        
        elapsed = time.time() - start_time
        
        assert len(results) == 100
        assert elapsed < 5.0


class TestIntegration:
    """éææµè¯"""

    def test_full_detection_pipeline(self):
        """æµè¯å®æ´æ£æµæµæ°´çº¿"""
        detector = IntentDetector(use_semantic=False)
        
        test_cases = [
            ('åå»ºæ°æä»?/app/main.py', 'file_create'),
            ('è¯»åéç½®æä»¶ /etc/config.yaml', 'file_read'),
            ('åå¥æ°æ®å?output.json', 'file_write'),
            ('å é¤æ§çæ¥å¿æä»¶', 'file_delete'),
            ('ååºå½åç®å½', 'file_list'),
            ('æå¼è®°äºæ?, 'app_open'),
            ('è®¿é® https://google.com', 'url_open'),
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
        """æµè¯ä¼è¯ä¸ä¸ææµç¨?""
        detector = IntentDetector(use_semantic=False)
        session_id = "integration_session"
        
        result1 = detector.detect('åå»ºæä»¶ /project/app.py', session_id)
        assert result1.action.value == 'file_create'
        
        result2 = detector.detect('åå¥ä»£ç ', session_id)
        assert result2 is not None
        
        result3 = detector.detect('ä¿å­', session_id)
        assert result3 is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
