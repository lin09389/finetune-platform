"""
实体识别服务
支持命名实体识别（NER）和实体高亮
"""
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class Entity:
    text: str
    label: str
    start: int
    end: int
    confidence: float = 1.0
    metadata: dict[str, Any] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "label": self.label,
            "start": self.start,
            "end": self.end,
            "confidence": self.confidence,
            "metadata": self.metadata or {},
        }


class EntityRecognizer:
    """基于规则的实体识别器"""

    ENTITY_PATTERNS = {
        "PERSON": [
            r"[张王李刘陈杨赵黄周吴徐孙胡朱高林何郭马罗梁宋郑谢韩唐冯于董萧程曹袁邓许傅沈曾彭吕苏卢蒋蒋蔡贾丁魏薛叶阎余潘杜戴夏钟汪田任姜范方石姚谭廖邹熊金陆郝孔白崔康毛邱秦江史顾侯邵孟龙万段雷钱汤尹黎易常武乔贺赖龚文]",
            r"[张王李刘陈杨赵黄周吴徐孙胡朱高林何郭马罗梁宋郑谢韩唐冯于董萧程曹袁邓许傅沈曾彭吕苏卢蒋蒋蔡贾丁魏薛叶阎余潘杜戴夏钟汪田任姜范方石姚谭廖邹熊金陆郝孔白崔康毛邱秦江史顾侯邵孟龙万段雷钱汤尹黎易常武乔贺赖龚文]{2,4}",
        ],
        "ORGANIZATION": [
            r"[\u4e00-\u9fa5]+公司",
            r"[\u4e00-\u9fa5]+集团",
            r"[\u4e00-\u9fa5]+银行",
            r"[\u4e00-\u9fa5]+大学",
            r"[\u4e00-\u9fa5]+研究院",
            r"[\u4e00-\u9fa5]+医院",
            r"[\u4e00-\u9fa5]+政府",
            r"[\u4e00-\u9fa5]+部门",
            r"腾讯|阿里巴巴|百度|字节跳动|华为|小米|京东|美团|滴滴|快手",
        ],
        "LOCATION": [
            r"[\u4e00-\u9fa5]+省",
            r"[\u4e00-\u9fa5]+市",
            r"[\u4e00-\u9fa5]+区",
            r"[\u4e00-\u9fa5]+县",
            r"[\u4e00-\u9fa5]+镇",
            r"[\u4e00-\u9fa5]+村",
            r"北京|上海|广州|深圳|杭州|南京|武汉|成都|西安|重庆|天津|苏州|郑州|长沙|东莞|青岛|沈阳|宁波|昆明",
        ],
        "DATE": [
            r"\d{4}年\d{1,2}月\d{1,2}日",
            r"\d{4}-\d{1,2}-\d{1,2}",
            r"\d{4}/\d{1,2}/\d{1,2}",
            r"\d{1,2}月\d{1,2}日",
            r"今天|明天|后天|昨天|前天",
            r"上周|下周|本周",
            r"上个月|下个月|这个月",
            r"去年|今年|明年",
        ],
        "TIME": [
            r"\d{1,2}:\d{2}",
            r"\d{1,2}点\d{0,2}分?",
            r"早上|上午|中午|下午|晚上|凌晨",
        ],
        "MONEY": [
            r"\d+(\.\d{1,2})?元",
            r"\d+(\.\d{1,2})?万",
            r"\d+(\.\d{1,2})?亿",
            r"\$\d+(\.\d{1,2})?",
            r"￥\d+(\.\d{1,2})?",
        ],
        "PHONE": [
            r"1[3-9]\d{9}",
            r"\d{3,4}-\d{7,8}",
            r"\d{3,4}\s\d{7,8}",
        ],
        "EMAIL": [
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        ],
        "URL": [
            r"https?://[^\s]+",
            r"www\.[^\s]+\.[a-zA-Z]{2,}",
        ],
        "FILE_PATH": [
            r"[A-Za-z]:\\[\w\\\-\.]+",
            r"/[\w/\-\.]+",
            r"[\w\-]+\.\w{1,5}",
        ],
        "CODE": [
            r"```[\s\S]*?```",
            r"`[^`]+`",
        ],
        "IP_ADDRESS": [
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",
        ],
    }

    ENTITY_COLORS = {
        "PERSON": "#1890ff",
        "ORGANIZATION": "#722ed1",
        "LOCATION": "#13c2c2",
        "DATE": "#fa8c16",
        "TIME": "#faad14",
        "MONEY": "#52c41a",
        "PHONE": "#eb2f96",
        "EMAIL": "#2f54eb",
        "URL": "#1890ff",
        "FILE_PATH": "#fa541c",
        "CODE": "#595959",
        "IP_ADDRESS": "#f5222d",
    }

    ENTITY_LABELS_ZH = {
        "PERSON": "人物",
        "ORGANIZATION": "组织",
        "LOCATION": "地点",
        "DATE": "日期",
        "TIME": "时间",
        "MONEY": "金额",
        "PHONE": "电话",
        "EMAIL": "邮箱",
        "URL": "网址",
        "FILE_PATH": "文件",
        "CODE": "代码",
        "IP_ADDRESS": "IP地址",
    }

    def __init__(self):
        self.compiled_patterns = {
            label: [re.compile(p) for p in patterns]
            for label, patterns in self.ENTITY_PATTERNS.items()
        }

    def recognize(self, text: str) -> list[Entity]:
        entities = []
        seen_ranges = set()

        for label, patterns in self.compiled_patterns.items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    start, end = match.start(), match.end()

                    if any(
                        start < r_end and end > r_start
                        for r_start, r_end in seen_ranges
                    ):
                        continue

                    seen_ranges.add((start, end))

                    entity = Entity(
                        text=match.group(),
                        label=label,
                        start=start,
                        end=end,
                        confidence=0.85,
                        metadata={
                            "label_zh": self.ENTITY_LABELS_ZH.get(label, label),
                            "color": self.ENTITY_COLORS.get(label, "#999"),
                        },
                    )
                    entities.append(entity)

        entities.sort(key=lambda e: e.start)
        return entities

    def highlight_text(self, text: str, entities: list[Entity]) -> str:
        if not entities:
            return text

        result = []
        last_end = 0

        for entity in entities:
            result.append(text[last_end:entity.start])

            color = self.ENTITY_COLORS.get(entity.label, "#999")
            label_zh = self.ENTITY_LABELS_ZH.get(entity.label, entity.label)

            result.append(
                f'<span style="background-color: {color}20; '
                f'border-bottom: 2px solid {color}; '
                f'padding: 0 2px; border-radius: 2px;" '
                f'title="{label_zh}">{entity.text}</span>'
            )
            last_end = entity.end

        result.append(text[last_end:])
        return "".join(result)

    def get_entity_stats(self, entities: list[Entity]) -> dict[str, int]:
        stats = {}
        for entity in entities:
            label = self.ENTITY_LABELS_ZH.get(entity.label, entity.label)
            stats[label] = stats.get(label, 0) + 1
        return stats

    def link_to_memory(
        self,
        entities: list[Entity],
        memory_entities: dict[str, Any],
    ) -> list[Entity]:
        for entity in entities:
            if entity.text in memory_entities:
                entity.metadata["memory_linked"] = True
                entity.metadata["memory_data"] = memory_entities[entity.text]
        return entities


class EntityHighlighter:
    """实体高亮处理器"""

    def __init__(self, recognizer: EntityRecognizer):
        self.recognizer = recognizer

    def process_message(
        self,
        text: str,
        highlight: bool = True,
        link_memory: bool = False,
        memory_entities: dict[str, Any] = None,
    ) -> dict[str, Any]:
        entities = self.recognizer.recognize(text)

        if link_memory and memory_entities:
            entities = self.recognizer.link_to_memory(entities, memory_entities)

        result = {
            "original_text": text,
            "entities": [e.to_dict() for e in entities],
            "entity_count": len(entities),
            "entity_stats": self.recognizer.get_entity_stats(entities),
        }

        if highlight:
            result["highlighted_text"] = self.recognizer.highlight_text(text, entities)
        else:
            result["highlighted_text"] = text

        return result


entity_recognizer = EntityRecognizer()
entity_highlighter = EntityHighlighter(entity_recognizer)
