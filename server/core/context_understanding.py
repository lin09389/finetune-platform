"""
上下文理解增强模�?
功能�?1. 代词消解（指代消解）- 识别代词并解析指向实�?2. 省略补全 - 检测省略句并根据上下文补全
3. 对话摘要生成 - 长对话自动摘�?4. 长上下文窗口管理 - 滑动窗口策略和Token预算管理
"""
import re
import logging
import threading
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
from enum import Enum
import json

logger = logging.getLogger(__name__)


class EntityType(str, Enum):
    """实体类型"""
    PERSON = "person"
    OBJECT = "object"
    CONCEPT = "concept"
    CODE = "code"
    FILE = "file"
    FUNCTION = "function"
    VARIABLE = "variable"
    UNKNOWN = "unknown"


class PronounType(str, Enum):
    """代词类型"""
    PERSONAL = "personal"
    DEMONSTRATIVE = "demonstrative"
    INTERROGATIVE = "interrogative"
    RELATIVE = "relative"


@dataclass
class Entity:
    """实体"""
    id: str
    text: str
    entity_type: EntityType
    mentions: List[str] = field(default_factory=list)
    first_mention_idx: int = 0
    last_mention_idx: int = 0
    importance: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PronounResolution:
    """代词消解结果"""
    pronoun: str
    pronoun_type: PronounType
    resolved_entity: Optional[Entity]
    confidence: float
    position: Tuple[int, int]
    context: str


@dataclass
class OmissionCompletion:
    """省略补全结果"""
    original_text: str
    completed_text: str
    omitted_parts: List[str]
    confidence: float
    source_message_idx: Optional[int] = None


@dataclass
class Message:
    """对话消息"""
    id: str
    role: str
    content: str
    timestamp: str
    token_count: int = 0
    importance: float = 0.5
    entities: List[Entity] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationSummary:
    """对话摘要"""
    summary_text: str
    key_points: List[str]
    entities_mentioned: List[str]
    topics: List[str]
    token_count: int
    message_range: Tuple[int, int]
    created_at: str


