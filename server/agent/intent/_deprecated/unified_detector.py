"""
统一意图检测器 - 升级版架构
整合规则匹配、语义匹配、上下文感知、置信度评估
支持多意图检测、模糊意图识别、实时性能监控
"""
import asyncio
import logging
import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class DetectionMethod(str, Enum):
    """检测方法"""
    RULE = "rule"
    SEMANTIC = "semantic"
    FUZZY = "semantic"
    LLM = "llm"
    CONTEXT = "context"
    HYBRID = "hybrid"


class ConfidenceLevel(str, Enum):
    """置信度等级"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class IntentCategory(str, Enum):
    """意图分类"""
    FILE_OPERATION = "file_operation"
    APP_CONTROL = "app_control"
    BROWSER_OPERATION = "browser_operation"
    CUA_OPERATION = "cua_operation"
    SYSTEM_OPERATION = "system_operation"
    INFORMATION_QUERY = "information_query"
    CONVERSATION = "conversation"
    UNKNOWN = "unknown"


@dataclass
class IntentResult:
    """意图检测结果"""
    detected: bool
    intent_type: str = ""
    action: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    confidence: float = 0.0
    confidence_level: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    method: DetectionMethod = DetectionMethod.RULE
    need_confirm: bool = False
    alternatives: list[tuple[str, float]] = field(default_factory=list)
    clarification: dict[str, Any] | None = None
    category: IntentCategory = IntentCategory.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected": self.detected,
            "intent_type": self.intent_type,
            "action": self.action,
            "params": self.params,
            "description": self.description,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level.value,
            "method": self.method.value,
            "need_confirm": self.need_confirm,
            "alternatives": self.alternatives,
            "clarification": self.clarification,
            "category": self.category.value
        }


@dataclass
class MultiIntentResult:
    """多意图检测结果"""
    detected: bool
    intents: list[IntentResult] = field(default_factory=list)
    has_ambiguity: bool = False
    clarification_dialog: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected": self.detected,
            "intents": [i.to_dict() for i in self.intents],
            "has_ambiguity": self.has_ambiguity,
            "clarification_dialog": self.clarification_dialog
        }


@dataclass
class DetectionMetrics:
    """检测性能指标"""
    total_requests: int = 0
    successful_detections: int = 0
    failed_detections: int = 0
    average_response_time_ms: float = 0.0
    total_response_time_ms: float = 0.0
    method_usage: dict[str, int] = field(default_factory=dict)
    intent_distribution: dict[str, int] = field(default_factory=dict)
    confidence_distribution: dict[str, int] = field(default_factory=lambda: {"high": 0, "medium": 0, "low": 0})
    last_reset: datetime = field(default_factory=datetime.now)

    def record_detection(self, method: DetectionMethod, intent_type: str, confidence: float, response_time_ms: float):
        """记录检测结果"""
        self.total_requests += 1
        self.successful_detections += 1
        self.total_response_time_ms += response_time_ms
        self.average_response_time_ms = self.total_response_time_ms / self.total_requests

        method_key = method.value if isinstance(method, DetectionMethod) else str(method)
        self.method_usage[method_key] = self.method_usage.get(method_key, 0) + 1
        self.intent_distribution[intent_type] = self.intent_distribution.get(intent_type, 0) + 1

        if confidence >= 0.9:
            self.confidence_distribution["high"] += 1
        elif confidence >= 0.7:
            self.confidence_distribution["medium"] += 1
        else:
            self.confidence_distribution["low"] += 1

    def record_failure(self, response_time_ms: float):
        """记录失败检测"""
        self.total_requests += 1
        self.failed_detections += 1
        self.total_response_time_ms += response_time_ms
        self.average_response_time_ms = self.total_response_time_ms / self.total_requests

    def get_report(self) -> dict[str, Any]:
        """获取性能报告"""
        success_rate = self.successful_detections / self.total_requests if self.total_requests > 0 else 0
        return {
            "total_requests": self.total_requests,
            "successful_detections": self.successful_detections,
            "failed_detections": self.failed_detections,
            "success_rate": success_rate,
            "average_response_time_ms": self.average_response_time_ms,
            "method_usage": self.method_usage,
            "intent_distribution": self.intent_distribution,
            "confidence_distribution": self.confidence_distribution,
            "uptime_seconds": (datetime.now() - self.last_reset).total_seconds()
        }

    def reset(self):
        """重置指标"""
        self.total_requests = 0
        self.successful_detections = 0
        self.failed_detections = 0
        self.total_response_time_ms = 0
        self.average_response_time_ms = 0
        self.method_usage.clear()
        self.intent_distribution.clear()
        self.confidence_distribution = {"high": 0, "medium": 0, "low": 0}
        self.last_reset = datetime.now()


class ConversationContext:
    """对话上下文"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.recent_messages: list[dict[str, Any]] = []
        self.recent_intents: list[str] = []
        self.mentioned_entities: dict[str, list[str]] = defaultdict(list)
        self.user_preferences: dict[str, Any] = {}
        self.current_task: str | None = None
        self.expecting_action: str | None = None
        self.last_updated = datetime.now()
        self.last_generated_content: str | None = None
        self.last_generated_type: str | None = None

    def add_message(self, role: str, content: str, intent: str | None = None, entities: dict[str, Any] | None = None):
        """添加消息"""
        self.recent_messages.append({
            "role": role,
            "content": content,
            "intent": intent,
            "entities": entities or {},
            "timestamp": datetime.now().isoformat()
        })

        if len(self.recent_messages) > 20:
            self.recent_messages = self.recent_messages[-20:]

        if intent:
            self.recent_intents.append(intent)
            if len(self.recent_intents) > 10:
                self.recent_intents = self.recent_intents[-10:]

        if entities:
            for key, value in entities.items():
                if isinstance(value, str):
                    self.mentioned_entities[key].append(value)
                    if len(self.mentioned_entities[key]) > 10:
                        self.mentioned_entities[key] = self.mentioned_entities[key][-10:]

        if role == "assistant" and content:
            self._extract_generated_content(content)

        self.last_updated = datetime.now()

    def _extract_generated_content(self, content: str):
        """从 AI 响应中提取生成的内容"""
        code_blocks = re.findall(r'```[\w]*\n(.*?)```', content, re.DOTALL)
        if code_blocks:
            self.last_generated_content = code_blocks[-1].strip()
            lang_match = re.search(r'```(\w+)', content)
            self.last_generated_type = lang_match.group(1) if lang_match else "code"
            self.user_preferences["last_generated_content"] = self.last_generated_content
            self.user_preferences["last_generated_type"] = self.last_generated_type
            return

        if len(content) > 50 and ("代码" in content or "函数" in content or "实现" in content or "示例" in content):
            lines = content.split('\n')
            code_like_lines = [l for l in lines if l.strip().startswith(('def ', 'class ', 'import ', 'function ', 'const ', 'let ', 'var '))]
            if code_like_lines:
                self.last_generated_content = '\n'.join(code_like_lines)
                self.last_generated_type = "code"
                self.user_preferences["last_generated_content"] = self.last_generated_content

    def set_generated_content(self, content: str, content_type: str = "text"):
        """手动设置生成的内容"""
        self.last_generated_content = content
        self.last_generated_type = content_type
        self.user_preferences["last_generated_content"] = content
        self.user_preferences["last_generated_type"] = content_type

    def resolve_reference(self, reference: str) -> str | None:
        """解析代词引用"""
        reference_map = {
            "它": "file_path",
            "这个": "file_path",
            "那个": "file_path",
            "这个文件": "file_path",
            "那个文件": "file_path",
            "这个目录": "directory",
            "那个目录": "directory",
            "这个应用": "app_name",
            "那个应用": "app_name",
            "这个网址": "url",
            "那个网址": "url",
            "刚才": "intent",
            "继续": "intent",
            "重复": "intent"
        }

        entity_type = reference_map.get(reference)
        if entity_type:
            if entity_type == "intent":
                if self.recent_intents:
                    return self.recent_intents[-1]
            elif entity_type in self.mentioned_entities:
                entities = self.mentioned_entities[entity_type]
                if entities:
                    if reference in ["那个", "刚才"]:
                        return entities[-2] if len(entities) > 1 else entities[-1]
                    return entities[-1]

        if reference in ["它", "这个", "那个"]:
            for entity_type in ["file_path", "directory", "app_name", "url"]:
                if entity_type in self.mentioned_entities and self.mentioned_entities[entity_type]:
                    return self.mentioned_entities[entity_type][-1]

        if reference in ["继续", "重复", "刚才"]:
            if self.recent_intents:
                return self.recent_intents[-1]

        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "recent_messages": self.recent_messages[-5:],
            "recent_intents": self.recent_intents[-5:],
            "mentioned_entities": dict(self.mentioned_entities),
            "current_task": self.current_task,
            "expecting_action": self.expecting_action
        }


