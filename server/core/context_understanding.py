"""
上下文理解增强模块
功能：
1. 代词消解（指代消解）- 识别代词并解析指向实体
2. 省略补全 - 检测省略句并根据上下文补全
3. 对话摘要生成 - 长对话自动摘要
4. 长上下文窗口管理 - 滑动窗口策略和Token预算管理
"""
import json
import logging
import re
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

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
    mentions: list[str] = field(default_factory=list)
    first_mention_idx: int = 0
    last_mention_idx: int = 0
    importance: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PronounResolution:
    """代词消解结果"""
    pronoun: str
    pronoun_type: PronounType
    resolved_entity: Entity | None
    confidence: float
    position: tuple[int, int]
    context: str = ""


@dataclass
class OmissionCompletion:
    """省略补全结果"""
    original_text: str
    completed_text: str
    omitted_parts: list[str]
    confidence: float
    source_message_idx: int | None = None


@dataclass
class Message:
    """对话消息"""
    id: str
    role: str
    content: str
    timestamp: str
    token_count: int = 0
    importance: float = 0.5
    entities: list[Entity] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationSummary:
    """对话摘要"""
    summary_text: str
    key_points: list[str]
    entities_mentioned: list[str]
    topics: list[str]
    token_count: int
    message_range: tuple[int, int]
    created_at: str = ""


class PronounResolver:
    """代词消解器"""

    PERSONAL_PRONOUNS = {
        "zh": ["我", "你", "他", "她", "它", "我们", "你们", "他们", "咱们"],
        "en": ["i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them"]
    }

    DEMONSTRATIVE_PRONOUNS = {
        "zh": ["这", "那", "这个", "那个", "这些", "那些", "这里", "那里"],
        "en": ["this", "that", "these", "those", "here", "there"]
    }

    ENTITY_PATTERNS = {
        EntityType.FILE: [
            r'[a-zA-Z0-9_\-/]+\.(py|js|ts|java|go|rs|cpp|c|h|json|yaml|yml|md|txt)',
            r'文件\s*[\'"]?([a-zA-Z0-9_\-/\.]+)[\'"]?',
        ],
        EntityType.FUNCTION: [
            r'(?:函数|方法|function)\s+[a-zA-Z_][a-zA-Z0-9_]*',
            r'[a-zA-Z_][a-zA-Z0-9_]*\s*\([^)]*\)',
        ],
        EntityType.VARIABLE: [
            r'(?:变量|参数|variable)\s+[a-zA-Z_][a-zA-Z0-9_]*',
        ],
        EntityType.CODE: [
            r'```[\s\S]*?```',
            r'`[^`]+`',
        ],
    }

    def __init__(self, language: str = "zh"):
        self.language = language
        self._entity_cache: dict[str, Entity] = {}

    def resolve_all(
        self,
        text: str,
        history: list[Message]
    ) -> tuple[str, list[PronounResolution]]:
        """解析文本中所有代词"""
        resolutions = []
        resolved_text = text

        entities = self._extract_entities_from_history(history)

        pronouns = self._find_pronouns(text)

        for pronoun, pronoun_type, pos in pronouns:
            entity = self._resolve_pronoun(pronoun, pronoun_type, entities, history)

            if entity:
                resolution = PronounResolution(
                    pronoun=pronoun,
                    pronoun_type=pronoun_type,
                    resolved_entity=entity,
                    confidence=self._calculate_confidence(pronoun, entity, history),
                    position=pos,
                    context=text[max(0, pos[0]-20):min(len(text), pos[1]+20)]
                )
                resolutions.append(resolution)

                resolved_text = resolved_text[:pos[0]] + f"[{entity.text}]" + resolved_text[pos[1]:]

        return resolved_text, resolutions

    def _find_pronouns(self, text: str) -> list[tuple[str, PronounType, tuple[int, int]]]:
        """查找文本中的代词"""
        results = []

        for pronoun in self.PERSONAL_PRONOUNS.get(self.language, []):
            for match in re.finditer(re.escape(pronoun), text):
                results.append((pronoun, PronounType.PERSONAL, (match.start(), match.end())))

        for pronoun in self.DEMONSTRATIVE_PRONOUNS.get(self.language, []):
            for match in re.finditer(re.escape(pronoun), text):
                results.append((pronoun, PronounType.DEMONSTRATIVE, (match.start(), match.end())))

        results.sort(key=lambda x: x[2][0])

        return results

    def _extract_entities_from_history(self, history: list[Message]) -> list[Entity]:
        """从历史消息中提取实体"""
        entities = []

        for i, message in enumerate(history):
            for entity_type, patterns in self.ENTITY_PATTERNS.items():
                for pattern in patterns:
                    for match in re.finditer(pattern, message.content):
                        entity_text = match.group(0)

                        entity_id = f"{entity_type.value}_{entity_text}"

                        if entity_id not in self._entity_cache:
                            entity = Entity(
                                id=entity_id,
                                text=entity_text,
                                entity_type=entity_type,
                                mentions=[entity_text],
                                first_mention_idx=i,
                                last_mention_idx=i
                            )
                            self._entity_cache[entity_id] = entity
                        else:
                            self._entity_cache[entity_id].last_mention_idx = i
                            self._entity_cache[entity_id].mentions.append(entity_text)

                        entities.append(self._entity_cache[entity_id])

        return entities

    def _resolve_pronoun(
        self,
        pronoun: str,
        pronoun_type: PronounType,
        entities: list[Entity],
        history: list[Message]
    ) -> Entity | None:
        """解析单个代词"""
        if not entities:
            return None

        if pronoun_type == PronounType.DEMONSTRATIVE:
            for entity in reversed(entities):
                if entity.entity_type in [EntityType.FILE, EntityType.FUNCTION, EntityType.CODE]:
                    return entity

        if pronoun_type == PronounType.PERSONAL:
            if pronoun in ["我", "i", "me"] or pronoun in ["你", "you"]:
                return None
            else:
                for entity in reversed(entities):
                    if entity.entity_type in [EntityType.FILE, EntityType.FUNCTION, EntityType.VARIABLE]:
                        return entity

        return entities[-1] if entities else None

    def _calculate_confidence(
        self,
        pronoun: str,
        entity: Entity,
        history: list[Message]
    ) -> float:
        """计算消解置信度"""
        distance = len(history) - entity.last_mention_idx

        base_confidence = 0.7

        distance_penalty = min(0.1 * distance, 0.3)

        return max(0.3, base_confidence - distance_penalty)