class PronounResolver:
    """代词消解�?""

    PERSONAL_PRONOUNS = {
        "�?: {"type": PronounType.PERSONAL, "gender": "male", "entity_types": [EntityType.PERSON]},
        "�?: {"type": PronounType.PERSONAL, "gender": "female", "entity_types": [EntityType.PERSON]},
        "�?: {"type": PronounType.PERSONAL, "gender": "neutral", "entity_types": [EntityType.OBJECT, EntityType.CONCEPT]},
        "他们": {"type": PronounType.PERSONAL, "gender": "plural", "entity_types": [EntityType.PERSON]},
        "她们": {"type": PronounType.PERSONAL, "gender": "plural_female", "entity_types": [EntityType.PERSON]},
        "它们": {"type": PronounType.PERSONAL, "gender": "plural_neutral", "entity_types": [EntityType.OBJECT, EntityType.CONCEPT]},
    }

    DEMONSTRATIVE_PRONOUNS = {
        "�?: {"type": PronounType.DEMONSTRATIVE, "distance": "near"},
        "这个": {"type": PronounType.DEMONSTRATIVE, "distance": "near"},
        "�?: {"type": PronounType.DEMONSTRATIVE, "distance": "far"},
        "那个": {"type": PronounType.DEMONSTRATIVE, "distance": "far"},
        "这些": {"type": PronounType.DEMONSTRATIVE, "distance": "near_plural"},
        "那些": {"type": PronounType.DEMONSTRATIVE, "distance": "far_plural"},
        "这里": {"type": PronounType.DEMONSTRATIVE, "distance": "near_place"},
        "那里": {"type": PronounType.DEMONSTRATIVE, "distance": "far_place"},
    }

    INTERROGATIVE_PRONOUNS = {
        "�?: {"type": PronounType.INTERROGATIVE, "query_type": "person"},
        "什�?: {"type": PronounType.INTERROGATIVE, "query_type": "thing"},
        "�?: {"type": PronounType.INTERROGATIVE, "query_type": "choice"},
        "哪个": {"type": PronounType.INTERROGATIVE, "query_type": "choice"},
        "哪里": {"type": PronounType.INTERROGATIVE, "query_type": "place"},
        "怎么": {"type": PronounType.INTERROGATIVE, "query_type": "manner"},
    }

    ENTITY_PATTERNS = {
        EntityType.PERSON: [
            r"([^\s]+?)(?:说|问|回答|认为|觉得|表示|指出)",
            r"([^\s]+?)(?:先生|女士|老师|教授|博士|工程�?",
            r"用户([^\s]*)",
        ],
        EntityType.CODE: [
            r"(\w+)\s*(?:函数|方法|类|模块|变量)",
            r"function\s+(\w+)",
            r"class\s+(\w+)",
            r"def\s+(\w+)",
            r"const\s+(\w+)",
            r"let\s+(\w+)",
            r"var\s+(\w+)",
        ],
        EntityType.FILE: [
            r"([^\s]+\.\w+)\s*(?:文件|配置)",
            r"文件\s+([^\s]+)",
            r"([^\s]+\.py|\.js|\.ts|\.tsx|\.java|\.go|\.rs)",
        ],
        EntityType.FUNCTION: [
            r"(\w+)\s*(?:方法|函数|接口)",
            r"调用\s+(\w+)",
            r"执行\s+(\w+)",
        ],
    }

    def __init__(self):
        self.entity_registry: Dict[str, Entity] = {}
        self.entity_counter = 0

    def _generate_entity_id(self) -> str:
        self.entity_counter += 1
        return f"entity_{self.entity_counter}"

    def extract_entities(self, text: str, message_idx: int = 0) -> List[Entity]:
        """从文本中提取实体"""
        entities = []

        for entity_type, patterns in self.ENTITY_PATTERNS.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text)
                for match in matches:
                    entity_text = match.group(1).strip()
                    if entity_text and len(entity_text) > 1:
                        entity = Entity(
                            id=self._generate_entity_id(),
                            text=entity_text,
                            entity_type=entity_type,
                            mentions=[entity_text],
                            first_mention_idx=message_idx,
                            last_mention_idx=message_idx,
                            importance=0.6
                        )
                        entities.append(entity)

        return entities

    def find_pronouns(self, text: str) -> List[Tuple[str, PronounType, Tuple[int, int]]]:
        """查找文本中的代词"""
        pronouns = []

        all_pronouns = {}
        all_pronouns.update({k: v for k, v in self.PERSONAL_PRONOUNS.items()})
        all_pronouns.update({k: v for k, v in self.DEMONSTRATIVE_PRONOUNS.items()})

        for pronoun, info in all_pronouns.items():
            for match in re.finditer(re.escape(pronoun), text):
                pronouns.append((pronoun, info["type"], (match.start(), match.end())))

        pronouns.sort(key=lambda x: x[2][0])
        return pronouns

    def resolve_pronoun(
        self,
        pronoun: str,
        pronoun_type: PronounType,
        position: Tuple[int, int],
        context: str,
        entities: List[Entity],
        messages: List[Message]
    ) -> PronounResolution:
        """解析单个代词"""
        resolved_entity = None
        confidence = 0.0

        if pronoun in self.PERSONAL_PRONOUNS:
            pronoun_info = self.PERSONAL_PRONOUNS[pronoun]
            allowed_types = pronoun_info.get("entity_types", [])

            candidates = [
                e for e in entities
                if e.entity_type in allowed_types
            ]

            if candidates:
                candidates.sort(key=lambda e: (-e.importance, -e.last_mention_idx))
                resolved_entity = candidates[0]
                confidence = 0.8 if resolved_entity.importance > 0.7 else 0.6

        elif pronoun in self.DEMONSTRATIVE_PRONOUNS:
            pronoun_info = self.DEMONSTRATIVE_PRONOUNS[pronoun]
            distance = pronoun_info.get("distance", "near")

            if messages:
                last_message = messages[-1]
                if last_message.entities:
                    resolved_entity = last_message.entities[-1]
                    confidence = 0.7

                if not resolved_entity and entities:
                    entities_sorted = sorted(entities, key=lambda e: -e.last_mention_idx)
                    resolved_entity = entities_sorted[0] if entities_sorted else None
                    confidence = 0.5

        return PronounResolution(
            pronoun=pronoun,
            pronoun_type=pronoun_type,
            resolved_entity=resolved_entity,
            confidence=confidence,
            position=position,
            context=context[max(0, position[0] - 20):position[1] + 20]
        )

    def resolve_all(
        self,
        text: str,
        messages: List[Message]
    ) -> Tuple[str, List[PronounResolution]]:
        """解析文本中所有代�?""
        all_entities = []
        for msg in messages:
            all_entities.extend(msg.entities)

        pronouns = self.find_pronouns(text)
        resolutions = []

        result_text = text
        offset = 0

        for pronoun, pronoun_type, position in pronouns:
            resolution = self.resolve_pronoun(
                pronoun, pronoun_type, position, text, all_entities, messages
            )
            resolutions.append(resolution)

            if resolution.resolved_entity and resolution.confidence > 0.5:
                entity_text = resolution.resolved_entity.text
                new_position = (position[0] + offset, position[1] + offset)
                result_text = (
                    result_text[:new_position[0]] +
                    f"[{entity_text}]" +
                    result_text[new_position[1]:]
                )
                offset += len(entity_text) + 2 - (position[1] - position[0])

        return result_text, resolutions


