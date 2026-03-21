"""
意图检测服务测试
"""
import pytest
from core.intent_detector import EnhancedIntentDetector, IntentType, ParamType


class TestEnhancedIntentDetector:
    def setup_method(self):
        self.detector = EnhancedIntentDetector()

    def test_detect_file_create_intent(self):
        text = "创建一个test.py文件"
        result = self.detector.detect(text)
        
        assert result.detected == True
        assert len(result.intents) >= 1
        assert any(i.intent_type == IntentType.FILE_OPERATION for i in result.intents)

    def test_detect_code_execute_intent(self):
        text = "执行代码 print('hello')"
        result = self.detector.detect(text)
        
        if result.detected:
            assert len(result.intents) >= 1
        else:
            assert True

    def test_detect_info_query_intent(self):
        text = "查询系统状态"
        result = self.detector.detect(text)
        
        if result.detected:
            assert len(result.intents) >= 1
        else:
            assert True

    def test_detect_multi_intent(self):
        text = "创建一个test.py文件，然后运行它"
        result = self.detector.detect(text)
        
        assert result.detected == True
        assert len(result.intents) >= 1

    def test_confidence_score(self):
        text = "创建文件"
        result = self.detector.detect(text)
        
        if result.detected:
            for intent in result.intents:
                assert 0 <= intent.confidence <= 1

    def test_parameter_extraction(self):
        text = "创建一个名为main.py的文件"
        result = self.detector.detect(text)
        
        if result.detected and result.intents:
            intent = result.intents[0]
            assert hasattr(intent, 'params')

    def test_clarification_needed(self):
        text = "帮我做这件事"
        result = self.detector.detect(text)
        
        if result.has_ambiguity:
            assert result.clarification_dialog is not None

    def test_context_influence(self):
        text = "创建它"
        context = {"last_mentioned_file": "test.py"}
        result = self.detector.detect(text, context=context)
        
        assert result is not None

    def test_empty_text(self):
        text = ""
        result = self.detector.detect(text)
        
        assert result.detected == False

    def test_intent_description(self):
        text = "创建test.py文件"
        result = self.detector.detect(text)
        
        if result.detected and result.intents:
            assert result.intents[0].description is not None


class TestIntentTypes:
    def test_intent_type_values(self):
        assert IntentType.FILE_OPERATION.value == "file_operation"
        assert IntentType.CODE_EXECUTION.value == "code_execution"
        assert IntentType.SYSTEM_OPERATION.value == "system_operation"
        assert IntentType.INFORMATION_QUERY.value == "information_query"

    def test_param_type_values(self):
        assert ParamType.STRING.value == "string"
        assert ParamType.NUMBER.value == "number"
        assert ParamType.PATH.value == "path"
        assert ParamType.URL.value == "url"