class UnifiedIntentDetector:
    """
    统一意图检测器 - 升级版

    支持功能：
    - 多层检测架构（规则->语义->模糊->上下文->LLM）
    - 多意图并行检测
    - 置信度动态评估
    - 实时性能监控
    - 会话上下文管理
    - 智能错误处理
    - 插件式扩展
    """

    CONFIDENCE_HIGH = 0.85
    CONFIDENCE_MEDIUM = 0.65
    CONFIDENCE_LOW = 0.45

    MAX_CONTEXT_HISTORY = 20
    MAX_ALTERNATIVES = 3

    def __init__(
        self,
        llm_client=None,
        use_semantic: bool = True,
        use_context: bool = True,
        use_llm_fallback: bool = True,
        use_bert: bool = True,
        enable_metrics: bool = True,
        session_store=None
    ):
        self.llm_client = llm_client
        self.use_semantic = use_semantic
        self.use_context = use_context
        self.use_llm_fallback = use_llm_fallback
        self.use_bert = use_bert
        self.enable_metrics = enable_metrics

        self.metrics = DetectionMetrics() if enable_metrics else None
        self.sessions: dict[str, ConversationContext] = {}
        self.sessions_lock = threading.Lock()

        self.session_store = session_store

        self.rule_patterns: list[dict[str, Any]] = []
        self.semantic_matcher = None
        self.fuzzy_matcher = None
        self.context_aware = None
        self.llm_detector = None
        self.error_handler = None
        self.bert_classifier = None

        self._components_initialized = False
        self._intent_definitions: dict[str, dict[str, Any]] = {}

        self._init_components()
        self._init_patterns()
        self._init_intent_definitions()

    def _init_components(self):
        """初始化组件"""
        try:
            from .confidence import ConfidenceEvaluator
            from .context_aware import ContextAwareDetector, ContextManager
            from .semantic_matcher import FuzzyMatcher, SemanticMatcher

            self.semantic_matcher = SemanticMatcher(use_embedding=self.use_semantic)
            self.fuzzy_matcher = FuzzyMatcher()
            self.context_manager = ContextManager()
            self.context_aware = ContextAwareDetector(self.context_manager)
            self.confidence_evaluator = ConfidenceEvaluator()

            if self.use_bert:
                try:
                    from .bert_classifier import get_bert_classifier
                    self.bert_classifier = get_bert_classifier()
                    if self.bert_classifier.is_loaded():
                        logger.info("BERT 意图分类器加载成功")
                    else:
                        logger.warning("BERT 意图分类器未加载，将使用规则匹配")
                        self.bert_classifier = None
                except Exception as e:
                    logger.warning(f"BERT 分类器加载失败: {e}")
                    self.bert_classifier = None

            self._components_initialized = True
            logger.info("统一意图检测器组件初始化完成")
        except Exception as e:
            logger.warning(f"部分组件初始化失败: {e}")
            self._components_initialized = False

    def _detect_composite_request(self, message: str) -> dict[str, Any] | None:
        """
        检测复合请求 - 包含内容生成+保存的请求

        例如: "帮我写一个我的妈妈记叙文保存"
        应该返回: {"type": "composite", "needs_content_generation": True, "content_type": "记叙文", "topic": "我的妈妈", "save": True}
        """
        import re

        # 检测内容生成+保存的复合请求
        content_gen_patterns = [
            # 写/生成/创作 + 内容类型 + 主题 + 保存
            r"(?:帮我)?(?:写|生成|创作|编写)(?:一个|一篇)?(.+?)(?:记叙文|作文|文章|故事|诗歌|散文)(.+?)保存",
            r"(?:帮我)?(?:写|生成|创作|编写)(?:一个|一篇)?(.+?)(?:记叙文|作文|文章|故事|诗歌|散文).*(?:保存|存)",
            # 保存 + 内容描述
            r"保存(?:一个|一篇)?(.+?)(?:记叙文|作文|文章|故事|诗歌|散文)",
        ]

        for pattern in content_gen_patterns:
            match = re.search(pattern, message)
            if match:
                # 提取主题
                topic = ""
                content_type = "文章"

                # 尝试提取主题和内容类型
                if "记叙文" in message:
                    content_type = "记叙文"
                elif "作文" in message:
                    content_type = "作文"
                elif "故事" in message:
                    content_type = "故事"
                elif "诗歌" in message:
                    content_type = "诗歌"

                # 提取主题关键词
                topic_patterns = [
                    r"关于(.+?)的",
                    r"我的(.+?)(?:记叙文|作文|文章|故事)",
                    r"写(.+?)(?:记叙文|作文|文章|故事)",
                ]
                for tp in topic_patterns:
                    tm = re.search(tp, message)
                    if tm:
                        topic = tm.group(1).strip()
                        break

                return {
                    "type": "composite",
                    "needs_content_generation": True,
                    "content_type": content_type,
                    "topic": topic or "未指定主题",
                    "save": True,
                    "original_message": message
                }

        return None

    CONVERSATION_PATTERNS = [
        r"^(你好|您好|hi|hello|hey|嗨|哈喽|早上好|下午好|晚上好)[\s!！.。]*$",
        r"^(谢谢|感谢|多谢|thanks|thank you)[\s!！.。]*$",
        r"^(再见|拜拜|bye|goodbye|下次见)[\s!！.。]*$",
        r"^(怎么样|如何|什么情况|怎么了|什么事)[\?？]*$",
        r"^(好的|明白|收到|ok|okay|嗯|哦)[\s!！.。]*$",
        r"^(是|对|没错|是的|right)[\s!！.。]*$",
        r"^(不是|不对|错|no|不对)[\s!！.。]*$",
        r"^(请|麻烦|劳驾|能不能|可以吗|行吗)",
        r"^(我想问|请问|问一下|请教)",
        r"^(帮我|帮我看看|帮我查|帮我找)",
        r"^(你是谁|你叫什么|你的名字|自我介绍)",
        r"^(你能做什么|你会什么|你的功能|你能帮我)",
        r"^(今天天气|现在几点|什么时间)",
        r"^(哈哈|呵呵|嘻嘻|嘿嘿|haha|lol)",
    ]

    def _init_patterns(self):
        """初始化规则模式"""
        self.rule_patterns = [
            {
                "pattern": r"^(你好|您好|hi|hello|hey|嗨|哈喽|早上好|下午好|晚上好)[\s!！.。]*$",
                "action": "conversation",
                "params": lambda m: {},
                "description": "问候",
                "keywords": ["你好", "hello", "hi"],
                "priority": 0,
                "category": IntentCategory.CONVERSATION
            },
            {
                "pattern": r"^(谢谢|感谢|多谢|thanks|thank you)[\s!！.。]*$",
                "action": "conversation",
                "params": lambda m: {},
                "description": "感谢",
                "keywords": ["谢谢", "thanks"],
                "priority": 0,
                "category": IntentCategory.CONVERSATION
            },
            {
                "pattern": r"^(再见|拜拜|bye|goodbye|下次见)[\s!！.。]*$",
                "action": "conversation",
                "params": lambda m: {},
                "description": "告别",
                "keywords": ["再见", "bye"],
                "priority": 0,
                "category": IntentCategory.CONVERSATION
            },
            {
                "pattern": r"^(你是谁|你叫什么|你的名字|自我介绍)",
                "action": "conversation",
                "params": lambda m: {},
                "description": "自我介绍询问",
                "keywords": ["你是谁", "名字"],
                "priority": 0,
                "category": IntentCategory.CONVERSATION
            },
            {
                "pattern": r"^(你能做什么|你会什么|你的功能|你能帮我)",
                "action": "conversation",
                "params": lambda m: {},
                "description": "能力询问",
                "keywords": ["功能", "能力"],
                "priority": 0,
                "category": IntentCategory.CONVERSATION
            },
            {
                "pattern": r"^(我想问|请问|问一下|请教)",
                "action": "conversation",
                "params": lambda m: {},
                "description": "提问",
                "keywords": ["问", "请问"],
                "priority": 0,
                "category": IntentCategory.CONVERSATION
            },
            {
                "pattern": r"^(帮我|帮我看看|帮我查|帮我找)(?!.*(?:文件|目录|应用|软件|程序))",
                "action": "conversation",
                "params": lambda m: {},
                "description": "请求帮助",
                "keywords": ["帮我"],
                "priority": 0,
                "category": IntentCategory.CONVERSATION
            },
            {
                "pattern": r"创建(?:一个)?(?:新)?(?:文件)?\s*([\w\-./]+\.\w+)",
                "action": "file_create",
                "params": lambda m: {"file_path": m.group(1), "content": ""},
                "description": "创建文件",
                "keywords": ["创建", "新建", "生成", "建立"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION
            },
            {
                "pattern": r"新建(?:一个)?(?:新)?(?:文件)?\s*([\w\-./]+\.\w+)",
                "action": "file_create",
                "params": lambda m: {"file_path": m.group(1), "content": ""},
                "description": "新建文件",
                "keywords": ["新建"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION
            },
            {
                "pattern": r"读取\s*([\w\-./]+\.\w+)",
                "action": "file_read",
                "params": lambda m: {"file_path": m.group(1)},
                "description": "读取文件",
                "keywords": ["读取", "查看", "打开", "显示"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION
            },
            {
                "pattern": r"打开\s*([\w\-./]+\.\w+)",
                "action": "file_read",
                "params": lambda m: {"file_path": m.group(1)},
                "description": "打开文件",
                "keywords": ["打开"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION
            },
            {
                "pattern": r"查看\s*([\w\-./]+\.\w+)",
                "action": "file_read",
                "params": lambda m: {"file_path": m.group(1)},
                "description": "查看文件",
                "keywords": ["查看"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION
            },
            {
                "pattern": r"(?:把|将)\s*([\w\-./]+\.\w+)\s*(?:改成|修改成|内容改为|内容改成|改成)\s*[\"「『]([^」」\']*)[」』\"]",
                "action": "file_write",
                "params": lambda m: {"file_path": m.group(1), "content": m.group(2)},
                "description": "修改文件内容",
                "keywords": ["改成", "修改", "内容"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION
            },
            {
                "pattern": r"(?:把|将)\s*([\w\-./]+\.\w+)\s*(?:改成|修改成|内容改为|内容改成)\s*(.+)",
                "action": "file_write",
                "params": lambda m: {"file_path": m.group(1), "content": m.group(2)},
                "description": "修改文件内容",
                "keywords": ["改成", "修改", "内容"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION
            },
            {
                "pattern": r"(?:在|向)\s*([\w\-./]+\.\w+)\s*(?:中|里)?(?:写入|添加|追加)\s*[\"「『]([^」」\']*)[」』\"]",
                "action": "file_write",
                "params": lambda m: {"file_path": m.group(1), "content": m.group(2)},
                "description": "写入文件",
                "keywords": ["写入", "添加", "追加"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION
            },
            {
                "pattern": r"写入\s*([\w\-./]+)\s+(.+)",
                "action": "file_write",
                "params": lambda m: {"file_path": m.group(1), "content": m.group(2)},
                "description": "写入文件",
                "keywords": ["写入", "修改", "更新"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION
            },
            {
                "pattern": r"(?:保存|存储)\s*[\"「『]([^」」\']*)[」』\"]\s*(?:到|至)\s*([\w\-./]+\.\w+)",
                "action": "file_write",
                "params": lambda m: {"file_path": m.group(2), "content": m.group(1)},
                "description": "保存内容到文件",
                "keywords": ["保存", "存储"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION
            },
            {
                "pattern": r"(?:修改|编辑)\s*([\w\-./]+\.\w+)\s*(?:的内容)?(?:为|改成)?\s*(.+)",
                "action": "file_write",
                "params": lambda m: {"file_path": m.group(1), "content": m.group(2)},
                "description": "修改文件内容",
                "keywords": ["修改", "编辑"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION
            },
            {
                "pattern": r"删除\s*([\w\-./]+\.\w+)",
                "action": "file_delete",
                "params": lambda m: {"file_path": m.group(1)},
                "description": "删除文件",
                "keywords": ["删除", "移除", "清除"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION,
                "need_confirm": True
            },
            {
                "pattern": r"删除\s*(?:所有|全部)?\s*\*\.(\w+)",
                "action": "file_batch_delete",
                "params": lambda m: {"pattern": f"*.{m.group(1)}", "batch": True},
                "description": "批量删除文件",
                "keywords": ["删除", "所有", "全部"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION,
                "need_confirm": True
            },
            {
                "pattern": r"批量删除\s*(\w+)\s*文件",
                "action": "file_batch_delete",
                "params": lambda m: {"pattern": f"*.{m.group(1)}", "batch": True},
                "description": "批量删除文件",
                "keywords": ["批量删除", "删除"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION,
                "need_confirm": True
            },
            {
                "pattern": r"删除所有\s*(\w+)\s*文件",
                "action": "file_batch_delete",
                "params": lambda m: {"pattern": f"*.{m.group(1)}", "batch": True},
                "description": "批量删除文件",
                "keywords": ["删除所有"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION,
                "need_confirm": True
            },
            {
                "pattern": r"清理\s*(\w+)\s*文件",
                "action": "file_batch_delete",
                "params": lambda m: {"pattern": f"*.{m.group(1)}", "batch": True},
                "description": "清理文件",
                "keywords": ["清理"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION,
                "need_confirm": True
            },
            {
                "pattern": r"批量重命名\s*(\w+)\s*(?:为|到)\s*(\w+)",
                "action": "file_batch_rename",
                "params": lambda m: {"from_ext": m.group(1), "to_ext": m.group(2), "batch": True},
                "description": "批量重命名文件",
                "keywords": ["批量重命名"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION,
                "need_confirm": True
            },
            {
                "pattern": r"(?:复制|拷贝)\s*([\w\-./]+\.\w+)\s*(?:到|至)\s*([\w\-./]+)",
                "action": "file_copy",
                "params": lambda m: {"source": m.group(1), "destination": m.group(2)},
                "description": "复制文件",
                "keywords": ["复制", "拷贝"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION
            },
            {
                "pattern": r"(?:移动|转移)\s*([\w\-./]+\.\w+)\s*(?:到|至)\s*([\w\-./]+)",
                "action": "file_move",
                "params": lambda m: {"source": m.group(1), "destination": m.group(2)},
                "description": "移动文件",
                "keywords": ["移动", "转移"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION
            },
            {
                "pattern": r"(?:重命名|改名)\s*([\w\-./]+\.\w+)\s*(?:为|改成)?\s*([\w\-./]+\.\w+)",
                "action": "file_rename",
                "params": lambda m: {"old_name": m.group(1), "new_name": m.group(2)},
                "description": "重命名文件",
                "keywords": ["重命名", "改名"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION
            },
            {
                "pattern": r"(?:搜索|查找|寻找)\s*(?:文件)?\s*([\w\-*?]+)",
                "action": "file_search",
                "params": lambda m: {"pattern": m.group(1)},
                "description": "搜索文件",
                "keywords": ["搜索", "查找", "寻找"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION
            },
            {
                "pattern": r"列出\s*(\S*)\s*(?:的)?文件",
                "action": "file_list",
                "params": lambda m: {"directory": m.group(1) or "."},
                "description": "列出文件",
                "keywords": ["列出", "显示", "查看", "ls"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION
            },
            {
                "pattern": r"(?:列出|显示|查看)\s*当前目录",
                "action": "file_list",
                "params": lambda m: {"directory": "."},
                "description": "列出当前目录",
                "keywords": ["当前目录"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION
            },
            {
                "pattern": r"(?:列出|显示|查看)\s*([\w\-./]+)\s*(?:目录|文件夹)?",
                "action": "file_list",
                "params": lambda m: {"directory": m.group(1)},
                "description": "列出目录内容",
                "keywords": ["列出", "目录"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION
            },
            {
                "pattern": r"ls\s*(\S*)",
                "action": "file_list",
                "params": lambda m: {"directory": m.group(1) or "."},
                "description": "列出目录",
                "keywords": ["ls"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION
            },
            {
                "pattern": r"dir\s*(\S*)",
                "action": "file_list",
                "params": lambda m: {"directory": m.group(1) or "."},
                "description": "列出目录",
                "keywords": ["dir"],
                "priority": 1,
                "category": IntentCategory.FILE_OPERATION
            },
            {
                "pattern": r"打开\s*(VS\s*Code|Visual\s*Studio\s*Code)",
                "action": "app_open",
                "params": lambda m: {"app_name": "vscode"},
                "description": "打开 VS Code",
                "keywords": ["VS Code", "VSCode"],
                "priority": 1,
                "category": IntentCategory.APP_CONTROL
            },
            {
                "pattern": r"打开\s*(记事本|Notepad)",
                "action": "app_open",
                "params": lambda m: {"app_name": "notepad"},
                "description": "打开记事本",
                "keywords": ["记事本", "Notepad"],
                "priority": 1,
                "category": IntentCategory.APP_CONTROL
            },
            {
                "pattern": r"打开\s*(Chrome|谷歌浏览器)",
                "action": "app_open",
                "params": lambda m: {"app_name": "chrome"},
                "description": "打开 Chrome",
                "keywords": ["Chrome", "谷歌"],
                "priority": 1,
                "category": IntentCategory.APP_CONTROL
            },
            {
                "pattern": r"打开\s*(Edge|edge)",
                "action": "app_open",
                "params": lambda m: {"app_name": "edge"},
                "description": "打开 Edge",
                "keywords": ["Edge"],
                "priority": 1,
                "category": IntentCategory.APP_CONTROL
            },
            {
                "pattern": r"打开\s*(微信|WeChat)",
                "action": "app_open",
                "params": lambda m: {"app_name": "wechat"},
                "description": "打开微信",
                "keywords": ["微信", "WeChat"],
                "priority": 1,
                "category": IntentCategory.APP_CONTROL
            },
            {
                "pattern": r"打开\s*(钉钉|DingTalk)",
                "action": "app_open",
                "params": lambda m: {"app_name": "dingtalk"},
                "description": "打开钉钉",
                "keywords": ["钉钉", "DingTalk"],
                "priority": 1,
                "category": IntentCategory.APP_CONTROL
            },
            {
                "pattern": r"打开\s*(QQ|腾讯QQ)",
                "action": "app_open",
                "params": lambda m: {"app_name": "qq"},
                "description": "打开 QQ",
                "keywords": ["QQ", "腾讯QQ"],
                "priority": 1,
                "category": IntentCategory.APP_CONTROL
            },
            {
                "pattern": r"打开\s*([a-zA-Z][a-zA-Z0-9\s]{1,})(?:应用|软件|程序)?$",
                "action": "app_open",
                "params": lambda m: {"app_name": m.group(1).lower().replace(" ", "")},
                "description": "打开应用",
                "keywords": ["打开", "启动", "运行"],
                "priority": 2,
                "category": IntentCategory.APP_CONTROL
            },
            {
                "pattern": r"打开\s*([\u4e00-\u9fa5]{2,})(?:应用|软件|程序)?$",
                "action": "app_open",
                "params": lambda m: {"app_name": m.group(1).lower().replace(" ", "")},
                "description": "打开应用",
                "keywords": ["打开", "启动", "运行"],
                "priority": 2,
                "category": IntentCategory.APP_CONTROL
            },
            {
                "pattern": r"关闭\s+(微信|WeChat)",
                "action": "app_close",
                "params": lambda m: {"app_name": "wechat"},
                "description": "关闭微信",
                "keywords": ["关闭", "微信"],
                "priority": 1,
                "category": IntentCategory.APP_CONTROL
            },
            {
                "pattern": r"(https?://\S+)",
                "action": "url_open",
                "params": lambda m: {"url": m.group(1)},
                "description": "打开网址",
                "keywords": ["http", "https"],
                "priority": 0,
                "category": IntentCategory.BROWSER_OPERATION
            },
            {
                "pattern": r"(?:访问|打开)\s*(?:网址|网站|链接)?\s*(https?://\S+)",
                "action": "url_open",
                "params": lambda m: {"url": m.group(1)},
                "description": "打开网址",
                "keywords": ["访问", "网址"],
                "priority": 1,
                "category": IntentCategory.BROWSER_OPERATION
            },
            {
                "pattern": r"截图$",
                "action": "screenshot",
                "params": lambda m: {"monitor": 0},
                "description": "截取屏幕截图",
                "keywords": ["截图", "截屏"],
                "priority": 0,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"截个屏$",
                "action": "screenshot",
                "params": lambda m: {"monitor": 0},
                "description": "截屏",
                "keywords": ["截屏"],
                "priority": 0,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"截屏$",
                "action": "screenshot",
                "params": lambda m: {"monitor": 0},
                "description": "截屏",
                "keywords": ["截屏"],
                "priority": 0,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"(?:截取|拍)(?:一张)?(?:屏幕)?截图",
                "action": "screenshot",
                "params": lambda m: {"monitor": 0},
                "description": "截取屏幕截图",
                "keywords": ["截图", "截屏"],
                "priority": 0,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"(?:点击|单击)\s*(?:坐标)?\s*\(?(\d+)\s*[,，]\s*(\d+)\)?",
                "action": "mouse_click",
                "params": lambda m: {"x": int(m.group(1)), "y": int(m.group(2)), "button": "left"},
                "description": "鼠标点击",
                "keywords": ["点击", "单击"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"双击\s*(?:坐标)?\s*\(?(\d+)\s*[,，]\s*(\d+)\)?",
                "action": "mouse_click",
                "params": lambda m: {"x": int(m.group(1)), "y": int(m.group(2)), "clicks": 2},
                "description": "鼠标双击",
                "keywords": ["双击"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"右键(?:点击)?\s*(?:坐标)?\s*\(?(\d+)\s*[,，]\s*(\d+)\)?",
                "action": "mouse_click",
                "params": lambda m: {"x": int(m.group(1)), "y": int(m.group(2)), "button": "right"},
                "description": "鼠标右键点击",
                "keywords": ["右键"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"(?:移动|移动鼠标到)\s*(?:坐标)?\s*\(?(\d+)\s*[,，]\s*(\d+)\)?",
                "action": "mouse_move",
                "params": lambda m: {"x": int(m.group(1)), "y": int(m.group(2))},
                "description": "移动鼠标",
                "keywords": ["移动"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"(?:鼠标|光标)(?:现在)?(?:在)?哪里",
                "action": "mouse_position",
                "params": lambda m: {},
                "description": "获取鼠标位置",
                "keywords": ["鼠标", "位置"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"(?:输入|打字)\s*[\"「『]([^」」\']*)[」』\"]",
                "action": "keyboard_type",
                "params": lambda m: {"text": m.group(1)},
                "description": "键盘输入",
                "keywords": ["输入", "打字"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"(?:输入|打字)\s*(.+)",
                "action": "keyboard_type",
                "params": lambda m: {"text": m.group(1)},
                "description": "键盘输入",
                "keywords": ["输入", "打字"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"按下\s*(\S+)\s*键",
                "action": "keyboard_press",
                "params": lambda m: {"key": m.group(1)},
                "description": "按下按键",
                "keywords": ["按下", "键"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"(?:按下|按)\s*([A-Za-z0-9]+)\s*(?:和|加|\\+)\s*([A-Za-z0-9]+)\s*键",
                "action": "keyboard_hotkey",
                "params": lambda m: {"keys": [m.group(1), m.group(2)]},
                "description": "按下组合键",
                "keywords": ["组合键", "快捷键"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"(?:列出|显示)(?:所有)?(?:打开的)?窗口",
                "action": "window_list",
                "params": lambda m: {},
                "description": "列出所有窗口",
                "keywords": ["窗口", "列出"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"(?:当前|活动)(?:的)?窗口(?:是什么|是啥)",
                "action": "window_active",
                "params": lambda m: {},
                "description": "获取活动窗口",
                "keywords": ["当前窗口", "活动窗口"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"激活\s*(.+?)\s*窗口",
                "action": "window_activate",
                "params": lambda m: {"title": m.group(1)},
                "description": "激活窗口",
                "keywords": ["激活"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"(?:切换|转到)\s*(?:到)?\s*(.+?)\s*窗口",
                "action": "window_activate",
                "params": lambda m: {"title": m.group(1)},
                "description": "切换窗口",
                "keywords": ["切换", "转到"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"关闭\s*(.+?)\s*窗口",
                "action": "window_close",
                "params": lambda m: {"title": m.group(1)},
                "description": "关闭窗口",
                "keywords": ["关闭"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"(?:最小化|最小)\s*(.+?)\s*窗口",
                "action": "window_minimize",
                "params": lambda m: {"title": m.group(1)},
                "description": "最小化窗口",
                "keywords": ["最小化"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"(?:最大化|最大)\s*(.+?)\s*窗口",
                "action": "window_maximize",
                "params": lambda m: {"title": m.group(1)},
                "description": "最大化窗口",
                "keywords": ["最大化"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"(?:识别|OCR)(?:屏幕上的)?文字",
                "action": "ocr_recognize",
                "params": lambda m: {},
                "description": "OCR识别文字",
                "keywords": ["OCR", "识别"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"(?:识别|OCR)(?:屏幕)?(?:上的)?文字",
                "action": "ocr_recognize",
                "params": lambda m: {},
                "description": "OCR识别文字",
                "keywords": ["OCR", "识别"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"(?:查找|寻找|找)\s*(?:屏幕上的)?(?:文字|文本)?\s*[\"「『]([^」」\']*)[」』\"]",
                "action": "ocr_find_text",
                "params": lambda m: {"text": m.group(1)},
                "description": "查找屏幕文字",
                "keywords": ["查找", "文字"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"开始录制",
                "action": "record_start",
                "params": lambda m: {},
                "description": "开始录制操作",
                "keywords": ["录制", "开始"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"停止录制",
                "action": "record_stop",
                "params": lambda m: {},
                "description": "停止录制",
                "keywords": ["停止", "录制"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"(?:回放|播放)(?:录制的)?(?:操作)?",
                "action": "record_play",
                "params": lambda m: {},
                "description": "回放录制的操作",
                "keywords": ["回放", "播放"],
                "priority": 1,
                "category": IntentCategory.CUA_OPERATION
            },
            {
                "pattern": r"(?:系统|电脑)(?:信息|状态|配置)",
                "action": "system_info",
                "params": lambda m: {},
                "description": "获取系统信息",
                "keywords": ["系统", "信息"],
                "priority": 1,
                "category": IntentCategory.SYSTEM_OPERATION
            },
            {
                "pattern": r"(?:CPU|内存|磁盘|网络)(?:使用率|状态|信息)?",
                "action": "hardware_monitor",
                "params": lambda m: {"component": m.group(1) if m.group(1) else "all"},
                "description": "硬件监控",
                "keywords": ["CPU", "内存", "磁盘", "网络"],
                "priority": 1,
                "category": IntentCategory.SYSTEM_OPERATION
            },
            {
                "pattern": r"(?:进程|任务)(?:列表|管理)",
                "action": "process_list",
                "params": lambda m: {},
                "description": "列出进程",
                "keywords": ["进程", "任务"],
                "priority": 1,
                "category": IntentCategory.SYSTEM_OPERATION
            },
        ]

        self.rule_patterns.sort(key=lambda x: x.get("priority", 3))

    def _init_intent_definitions(self):
        """初始化意图定义"""
        self._intent_definitions = {
            "file_create": {
                "description": "创建新文件",
                "required_params": ["file_path"],
                "optional_params": ["content"],
                "keywords": ["创建", "新建", "生成", "建立", "弄", "搞"],
                "category": IntentCategory.FILE_OPERATION,
                "dangerous": False
            },
            "file_read": {
                "description": "读取文件内容",
                "required_params": ["file_path"],
                "optional_params": [],
                "keywords": ["读取", "查看", "打开", "显示", "看"],
                "category": IntentCategory.FILE_OPERATION,
                "dangerous": False
            },
            "file_write": {
                "description": "写入或修改文件",
                "required_params": ["file_path"],
                "optional_params": ["content"],
                "keywords": ["写入", "修改", "更新", "编辑", "保存"],
                "category": IntentCategory.FILE_OPERATION,
                "dangerous": False
            },
            "file_delete": {
                "description": "删除文件",
                "required_params": ["file_path"],
                "optional_params": [],
                "keywords": ["删除", "移除", "清除", "删掉"],
                "category": IntentCategory.FILE_OPERATION,
                "dangerous": True
            },
            "file_list": {
                "description": "列出目录文件",
                "required_params": [],
                "optional_params": ["directory"],
                "keywords": ["列出", "显示", "查看", "ls", "dir"],
                "category": IntentCategory.FILE_OPERATION,
                "dangerous": False
            },
            "app_open": {
                "description": "打开应用程序",
                "required_params": ["app_name"],
                "optional_params": [],
                "keywords": ["打开", "启动", "运行", "开启"],
                "category": IntentCategory.APP_CONTROL,
                "dangerous": False
            },
            "url_open": {
                "description": "打开网址",
                "required_params": ["url"],
                "optional_params": [],
                "keywords": ["打开", "访问", "http", "https"],
                "category": IntentCategory.BROWSER_OPERATION,
                "dangerous": False
            },
            "screenshot": {
                "description": "截取屏幕",
                "required_params": [],
                "optional_params": ["monitor"],
                "keywords": ["截图", "截屏", "截取"],
                "category": IntentCategory.CUA_OPERATION,
                "dangerous": False
            },
            "mouse_click": {
                "description": "鼠标点击",
                "required_params": ["x", "y"],
                "optional_params": ["button", "clicks"],
                "keywords": ["点击", "单击", "双击"],
                "category": IntentCategory.CUA_OPERATION,
                "dangerous": False
            },
            "mouse_move": {
                "description": "移动鼠标",
                "required_params": ["x", "y"],
                "optional_params": [],
                "keywords": ["移动", "移动到"],
                "category": IntentCategory.CUA_OPERATION,
                "dangerous": False
            },
            "keyboard_type": {
                "description": "键盘输入",
                "required_params": ["text"],
                "optional_params": [],
                "keywords": ["输入", "打字", "键盘"],
                "category": IntentCategory.CUA_OPERATION,
                "dangerous": False
            },
            "keyboard_press": {
                "description": "按下按键",
                "required_params": ["key"],
                "optional_params": [],
                "keywords": ["按下", "按键"],
                "category": IntentCategory.CUA_OPERATION,
                "dangerous": False
            },
            "window_list": {
                "description": "列出窗口",
                "required_params": [],
                "optional_params": [],
                "keywords": ["窗口", "列出"],
                "category": IntentCategory.CUA_OPERATION,
                "dangerous": False
            },
            "window_activate": {
                "description": "激活窗口",
                "required_params": ["title"],
                "optional_params": [],
                "keywords": ["激活"],
                "category": IntentCategory.CUA_OPERATION,
                "dangerous": False
            },
            "window_close": {
                "description": "关闭窗口",
                "required_params": ["title"],
                "optional_params": [],
                "keywords": ["关闭"],
                "category": IntentCategory.CUA_OPERATION,
                "dangerous": False
            },
            "ocr_recognize": {
                "description": "OCR识别",
                "required_params": [],
                "optional_params": [],
                "keywords": ["OCR", "识别", "文字"],
                "category": IntentCategory.CUA_OPERATION,
                "dangerous": False
            },
            "record_start": {
                "description": "开始录制",
                "required_params": [],
                "optional_params": [],
                "keywords": ["录制", "开始"],
                "category": IntentCategory.CUA_OPERATION,
                "dangerous": False
            },
            "record_stop": {
                "description": "停止录制",
                "required_params": [],
                "optional_params": [],
                "keywords": ["停止", "录制"],
                "category": IntentCategory.CUA_OPERATION,
                "dangerous": False
            },
        }

    def _get_session_context(self, session_id: str) -> ConversationContext:
        """获取会话上下文（支持持久化）"""
        if self.session_store:
            stored_data = self.session_store.get(session_id)
            if stored_data:
                ctx = ConversationContext(session_id)
                ctx.recent_messages = stored_data.recent_messages
                ctx.recent_intents = stored_data.recent_intents
                ctx.mentioned_entities = stored_data.mentioned_entities
                ctx.user_preferences = stored_data.user_preferences
                ctx.current_task = stored_data.current_task
                ctx.expecting_action = stored_data.expecting_action

                with self.sessions_lock:
                    self.sessions[session_id] = ctx
                return ctx

        with self.sessions_lock:
            if session_id not in self.sessions:
                self.sessions[session_id] = ConversationContext(session_id)
            return self.sessions[session_id]

    def _resolve_context_references(self, message: str, params: dict[str, Any], context: ConversationContext) -> tuple[dict[str, Any], float]:
        """解析上下文引用"""
        resolved_params = params.copy()
        boost = 0.0

        reference_keywords = {
            "它": "file_path",
            "这个": "file_path",
            "那个": "file_path",
            "这个文件": "file_path",
            "那个文件": "file_path",
            "这个目录": "directory",
            "那个目录": "directory",
            "这个应用": "app_name",
            "那个应用": "app_name",
            "刚才": "intent",
            "继续": "intent",
            "重复": "intent"
        }

        for keyword, entity_type in reference_keywords.items():
            if keyword in message:
                resolved = context.resolve_reference(keyword)
                if resolved:
                    if entity_type == "file_path" and "file_path" not in resolved_params:
                        resolved_params["file_path"] = resolved
                        boost += 0.15
                    elif entity_type == "directory" and "directory" not in resolved_params:
                        resolved_params["directory"] = resolved
                        boost += 0.15
                    elif entity_type == "app_name" and "app_name" not in resolved_params:
                        resolved_params["app_name"] = resolved
                        boost += 0.15
                    elif entity_type == "intent" and not resolved_params.get("action"):
                        resolved_params["action"] = resolved
                        boost += 0.15

        if context.expecting_action and not resolved_params.get("action"):
            resolved_params["action"] = context.expecting_action
            boost += 0.2

        content_keywords = ["刚才的内容", "刚才生成", "刚才写的", "刚才创建的", "生成的内容", "写的内容", "创建的内容"]
        if any(kw in message for kw in content_keywords):
            if context.user_preferences.get("last_generated_content"):
                if "content" not in resolved_params:
                    resolved_params["content"] = context.user_preferences["last_generated_content"]
                    boost += 0.2

        save_patterns = ["保存", "存", "存储"]
        if any(p in message for p in save_patterns):
            if not resolved_params.get("content"):
                if context.user_preferences.get("last_generated_content"):
                    resolved_params["content"] = context.user_preferences["last_generated_content"]
                    boost += 0.1

        return resolved_params, min(boost, 0.3)

    def _infer_from_context(self, message: str, context: ConversationContext) -> IntentResult | None:
        """从上下文推断意图"""
        action_keywords = {
            "读取": "file_read",
            "查看": "file_read",
            "打开": "file_read",
            "修改": "file_write",
            "写入": "file_write",
            "编辑": "file_write",
            "删除": "file_delete",
            "移除": "file_delete",
            "继续": context.recent_intents[-1] if context.recent_intents else None,
            "重复": context.recent_intents[-1] if context.recent_intents else None,
        }

        for keyword, intent in action_keywords.items():
            if keyword in message:
                if intent:
                    params = {}
                    resolved = context.resolve_reference("它")
                    if resolved:
                        params["file_path"] = resolved

                    intent_def = self._intent_definitions.get(intent, {})
                    return IntentResult(
                        detected=True,
                        intent_type=intent,
                        action=intent,
                        params=params,
                        description=intent_def.get("description", ""),
                        confidence=0.6,
                        confidence_level=ConfidenceLevel.MEDIUM,
                        method=DetectionMethod.CONTEXT,
                        need_confirm=True,
                        category=intent_def.get("category", IntentCategory.UNKNOWN)
                    )

        return None

    def _detect_by_rules(self, message: str) -> list[IntentResult]:
        """规则匹配检测"""
        results = []

        for pattern_def in self.rule_patterns:
            pattern = pattern_def["pattern"]
            match = re.search(pattern, message, re.IGNORECASE)

            if match:
                try:
                    params = pattern_def["params"](match)
                except Exception:
                    continue

                if pattern_def.get("category") == IntentCategory.CONVERSATION:
                    return []

                confidence = self._calculate_rule_confidence(message, match, pattern_def)

                need_confirm = pattern_def.get("need_confirm", False)
                if confidence < self.CONFIDENCE_MEDIUM:
                    need_confirm = True

                results.append(IntentResult(
                    detected=True,
                    intent_type=pattern_def["action"],
                    action=pattern_def["action"],
                    params=params,
                    description=pattern_def.get("description", ""),
                    confidence=confidence,
                    confidence_level=self._get_confidence_level(confidence),
                    method=DetectionMethod.RULE,
                    need_confirm=need_confirm,
                    category=pattern_def.get("category", IntentCategory.UNKNOWN)
                ))

        return results

    def _calculate_rule_confidence(self, message: str, match: re.Match, pattern_def: dict[str, Any]) -> float:
        """计算规则匹配置信度"""
        base_confidence = 0.75

        match_coverage = len(match.group(0)) / len(message)
        base_confidence += match_coverage * 0.15

        keywords = pattern_def.get("keywords", [])
        matched_keywords = sum(1 for kw in keywords if kw.lower() in message.lower())
        if keywords:
            base_confidence += (matched_keywords / len(keywords)) * 0.1

        return min(1.0, base_confidence)

    def _detect_by_semantic(self, message: str) -> list[IntentResult]:
        """语义匹配检测"""
        results = []

        if not self._components_initialized or not self.semantic_matcher:
            return results

        try:
            matches = self.semantic_matcher.match(message, top_k=3, threshold=0.4)

            for match in matches:
                intent_def = self._intent_definitions.get(match.intent_name)
                if intent_def:
                    results.append(IntentResult(
                        detected=True,
                        intent_type=match.intent_name,
                        action=match.intent_name,
                        params={},
                        description=intent_def.get("description", ""),
                        confidence=match.similarity * 0.9,
                        confidence_level=self._get_confidence_level(match.similarity * 0.9),
                        method=DetectionMethod.SEMANTIC,
                        need_confirm=match.similarity < self.CONFIDENCE_MEDIUM,
                        category=intent_def.get("category", IntentCategory.UNKNOWN)
                    ))
        except Exception as e:
            logger.debug(f"语义匹配失败: {e}")

        return results

    def _detect_by_fuzzy(self, message: str) -> list[IntentResult]:
        """模糊匹配检测"""
        results = []

        if not self._components_initialized or not self.fuzzy_matcher:
            return results

        try:
            matches = self.fuzzy_matcher.fuzzy_match(message)

            for intent_name, confidence in matches[:3]:
                intent_def = self._intent_definitions.get(intent_name)
                if intent_def:
                    results.append(IntentResult(
                        detected=True,
                        intent_type=intent_name,
                        action=intent_name,
                        params={},
                        description=intent_def.get("description", ""),
                        confidence=confidence * 0.8,
                        confidence_level=self._get_confidence_level(confidence * 0.8),
                        method=DetectionMethod.FUZZY,
                        need_confirm=confidence < self.CONFIDENCE_MEDIUM,
                        category=intent_def.get("category", IntentCategory.UNKNOWN)
                    ))
        except Exception as e:
            logger.debug(f"模糊匹配失败: {e}")

        return results

    def _get_confidence_level(self, confidence: float) -> ConfidenceLevel:
        """获取置信度等级"""
        if confidence >= self.CONFIDENCE_HIGH:
            return ConfidenceLevel.HIGH
        elif confidence >= self.CONFIDENCE_MEDIUM:
            return ConfidenceLevel.MEDIUM
        elif confidence >= self.CONFIDENCE_LOW:
            return ConfidenceLevel.LOW
        return ConfidenceLevel.UNKNOWN

    def _merge_results(self, results: list[IntentResult]) -> list[IntentResult]:
        """合并检测结果"""
        merged = {}

        for result in results:
            key = result.intent_type
            if key not in merged or result.confidence > merged[key].confidence:
                merged[key] = result

        return sorted(merged.values(), key=lambda x: x.confidence, reverse=True)

    def _create_clarification(self, results: list[IntentResult], message: str) -> dict[str, Any] | None:
        """创建澄清对话"""
        if len(results) < 2:
            return None

        options = []
        for result in results[:5]:
            options.append({
                "label": result.description or result.intent_type,
                "value": result.intent_type,
                "confidence": result.confidence
            })

        return {
            "type": "clarification",
            "message": "我不太确定您的意思，请选择您想要执行的操作：",
            "options": options
        }

    def _create_suggestions(self, message: str) -> dict[str, Any]:
        """创建建议"""
        suggestions = [
            "创建一个新文件",
            "读取文件内容",
            "列出当前目录",
            "打开应用程序",
            "截取屏幕截图"
        ]

        return {
            "type": "suggestion",
            "message": "我没有理解您的请求，您可以尝试以下操作：",
            "suggestions": suggestions[:4]
        }

    def detect(
        self,
        message: str,
        session_id: str | None = None,
        context: dict[str, Any] | None = None
    ) -> IntentResult:
        """
        检测用户意图

        Args:
            message: 用户消息
            session_id: 会话ID
            context: 额外上下文

        Returns:
            IntentResult: 检测结果
        """
        start_time = time.time()

        if not message or not message.strip():
            if self.metrics:
                self.metrics.record_failure((time.time() - start_time) * 1000)
            return IntentResult(detected=False)

        message = message.strip()

        # 首先检测复合请求
        composite = self._detect_composite_request(message)
        if composite:
            logger.info(f"检测到复合请求: {composite}")
            return IntentResult(
                detected=True,
                intent_type="composite_request",
                action="composite_content_gen",  # 添加 action 字段
                confidence=0.95,
                confidence_level=ConfidenceLevel.HIGH,
                method=DetectionMethod.RULE,
                params=composite,
                description=f"复合请求：生成{composite['content_type']}并保存"
            )

        ctx = None
        if session_id and self.use_context:
            ctx = self._get_session_context(session_id)

        candidates = []

        if self.bert_classifier and self.bert_classifier.is_loaded():
            if len(message) >= 3:
                try:
                    bert_result = self.bert_classifier.predict_with_params(message)
                    if bert_result.intent != "unknown" and bert_result.confidence > 0.7:
                        bert_intent_result = IntentResult(
                            detected=True,
                            intent_type=bert_result.intent,
                            action=bert_result.intent,
                            confidence=bert_result.confidence,
                            confidence_level=self._get_confidence_level(bert_result.confidence),
                            method=DetectionMethod.SEMANTIC,
                            params=bert_result.params
                        )
                        candidates.append(bert_intent_result)
                        logger.debug(f"BERT 检测: {bert_result.intent} ({bert_result.confidence:.4f}), 参数: {bert_result.params}")
                except Exception as e:
                    logger.warning(f"BERT 检测失败: {e}")

        rule_results = self._detect_by_rules(message)
        candidates.extend(rule_results)

        if self._components_initialized:
            semantic_results = self._detect_by_semantic(message)
            candidates.extend(semantic_results)

            fuzzy_results = self._detect_by_fuzzy(message)
            candidates.extend(fuzzy_results)

        if not candidates:
            if ctx:
                context_intent = self._infer_from_context(message, ctx)
                if context_intent:
                    response_time = (time.time() - start_time) * 1000
                    if self.metrics:
                        self.metrics.record_detection(
                            DetectionMethod.CONTEXT,
                            context_intent.intent_type,
                            context_intent.confidence,
                            response_time
                        )
                    ctx.add_message("user", message, context_intent.intent_type, context_intent.params)
                    return context_intent

            response_time = (time.time() - start_time) * 1000
            if self.metrics:
                self.metrics.record_failure(response_time)

            clarification = self._create_suggestions(message)
            return IntentResult(
                detected=False,
                confidence=0.0,
                confidence_level=ConfidenceLevel.UNKNOWN,
                clarification=clarification
            )

        merged_results = self._merge_results(candidates)

        best_result = merged_results[0]

        if ctx:
            resolved_params, context_boost = self._resolve_context_references(
                message, best_result.params, ctx
            )
            best_result.params = resolved_params
            if context_boost > 0:
                best_result.confidence = min(best_result.confidence + context_boost, 1.0)
                best_result.confidence_level = self._get_confidence_level(best_result.confidence)
                best_result.method = DetectionMethod.CONTEXT

        alternatives = [
            (r.intent_type, r.confidence)
            for r in merged_results[1:self.MAX_ALTERNATIVES]
        ]
        best_result.alternatives = alternatives

        if len(merged_results) > 1:
            confidence_gap = merged_results[0].confidence - merged_results[1].confidence
            if confidence_gap < 0.15:
                best_result.clarification = self._create_clarification(merged_results, message)
                best_result.need_confirm = True

        if best_result.confidence < self.CONFIDENCE_MEDIUM:
            best_result.need_confirm = True

        if self._components_initialized and self.confidence_evaluator:
            conf_result = self.confidence_evaluator.evaluate(
                message=message,
                params=best_result.params,
                intent_name=best_result.intent_type,
                context=context
            )
            best_result.confidence = (best_result.confidence * 0.7 + conf_result.score * 0.3)
            best_result.confidence_level = self._get_confidence_level(best_result.confidence)

        response_time = (time.time() - start_time) * 1000

        if self.metrics:
            self.metrics.record_detection(
                best_result.method,
                best_result.intent_type,
                best_result.confidence,
                response_time
            )

        if ctx and best_result.detected:
            ctx.add_message("user", message, best_result.intent_type, best_result.params)

        return best_result

    def detect_multi(
        self,
        message: str,
        session_id: str | None = None,
        context: dict[str, Any] | None = None
    ) -> MultiIntentResult:
        """
        多意图检测

        Args:
            message: 用户消息
            session_id: 会话ID
            context: 额外上下文

        Returns:
            MultiIntentResult: 多意图检测结果
        """
        separators = [
            r"[，,]\s*(?:然后|接着|并且|同时|再|之后)",
            r"[。]\s*",
            r"\s+然后\s+",
            r"\s+接着\s+",
            r"\s+并且\s+",
            r"\s+同时\s+",
            r"\s+之后\s+",
            r"\s+再\s+",
            r"\s+并\s+",
            r"[，,]\s*",
        ]

        sub_messages = [message]
        for sep in separators:
            new_parts = []
            for part in sub_messages:
                split_result = re.split(sep, part)
                new_parts.extend([p.strip() for p in split_result if p.strip()])
            sub_messages = new_parts

        sub_messages = [msg for msg in sub_messages if len(msg) >= 2]

        intents = []
        for sub_msg in sub_messages:
            result = self.detect(sub_msg, session_id, context)
            if result.detected:
                intents.append(result)

        if not intents and sub_messages:
            result = self.detect(message, session_id, context)
            if result.detected:
                intents.append(result)

        if not intents:
            return MultiIntentResult(
                detected=False,
                intents=[],
                clarification_dialog=self._create_suggestions(message)
            )

        has_ambiguity = len(intents) > 1
        clarification = None

        if has_ambiguity:
            clarification = {
                "type": "multi_intent",
                "message": f"检测到 {len(intents)} 个操作，请确认执行顺序：",
                "intents": [i.to_dict() for i in intents]
            }

        return MultiIntentResult(
            detected=True,
            intents=intents,
            has_ambiguity=has_ambiguity,
            clarification_dialog=clarification
        )

    async def detect_with_llm(
        self,
        message: str,
        session_id: str | None = None,
        context: dict[str, Any] | None = None
    ) -> IntentResult:
        """
        使用LLM进行意图检测

        Args:
            message: 用户消息
            session_id: 会话ID
            context: 额外上下文

        Returns:
            IntentResult: 检测结果
        """
        if not self.llm_client or not self.use_llm_fallback:
            return self.detect(message, session_id, context)

        result = self.detect(message, session_id, context)

        if result.detected and result.confidence >= self.CONFIDENCE_HIGH:
            return result

        try:
            llm_result = await self._llm_detect(message, context)
            if llm_result:
                if not result.detected or llm_result.confidence > result.confidence:
                    return llm_result
        except Exception as e:
            logger.warning(f"LLM检测失败: {e}")

        return result

    async def _llm_detect(
        self,
        message: str,
        context: dict[str, Any] | None
    ) -> IntentResult | None:
        """调用LLM进行意图检测"""
        if not self.llm_client:
            return None

        try:
            import json
            prompt = f"""分析用户意图并提取参数。

用户消息: {message}
上下文: {json.dumps(context or {}, ensure_ascii=False)}

支持的意图类型:
- file_create: 创建文件 (参数: file_path, content)
- file_read: 读取文件 (参数: file_path)
- file_write: 写入文件 (参数: file_path, content)
- file_delete: 删除文件 (参数: file_path)
- file_list: 列出文件 (参数: directory)
- app_open: 打开应用 (参数: app_name)
- url_open: 打开网址 (参数: url)
- screenshot: 截图 (参数: monitor)
- mouse_click: 鼠标点击 (参数: x, y, button)
- keyboard_type: 键盘输入 (参数: text)

返回 JSON 格式:
{{
    "intent": "意图类型",
    "params": {{}},
    "confidence": 0.0-1.0
}}

只返回 JSON，不要其他内容。"""

            response = await asyncio.wait_for(
                self._call_llm(prompt),
                timeout=5.0
            )

            return self._parse_llm_response(response)

        except asyncio.TimeoutError:
            logger.warning("LLM意图检测超时")
        except Exception as e:
            logger.error(f"LLM意图检测失败: {e}")

        return None

    async def _call_llm(self, prompt: str) -> str:
        """调用LLM"""
        if hasattr(self.llm_client, 'generate'):
            return await self.llm_client.generate(prompt)
        elif hasattr(self.llm_client, 'chat'):
            return await self.llm_client.chat(prompt)
        else:
            raise ValueError("LLM client不支持generate或chat方法")

    def _parse_llm_response(self, response: str) -> IntentResult | None:
        """解析LLM响应"""
        try:
            import json
            json_match = re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                return None

            data = json.loads(json_match.group())

            intent_name = data.get("intent", "")
            intent_def = self._intent_definitions.get(intent_name)

            if not intent_def:
                return None

            return IntentResult(
                detected=True,
                intent_type=intent_name,
                action=intent_name,
                params=data.get("params", {}),
                description=intent_def.get("description", ""),
                confidence=data.get("confidence", 0.7),
                confidence_level=self._get_confidence_level(data.get("confidence", 0.7)),
                method=DetectionMethod.LLM,
                need_confirm=data.get("confidence", 0.7) < self.CONFIDENCE_HIGH,
                category=intent_def.get("category", IntentCategory.UNKNOWN)
            )
        except Exception as e:
            logger.error(f"解析LLM响应失败: {e}")
            return None

    def record_feedback(
        self,
        session_id: str,
        predicted_intent: str,
        is_correct: bool,
        actual_intent: str | None = None
    ):
        """记录用户反馈"""
        if self._components_initialized and self.confidence_evaluator:
            self.confidence_evaluator.record_result(predicted_intent, is_correct)

        if self._components_initialized and self.metrics:
            self.metrics.intent_distribution[predicted_intent] = \
                self.metrics.intent_distribution.get(predicted_intent, 0) + 1

    def get_metrics_report(self) -> dict[str, Any]:
        """获取性能指标报告"""
        if self.metrics:
            return self.metrics.get_report()
        return {"error": "Metrics not enabled"}

    def reset_metrics(self):
        """重置性能指标"""
        if self.metrics:
            self.metrics.reset()

    def clear_session(self, session_id: str):
        """清除会话上下文"""
        with self.sessions_lock:
            if session_id in self.sessions:
                del self.sessions[session_id]

    def update_session_context(self, session_id: str, updates: dict[str, Any]):
        """更新会话上下文"""
        with self.sessions_lock:
            if session_id in self.sessions:
                ctx = self.sessions[session_id]
                for key, value in updates.items():
                    if key == "last_generated_content":
                        content_type = updates.get("last_generated_type", "text")
                        ctx.set_generated_content(value, content_type)
                    elif key == "last_action":
                        ctx.user_preferences["last_action"] = value
                    else:
                        ctx.user_preferences[key] = value
            else:
                ctx = ConversationContext(session_id)
                for key, value in updates.items():
                    if key == "last_generated_content":
                        ctx.set_generated_content(value, updates.get("last_generated_type", "text"))
                    else:
                        ctx.user_preferences[key] = value
                self.sessions[session_id] = ctx


def create_unified_detector(
    llm_client=None,
    use_semantic: bool = True,
    use_context: bool = True,
    use_llm_fallback: bool = True,
    use_bert: bool = True,
    enable_metrics: bool = True,
    session_store=None
) -> UnifiedIntentDetector:
    """创建统一意图检测器"""
    return UnifiedIntentDetector(
        llm_client=llm_client,
        use_semantic=use_semantic,
        use_context=use_context,
        use_llm_fallback=use_llm_fallback,
        use_bert=use_bert,
        enable_metrics=enable_metrics,
        session_store=session_store
    )