class OmissionCompleter:
    """省略补全器"""

    OMISSION_PATTERNS = [
        (r'^(可以|能|要|想|会)$', '可以%s'),
        (r'^(好的|行|OK|ok)$', '好的，%s'),
        (r'^(为什么|怎么|如何)$', '%s是什么'),
        (r'^(对|是的|没错)$', '对，%s'),
        (r'^(不|不是|不对)$', '不，%s'),
    ]

    QUESTION_PATTERNS = [
        r'(?:什么|哪个|哪些|如何|怎么|为什么|谁|哪里|何时)',
        r'(?:is|are|was|were|do|does|did|what|which|how|why|who|where|when)',
    ]

    def __init__(self):
        pass

    def complete_omission(
        self,
        text: str,
        history: list[Message]
    ) -> OmissionCompletion:
        """补全省略内容"""
        original_text = text.strip()

        if not history:
            return OmissionCompletion(
                original_text=original_text,
                completed_text=original_text,
                omitted_parts=[],
                confidence=0.0
            )

        for pattern, template in self.OMISSION_PATTERNS:
            if re.match(pattern, original_text):
                last_user_message = self._get_last_user_message(history)

                if last_user_message:
                    topic = self._extract_topic(last_user_message.content)

                    if topic:
                        completed = template % topic

                        return OmissionCompletion(
                            original_text=original_text,
                            completed_text=completed,
                            omitted_parts=[topic],
                            confidence=0.8,
                            source_message_idx=history.index(last_user_message)
                        )

        if self._is_short_response(original_text):
            last_user_message = self._get_last_user_message(history)

            if last_user_message:
                is_question = any(
                    re.search(p, last_user_message.content)
                    for p in self.QUESTION_PATTERNS
                )

                if is_question:
                    return OmissionCompletion(
                        original_text=original_text,
                        completed_text=original_text,
                        omitted_parts=[last_user_message.content[:50]],
                        confidence=0.6,
                        source_message_idx=history.index(last_user_message)
                    )

        return OmissionCompletion(
            original_text=original_text,
            completed_text=original_text,
            omitted_parts=[],
            confidence=0.0
        )

    def _is_short_response(self, text: str) -> bool:
        """判断是否是短回复"""
        return len(text) <= 10

    def _get_last_user_message(self, history: list[Message]) -> Message | None:
        """获取最后一条用户消息"""
        for message in reversed(history):
            if message.role == "user":
                return message
        return None

    def _extract_topic(self, text: str) -> str | None:
        """提取主题"""
        patterns = [
            r'(?:创建|修改|删除|查看|打开)\s*([a-zA-Z0-9_\-/\.]+)',
            r'(?:文件|函数|变量)\s*[:：]?\s*([a-zA-Z0-9_\-/\.]+)',
            r'([a-zA-Z0-9_\-/]+\.(py|js|ts|java|go))',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)

        return None


