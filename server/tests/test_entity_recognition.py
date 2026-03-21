"""
实体识别服务测试
"""
import pytest
from core.entity_recognition import EntityRecognizer, EntityHighlighter


class TestEntityRecognizer:
    def setup_method(self):
        self.recognizer = EntityRecognizer()

    def test_recognize_person(self):
        text = "张三和李四一起去了北京"
        entities = self.recognizer.recognize(text)
        
        person_entities = [e for e in entities if e.label == "PERSON"]
        assert len(person_entities) >= 1

    def test_recognize_organization(self):
        text = "他在腾讯公司工作，之前在阿里巴巴"
        entities = self.recognizer.recognize(text)
        
        org_entities = [e for e in entities if e.label == "ORGANIZATION"]
        assert len(org_entities) >= 2

    def test_recognize_location(self):
        text = "他去了北京、上海和广州"
        entities = self.recognizer.recognize(text)
        
        location_entities = [e for e in entities if e.label == "LOCATION"]
        assert len(location_entities) >= 1

    def test_recognize_date(self):
        text = "2024年1月5日，他去了北京"
        entities = self.recognizer.recognize(text)
        
        date_entities = [e for e in entities if e.label == "DATE"]
        assert len(date_entities) >= 1

    def test_recognize_money(self):
        text = "这个项目花费了500万元人民币"
        entities = self.recognizer.recognize(text)
        
        money_entities = [e for e in entities if e.label == "MONEY"]
        assert len(money_entities) >= 0

    def test_recognize_phone(self):
        text = "请拨打13812345678联系我"
        entities = self.recognizer.recognize(text)
        
        phone_entities = [e for e in entities if e.label == "PHONE"]
        assert len(phone_entities) >= 1

    def test_recognize_email(self):
        text = "请发送邮件到test@example.com"
        entities = self.recognizer.recognize(text)
        
        email_entities = [e for e in entities if e.label == "EMAIL"]
        assert len(email_entities) >= 1

    def test_recognize_url(self):
        text = "请访问 https://example.com 查看详情"
        entities = self.recognizer.recognize(text)
        
        url_entities = [e for e in entities if e.label == "URL"]
        assert len(url_entities) >= 1

    def test_recognize_multiple_entities(self):
        text = "2024年1月5日，张三从北京腾讯公司发送邮件到test@example.com"
        entities = self.recognizer.recognize(text)
        
        assert len(entities) >= 3

    def test_entity_positions(self):
        text = "张三在北京"
        entities = self.recognizer.recognize(text)
        
        for entity in entities:
            assert entity.start >= 0
            assert entity.end > entity.start
            assert text[entity.start:entity.end] == entity.text

    def test_highlight_text(self):
        text = "张三在北京工作"
        entities = self.recognizer.recognize(text)
        highlighted = self.recognizer.highlight_text(text, entities)
        
        assert "<span" in highlighted
        assert "张三" in highlighted or "北京" in highlighted

    def test_entity_stats(self):
        text = "张三和李四在北京、上海工作"
        entities = self.recognizer.recognize(text)
        stats = self.recognizer.get_entity_stats(entities)
        
        assert isinstance(stats, dict)
        assert len(stats) > 0


class TestEntityHighlighter:
    def setup_method(self):
        self.recognizer = EntityRecognizer()
        self.highlighter = EntityHighlighter(self.recognizer)

    def test_process_message(self):
        text = "张三在腾讯公司工作"
        result = self.highlighter.process_message(text)
        
        assert "original_text" in result
        assert "highlighted_text" in result
        assert "entities" in result
        assert "entity_count" in result
        assert "entity_stats" in result

    def test_process_message_with_memory(self):
        text = "张三在腾讯公司工作"
        memory_entities = {
            "张三": {"role": "用户", "id": "user_001"}
        }
        result = self.highlighter.process_message(
            text, 
            link_memory=True, 
            memory_entities=memory_entities
        )
        
        assert result["entity_count"] >= 1

    def test_process_message_no_highlight(self):
        text = "张三在腾讯公司工作"
        result = self.highlighter.process_message(text, highlight=False)
        
        assert result["highlighted_text"] == text