class OmissionCompleter:
    """省略补全�?""

    OMISSION_PATTERNS = [
        (r"^(是|对|好|行|可以|没问�?$", "是的，{context}"),
        (r"^(不|不是|不行|不可�?$", "不是，{context}"),
        (r"^(有|有的)$", "有{context}"),
        (r"^(没有|�?$", "没有{context}"),
        (r"^(能|可以|�?$", "可以{context}"),
        (r"^(不能|不可以|不行)$", "不可以{context}"),
        (r"^(会|会的)$", "会{context}"),
        (r"^(不会)$", "不会{context}"),
        (r"^(知道|晓得)$", "知道{context}"),
        (r"^(不知道|不清�?$", "不知道{context}"),
        (r"^(好的|�?$", "好的，{context}"),
        (r"^(谢谢|感谢)$", "谢谢，{context}"),
        (r"^(为什么|为啥)$", "为什么{context}"),
        (r"^(怎么样|如何)$", "{context}怎么�?),
        (r"^(多少|几个)$", "{context}有多�?),
    ]

    QUESTION_PATTERNS = [
        r"(.+?)�?.+?)吗[�?]?$",
        r"(.+?)�?.+?)吗[�?]?$",
        r"(.+?)�?.+?)吗[�?]?$",
        r"(.+?)�?.+?)吗[�?]?$",
        r"(.+?)可以(.+?)吗[�?]?$",
        r"(.+?)知道(.+?)吗[�?]?$",
        r"是不�?.+?)[�?]?$",
        r"有没�?.+?)[�?]?$",
        r"能不�?.+?)[�?]?$",
        r"会不�?.+?)[�?]?$",
        r"可不可以(.+?)[�?]?$",
    ]

    def __init__(self):
        pass

    def detect_omission(self, text: str) -> Tuple[bool, Optional[str]]:
        """检测是否为省略�?""
        text = text.strip()

        for pattern, _ in self.OMISSION_PATTERNS:
            if re.match(pattern, text):
                return True, pattern

        if len(text) <= 4 and not re.search(r"[。！�?!?]", text):
            if re.match(r"^[是是非对好行能不能会知]$", text):
                return True, text

        return False, None

    def extract_question_context(self, question: str) -> Optional[str]:
        """从问题中提取上下�?""
        for pattern in self.QUESTION_PATTERNS:
            match = re.match(pattern, question)
            if match:
                groups = match.groups()
                if len(groups) >= 2:
                    return f"{groups[0]}{groups[1]}"
                return groups[0]
        return None

    def complete_omission(
        self,
        text: str,
        messages: List[Message]
    ) -> OmissionCompletion:
        """补全省略内容"""
        is_omission, pattern = self.detect_omission(text)

        if not is_omission:
            return OmissionCompletion(
                original_text=text,
                completed_text=text,
                omitted_parts=[],
                confidence=1.0
            )

        context = None
        source_idx = None

        for i in range(len(messages) - 1, max(-1, len(messages) - 5), -1):
            msg = messages[i]
            if msg.role == "user":
                extracted = self.extract_question_context(msg.content)
                if extracted:
                    context = extracted
                    source_idx = i
                    break

        if not context:
            if messages:
                last_user_msg = None
                for msg in reversed(messages):
                    if msg.role == "user":
                        last_user_msg = msg.content
                        break
                if last_user_msg:
                    context = last_user_msg[:50]

        if not context:
            context = "这件�?

        completed_text = text
        omitted_parts = []

        for omit_pattern, template in self.OMISSION_PATTERNS:
            if re.match(omit_pattern, text.strip()):
                completed_text = template.format(context=context)
                omitted_parts.append(context)
                break

        confidence = 0.9 if source_idx is not None else 0.6

        return OmissionCompletion(
            original_text=text,
            completed_text=completed_text,
            omitted_parts=omitted_parts,
            confidence=confidence,
            source_message_idx=source_idx
        )


class ConversationSummarizer:
    """对话摘要生成�?""

    KEYWORD_WEIGHTS = {
        "问题": 1.5,
        "解决": 1.3,
        "完成": 1.2,
        "重要": 1.4,
        "关键": 1.3,
        "错误": 1.2,
        "成功": 1.2,
        "失败": 1.1,
        "建议": 1.1,
        "注意": 1.2,
    }

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    def calculate_importance(self, message: Message) -> float:
        """计算消息重要�?""
        base_importance = message.importance

        content = message.content
        keyword_boost = 0.0

        for keyword, weight in self.KEYWORD_WEIGHTS.items():
            if keyword in content:
                keyword_boost += (weight - 1.0) * 0.1

        length_factor = min(len(content) / 200, 1.0) * 0.2

        question_factor = 0.1 if "?" in content or "�? in content else 0.0

        code_factor = 0.15 if "```" in content or "def " in content or "function " in content else 0.0

        return min(base_importance + keyword_boost + length_factor + question_factor + code_factor, 1.0)

    def extract_key_points(self, messages: List[Message]) -> List[str]:
        """提取关键�?""
        key_points = []

        for msg in messages:
            importance = self.calculate_importance(msg)
            if importance > 0.6:
                sentences = re.split(r"[。！�?!?]", msg.content)
                for sentence in sentences:
                    sentence = sentence.strip()
                    if len(sentence) > 10:
                        has_keyword = any(kw in sentence for kw in self.KEYWORD_WEIGHTS.keys())
                        if has_keyword:
                            key_points.append(sentence[:100])

        return key_points[:10]

    def extract_entities_summary(self, messages: List[Message]) -> List[str]:
        """提取涉及的实体摘�?""
        entity_counts: Dict[str, int] = {}

        for msg in messages:
            for entity in msg.entities:
                entity_counts[entity.text] = entity_counts.get(entity.text, 0) + 1

        sorted_entities = sorted(entity_counts.items(), key=lambda x: -x[1])
        return [e[0] for e in sorted_entities[:10]]

    def extract_topics(self, messages: List[Message]) -> List[str]:
        """提取主题"""
        topic_keywords = {
            "代码": ["代码", "函数", "�?, "变量", "编程"],
            "问题": ["问题", "错误", "bug", "异常", "失败"],
            "配置": ["配置", "设置", "参数", "选项"],
            "模型": ["模型", "训练", "微调", "推理"],
            "数据": ["数据", "数据�?, "文件", "导入"],
        }

        topic_scores = {topic: 0 for topic in topic_keywords}

        for msg in messages:
            content = msg.content.lower()
            for topic, keywords in topic_keywords.items():
                for keyword in keywords:
                    if keyword in content:
                        topic_scores[topic] += 1

        sorted_topics = sorted(topic_scores.items(), key=lambda x: -x[1])
        return [t[0] for t in sorted_topics if t[1] > 0][:5]

    def summarize_rule_based(
        self,
        messages: List[Message],
        max_length: int = 500
    ) -> ConversationSummary:
        """基于规则的摘要生�?""
        if not messages:
            return ConversationSummary(
                summary_text="",
                key_points=[],
                entities_mentioned=[],
                topics=[],
                token_count=0,
                message_range=(0, 0),
                created_at=datetime.now().isoformat()
            )

        key_points = self.extract_key_points(messages)
        entities = self.extract_entities_summary(messages)
        topics = self.extract_topics(messages)

        summary_parts = []

        if topics:
            summary_parts.append(f"讨论主题：{', '.join(topics[:3])}")

        if entities:
            summary_parts.append(f"涉及实体：{', '.join(entities[:5])}")

        if key_points:
            summary_parts.append("关键内容�?)
            for i, point in enumerate(key_points[:5], 1):
                summary_parts.append(f"  {i}. {point}")

        summary_text = "\n".join(summary_parts)

        if len(summary_text) > max_length:
            summary_text = summary_text[:max_length] + "..."

        token_count = len(summary_text) // 2

        return ConversationSummary(
            summary_text=summary_text,
            key_points=key_points,
            entities_mentioned=entities,
            topics=topics,
            token_count=token_count,
            message_range=(0, len(messages) - 1),
            created_at=datetime.now().isoformat()
        )

    async def summarize_with_llm(
        self,
        messages: List[Message],
        max_length: int = 500
    ) -> ConversationSummary:
        """使用 LLM 生成摘要"""
        if not self.llm_client:
            return self.summarize_rule_based(messages, max_length)

        try:
            conversation_text = "\n".join([
                f"{msg.role}: {msg.content}"
                for msg in messages
            ])

            prompt = f"""请对以下对话进行摘要，要求：
1. 提取主要讨论的主�?2. 总结关键信息和结�?3. 列出涉及的重要实�?4. 保持简洁，不超过{max_length}�?
对话内容�?{conversation_text}

请用以下格式输出�?主题�?..
关键点：...
涉及实体�?.."""

            response = await self.llm_client.generate(prompt)
            summary_text = response.get("text", "")

            return ConversationSummary(
                summary_text=summary_text,
                key_points=self.extract_key_points(messages),
                entities_mentioned=self.extract_entities_summary(messages),
                topics=self.extract_topics(messages),
                token_count=len(summary_text) // 2,
                message_range=(0, len(messages) - 1),
                created_at=datetime.now().isoformat()
            )
        except Exception as e:
            logger.error(f"LLM 摘要生成失败: {e}")
            return self.summarize_rule_based(messages, max_length)

    def summarize(
        self,
        messages: List[Message],
        max_length: int = 500,
        use_llm: bool = False
    ) -> ConversationSummary:
        """生成摘要"""
        if use_llm and self.llm_client:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(
                    self.summarize_with_llm(messages, max_length)
                )
            except RuntimeError:
                return self.summarize_rule_based(messages, max_length)
        return self.summarize_rule_based(messages, max_length)


class ContextWindowManager:
    """长上下文窗口管理�?""

    def __init__(
        self,
        max_tokens: int = 4096,
        reserved_tokens: int = 512,
        summary_threshold: float = 0.8
    ):
        self.max_tokens = max_tokens
        self.reserved_tokens = reserved_tokens
        self.summary_threshold = summary_threshold
        self.summarizer = ConversationSummarizer()
        self._lock = threading.Lock()

    def count_tokens(self, text: str) -> int:
        """估算 Token 数量"""
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        english_words = len(re.findall(r"[a-zA-Z]+", text))
        other_chars = len(text) - chinese_chars - sum(len(w) for w in re.findall(r"[a-zA-Z]+", text))

        return chinese_chars + english_words + other_chars // 2

    def count_message_tokens(self, message: Message) -> int:
        """计算消息�?Token 数量"""
        if message.token_count > 0:
            return message.token_count
        return self.count_tokens(message.content) + 10

    def get_window_messages(
        self,
        messages: List[Message],
        keep_recent: int = 3
    ) -> Tuple[List[Message], int]:
        """获取窗口内的消息"""
        total_tokens = 0
        window_messages = []

        for msg in reversed(messages):
            msg_tokens = self.count_message_tokens(msg)
            if total_tokens + msg_tokens > self.max_tokens - self.reserved_tokens:
                break
            window_messages.insert(0, msg)
            total_tokens += msg_tokens

        if len(window_messages) < len(messages):
            recent_messages = messages[-keep_recent:] if len(messages) >= keep_recent else messages
            for msg in recent_messages:
                if msg not in window_messages:
                    window_messages.append(msg)

        return window_messages, total_tokens

    def prioritize_messages(
        self,
        messages: List[Message]
    ) -> List[Message]:
        """按重要性排序消�?""
        scored_messages = []
        for i, msg in enumerate(messages):
            importance = self.summarizer.calculate_importance(msg)
            recency = (i + 1) / len(messages)
            score = importance * 0.6 + recency * 0.4
            scored_messages.append((score, msg))

        scored_messages.sort(key=lambda x: -x[0])
        return [msg for _, msg in scored_messages]

    def create_summary_for_overflow(
        self,
        messages: List[Message],
        window_messages: List[Message]
    ) -> Optional[ConversationSummary]:
        """为溢出消息创建摘�?""
        overflow_messages = [m for m in messages if m not in window_messages]

        if not overflow_messages:
            return None

        return self.summarizer.summarize(overflow_messages)

    def manage_window(
        self,
        messages: List[Message],
        keep_recent: int = 3
    ) -> Dict[str, Any]:
        """管理上下文窗�?""
        with self._lock:
            if not messages:
                return {
                    "window_messages": [],
                    "total_tokens": 0,
                    "summary": None,
                    "overflow_count": 0
                }

            window_messages, total_tokens = self.get_window_messages(messages, keep_recent)

            summary = None
            overflow_count = len(messages) - len(window_messages)

            if overflow_count > 0:
                summary = self.create_summary_for_overflow(messages, window_messages)

            return {
                "window_messages": window_messages,
                "total_tokens": total_tokens,
                "summary": summary,
                "overflow_count": overflow_count,
                "max_tokens": self.max_tokens,
                "utilization": total_tokens / self.max_tokens
            }

    def format_context_for_prompt(
        self,
        messages: List[Message],
        include_summary: bool = True
    ) -> str:
        """格式化上下文用于提示�?""
        result = self.manage_window(messages)

        parts = []

        if include_summary and result["summary"]:
            parts.append("【历史摘要�?)
            parts.append(result["summary"].summary_text)
            parts.append("")

        parts.append("【当前对话�?)
        for msg in result["window_messages"]:
            role_label = "用户" if msg.role == "user" else "助手"
            parts.append(f"{role_label}: {msg.content}")

        return "\n".join(parts)


class ContextUnderstandingEngine:
    """上下文理解引�?""

    def __init__(self, llm_client=None, max_context_tokens: int = 4096):
        self.pronoun_resolver = PronounResolver()
        self.omission_completer = OmissionCompleter()
        self.summarizer = ConversationSummarizer(llm_client)
        self.window_manager = ContextWindowManager(max_tokens=max_context_tokens)
        self._lock = threading.Lock()

    def process_message(
        self,
        message: Message,
        history: List[Message]
    ) -> Dict[str, Any]:
        """处理消息，返回增强后的上下文"""
        with self._lock:
            resolved_text, resolutions = self.pronoun_resolver.resolve_all(
                message.content, history
            )

            completion = self.omission_completer.complete_omission(
                message.content, history
            )

            entities = self.pronoun_resolver.extract_entities(message.content, len(history))

            return {
                "original_text": message.content,
                "resolved_text": resolved_text,
                "pronoun_resolutions": [
                    {
                        "pronoun": r.pronoun,
                        "resolved_to": r.resolved_entity.text if r.resolved_entity else None,
                        "confidence": r.confidence
                    }
                    for r in resolutions
                ],
                "omission_completion": {
                    "original": completion.original_text,
                    "completed": completion.completed_text,
                    "confidence": completion.confidence
                },
                "entities": [
                    {
                        "text": e.text,
                        "type": e.entity_type.value,
                        "importance": e.importance
                    }
                    for e in entities
                ]
            }

    def enhance_context(
        self,
        messages: List[Message],
        query: str
    ) -> Dict[str, Any]:
        """增强上下�?""
        with self._lock:
            window_result = self.window_manager.manage_window(messages)

            query_message = Message(
                id="query",
                role="user",
                content=query,
                timestamp=datetime.now().isoformat()
            )

            processed = self.process_message(query_message, messages)

            enhanced_messages = window_result["window_messages"].copy()

            if processed["pronoun_resolutions"]:
                for resolution in processed["pronoun_resolutions"]:
                    if resolution["resolved_to"]:
                        query = query.replace(
                            resolution["pronoun"],
                            f"[{resolution['resolved_to']}]"
                        )

            if processed["omission_completion"]["confidence"] > 0.5:
                query = processed["omission_completion"]["completed"]

            return {
                "enhanced_query": query,
                "context_messages": [
                    {
                        "role": m.role,
                        "content": m.content,
                        "importance": m.importance
                    }
                    for m in enhanced_messages
                ],
                "summary": window_result["summary"].summary_text if window_result["summary"] else None,
                "entities": processed["entities"],
                "pronoun_resolutions": processed["pronoun_resolutions"],
                "window_stats": {
                    "total_tokens": window_result["total_tokens"],
                    "max_tokens": window_result["max_tokens"],
                    "utilization": window_result["utilization"],
                    "overflow_count": window_result["overflow_count"]
                }
            }

    def get_conversation_summary(
        self,
        messages: List[Message],
        use_llm: bool = False
    ) -> ConversationSummary:
        """获取对话摘要"""
        return self.summarizer.summarize(messages, use_llm=use_llm)


_context_engine: Optional[ContextUnderstandingEngine] = None
_engine_lock = threading.Lock()


def get_context_engine(
    llm_client=None,
    max_context_tokens: int = 4096
) -> ContextUnderstandingEngine:
    """获取上下文理解引擎实�?""
    global _context_engine
    with _engine_lock:
        if _context_engine is None:
            _context_engine = ContextUnderstandingEngine(llm_client, max_context_tokens)
        return _context_engine


def reset_context_engine(
    llm_client=None,
    max_context_tokens: int = 4096
) -> ContextUnderstandingEngine:
    """重置上下文理解引�?""
    global _context_engine
    with _engine_lock:
        _context_engine = ContextUnderstandingEngine(llm_client, max_context_tokens)
        return _context_engine