class ConversationSummarizer:
    """对话摘要生成器"""

    KEYWORD_WEIGHTS = {
        "问题": 2.0,
        "解决": 1.5,
        "完成": 1.5,
        "创建": 1.3,
        "修改": 1.3,
        "删除": 1.3,
        "错误": 1.4,
        "失败": 1.4,
        "成功": 1.2,
    }

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    def summarize(
        self,
        messages: list[Message],
        max_length: int = 500
    ) -> ConversationSummary:
        """生成对话摘要"""
        if not messages:
            return ConversationSummary(
                summary_text="",
                key_points=[],
                entities_mentioned=[],
                topics=[],
                token_count=0,
                message_range=(0, 0)
            )

        if self.llm_client:
            return self._llm_summarize(messages, max_length)
        else:
            return self._extractive_summarize(messages, max_length)

    def _llm_summarize(
        self,
        messages: list[Message],
        max_length: int
    ) -> ConversationSummary:
        """使用 LLM 生成摘要"""
        conversation_text = "\n".join([
            f"{m.role}: {m.content}"
            for m in messages
        ])

        prompt = f"""请总结以下对话内容，提取关键信息：

{conversation_text}

请以 JSON 格式返回：
{{
    "summary": "摘要内容",
    "key_points": ["关键点1", "关键点2"],
    "entities": ["提到的实体"],
    "topics": ["主题1", "主题2"]
}}
"""

        try:
            response = self.llm_client.generate(prompt)
            result = json.loads(response)

            return ConversationSummary(
                summary_text=result.get("summary", "")[:max_length],
                key_points=result.get("key_points", []),
                entities_mentioned=result.get("entities", []),
                topics=result.get("topics", []),
                token_count=len(result.get("summary", "").split()),
                message_range=(0, len(messages) - 1)
            )
        except Exception as e:
            logger.warning(f"LLM 摘要生成失败：{e}")
            return self._extractive_summarize(messages, max_length)

    def _extractive_summarize(
        self,
        messages: list[Message],
        max_length: int
    ) -> ConversationSummary:
        """抽取式摘要"""
        key_points = []
        entities = set()
        topics = set()

        for message in messages:
            importance = self._calculate_importance(message)

            if importance > 0.5:
                sentences = re.split(r'[。！？.!?]', message.content)
                for sentence in sentences:
                    if sentence.strip() and len(sentence) > 10:
                        key_points.append(sentence.strip()[:100])

            for pattern in [r'[a-zA-Z0-9_\-/]+\.(py|js|ts|java)', r'[a-zA-Z_][a-zA-Z0-9_]*']:
                for match in re.finditer(pattern, message.content):
                    entities.add(match.group(0))

        summary_text = "。".join(key_points[:5])[:max_length]

        return ConversationSummary(
            summary_text=summary_text,
            key_points=key_points[:10],
            entities_mentioned=list(entities)[:20],
            topics=list(topics)[:10],
            token_count=len(summary_text.split()),
            message_range=(0, len(messages) - 1)
        )

    def _calculate_importance(self, message: Message) -> float:
        """计算消息重要性"""
        importance = message.importance

        for keyword, weight in self.KEYWORD_WEIGHTS.items():
            if keyword in message.content:
                importance += weight * 0.1

        return min(1.0, importance)


class ContextWindowManager:
    """上下文窗口管理器"""

    def __init__(
        self,
        max_tokens: int = 4096,
        reserved_tokens: int = 512
    ):
        self.max_tokens = max_tokens
        self.reserved_tokens = reserved_tokens
        self.summarizer = ConversationSummarizer()

    def manage_window(
        self,
        messages: list[Message],
        keep_recent: int = 3
    ) -> dict[str, Any]:
        """管理上下文窗口"""
        if not messages:
            return {
                "window_messages": [],
                "total_tokens": 0,
                "max_tokens": self.max_tokens,
                "utilization": 0.0,
                "overflow_count": 0,
                "summary": None
            }

        total_tokens = sum(m.token_count for m in messages)

        available_tokens = self.max_tokens - self.reserved_tokens

        if total_tokens <= available_tokens:
            return {
                "window_messages": messages,
                "total_tokens": total_tokens,
                "max_tokens": self.max_tokens,
                "utilization": total_tokens / self.max_tokens,
                "overflow_count": 0,
                "summary": None
            }

        recent_messages = messages[-keep_recent:] if len(messages) > keep_recent else messages
        older_messages = messages[:-keep_recent] if len(messages) > keep_recent else []

        summary = None
        if older_messages:
            summary = self.summarizer.summarize(older_messages)

        window_messages = recent_messages
        window_tokens = sum(m.token_count for m in window_messages)

        if summary:
            summary_tokens = summary.token_count
            window_tokens += summary_tokens

        overflow_count = len(older_messages)

        return {
            "window_messages": window_messages,
            "total_tokens": window_tokens,
            "max_tokens": self.max_tokens,
            "utilization": window_tokens / self.max_tokens,
            "overflow_count": overflow_count,
            "summary": summary
        }


class ContextUnderstandingEngine:
    """上下文理解引擎"""

    def __init__(
        self,
        max_context_tokens: int = 4096,
        language: str = "zh",
        llm_client=None
    ):
        self.pronoun_resolver = PronounResolver(language)
        self.omission_completer = OmissionCompleter()
        self.summarizer = ConversationSummarizer(llm_client)
        self.window_manager = ContextWindowManager(max_context_tokens)
        self.llm_client = llm_client

    def process_message(
        self,
        current_message: Message,
        history: list[Message]
    ) -> dict[str, Any]:
        """处理消息，返回增强后的内容"""
        resolved_text, pronoun_resolutions = self.pronoun_resolver.resolve_all(
            current_message.content, history
        )

        completion = self.omission_completer.complete_omission(
            current_message.content, history
        )

        entities = self._extract_entities(current_message.content)

        return {
            "original_text": current_message.content,
            "resolved_text": resolved_text,
            "pronoun_resolutions": [
                {
                    "pronoun": r.pronoun,
                    "type": r.pronoun_type.value,
                    "resolved_to": r.resolved_entity.text if r.resolved_entity else None,
                    "confidence": r.confidence
                }
                for r in pronoun_resolutions
            ],
            "omission_completion": {
                "original": completion.original_text,
                "completed": completion.completed_text,
                "confidence": completion.confidence
            },
            "entities": [
                {
                    "text": e.text,
                    "type": e.entity_type.value
                }
                for e in entities
            ]
        }

    def enhance_context(
        self,
        messages: list[Message],
        query: str
    ) -> dict[str, Any]:
        """增强上下文"""
        window_result = self.window_manager.manage_window(messages)

        context_messages = window_result["window_messages"]

        resolved_query, pronoun_resolutions = self.pronoun_resolver.resolve_all(
            query, messages
        )

        completion = self.omission_completer.complete_omission(query, messages)

        entities = []
        for msg in context_messages:
            entities.extend(self._extract_entities(msg.content))

        summary = window_result.get("summary")

        return {
            "enhanced_query": completion.completed_text if completion.confidence > 0.5 else resolved_query,
            "context_messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "importance": m.importance
                }
                for m in context_messages
            ],
            "summary": summary.summary_text if summary else None,
            "entities": [
                {"text": e.text, "type": e.entity_type.value}
                for e in entities[:20]
            ],
            "pronoun_resolutions": [
                {
                    "pronoun": r.pronoun,
                    "resolved_to": r.resolved_entity.text if r.resolved_entity else None
                }
                for r in pronoun_resolutions
            ],
            "window_stats": {
                "total_tokens": window_result["total_tokens"],
                "max_tokens": window_result["max_tokens"],
                "utilization": window_result["utilization"]
            }
        }

    def get_conversation_summary(
        self,
        messages: list[Message],
        use_llm: bool = False
    ) -> ConversationSummary:
        """获取对话摘要"""
        if use_llm and self.llm_client:
            return self.summarizer.summarize(messages)
        else:
            return self.summarizer._extractive_summarize(messages, 500)

    def _extract_entities(self, text: str) -> list[Entity]:
        """从文本中提取实体"""
        entities = []

        for entity_type, patterns in PronounResolver.ENTITY_PATTERNS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text):
                    entity = Entity(
                        id=f"{entity_type.value}_{match.group(0)}",
                        text=match.group(0),
                        entity_type=entity_type
                    )
                    entities.append(entity)

        return entities


_engine_instance: ContextUnderstandingEngine | None = None
_engine_lock = threading.Lock()


def get_context_engine(
    max_context_tokens: int = 4096,
    language: str = "zh",
    llm_client=None
) -> ContextUnderstandingEngine:
    """获取上下文理解引擎实例"""
    global _engine_instance

    with _engine_lock:
        if _engine_instance is None:
            _engine_instance = ContextUnderstandingEngine(
                max_context_tokens=max_context_tokens,
                language=language,
                llm_client=llm_client
            )
        return _engine_instance


def reset_context_engine(
    max_context_tokens: int = 4096,
    language: str = "zh",
    llm_client=None
) -> ContextUnderstandingEngine:
    """重置上下文理解引擎"""
    global _engine_instance

    with _engine_lock:
        _engine_instance = ContextUnderstandingEngine(
            max_context_tokens=max_context_tokens,
            language=language,
            llm_client=llm_client
        )
        return _engine_instance
