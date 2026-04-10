"""
智能意图检测器
支持三层检测：规则匹配 -> 语义匹配 -> LLM后备
"""
import asyncio
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agent.config import ActionType

logger = logging.getLogger(__name__)


class DetectionMethod(str, Enum):
    """检测方法"""
    RULE = "rule"
    SEMANTIC = "semantic"
    LLM = "llm"
    CONTEXT = "context"


@dataclass
class SmartIntentResult:
    """智能意图检测结果"""
    detected: bool
    action: ActionType | None = None
    params: dict[str, Any] | None = None
    description: str = ""
    confidence: float = 0.0
    method: DetectionMethod = DetectionMethod.RULE
    need_confirm: bool = False
    alternatives: list[tuple[str, float]] = field(default_factory=list)
    clarification: dict[str, Any] | None = None
    suggestions: list[str] = field(default_factory=list)


class ActionKeywordClassifier:
    """动作关键词分类器"""

    ACTION_KEYWORDS = {
        ActionType.FILE_CREATE: {
            "positive": ["创建", "新建", "生成", "建立", "弄", "搞", "写", "做", "建", "建个", "新建个"],
            "negative": ["删除", "移除", "不要", "取消"],
        },
        ActionType.FILE_READ: {
            "positive": ["读取", "查看", "打开", "显示", "看看", "读一下", "看一下", "瞧瞧", "瞅瞅"],
            "negative": ["写入", "修改", "删除"],
        },
        ActionType.FILE_WRITE: {
            "positive": ["写入", "修改", "更新", "编辑", "更改", "改", "保存", "存"],
            "negative": ["读取", "查看", "删除"],
        },
        ActionType.FILE_DELETE: {
            "positive": ["删除", "移除", "清除", "去掉", "删掉", "卸载", "清理"],
            "negative": ["创建", "新建"],
        },
        ActionType.FILE_LIST: {
            "positive": ["列出", "显示", "查看", "ls", "dir", "有哪些", "文件列表"],
            "negative": ["删除", "创建"],
        },
        ActionType.APP_OPEN: {
            "positive": ["打开", "启动", "运行", "开启", "执行"],
            "negative": ["关闭", "退出"],
        },
        ActionType.SCREENSHOT: {
            "positive": ["截图", "截屏", "截取", "抓屏", "拍照", "屏幕"],
            "negative": [],
        },
    }

    def classify(self, message: str) -> list[tuple[ActionType, float]]:
        """分类并返回候选意图"""
        scores = {}

        for action, keywords in self.ACTION_KEYWORDS.items():
            pos_score = sum(1 for kw in keywords["positive"] if kw in message)
            neg_score = sum(1 for kw in keywords["negative"] if kw in message)

            if pos_score > 0:
                net_score = (pos_score - neg_score) / len(keywords["positive"])
                if net_score > 0:
                    scores[action] = min(1.0, net_score * 0.8)

        return sorted(scores.items(), key=lambda x: x[1], reverse=True)


class SmartParamExtractor:
    """智能参数提取器"""

    FILE_PATH_PATTERNS = [
        r"([a-zA-Z][\w\-./]*\.[a-zA-Z]{1,10})",
        r"叫[它]?([a-zA-Z][\w\-./]*)",
        r"名为[：:]?\s*([a-zA-Z][\w\-./]*)",
        r"文件名[是为]?\s*([a-zA-Z][\w\-./]*)",
    ]

    CONTENT_PATTERNS = [
        r"[：:]\s*(.+)$",
        r"内容[是为]?\s*[\"「『]([^」」\"]*)[」』\"]",
        r"写入\s*[\"「『]([^」」\"]*)[」』\"]",
        r"改成\s*[\"「『]([^」」\"]*)[」』\"]",
    ]

    APP_NAME_PATTERNS = [
        r"(?:打开|启动|运行|开启)\s*(\S+)",
        r"(VS\s*Code|Visual\s*Studio\s*Code|vscode)",
        r"(记事本|notepad)",
        r"(Chrome|chrome|谷歌浏览器)",
        r"(Edge|edge)",
        r"(计算器|calculator)",
        r"(PowerShell|powershell)",
        r"(终端|terminal|cmd)",
    ]

    URL_PATTERNS = [
        r"(https?://[^\s]+)",
    ]

    @classmethod
    def extract_file_path(cls, message: str) -> str | None:
        """提取文件路径"""
        for pattern in cls.FILE_PATH_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    @classmethod
    def extract_content(cls, message: str) -> str | None:
        """提取内容"""
        for pattern in cls.CONTENT_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1).strip()
        return None

    @classmethod
    def extract_app_name(cls, message: str) -> str | None:
        """提取应用名称"""
        for pattern in cls.APP_NAME_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    @classmethod
    def extract_url(cls, message: str) -> str | None:
        """提取URL"""
        for pattern in cls.URL_PATTERNS:
            match = re.search(pattern, message)
            if match:
                return match.group(1)
        return None


class SmartRuleMatcher:
    """智能规则匹配器"""

    RULES = [
        {
            "action": ActionType.FILE_CREATE,
            "patterns": [
                r"(?:创建|新建|生成|建立|弄|搞|写|做|建)\s*(?:一个)?(?:新)?(?:文件|文档|脚本)?",
                r"帮我(?:创建|新建|生成|建立)",
                r"要一个(?:新)?文件",
            ],
            "param_extractors": {
                "file_path": SmartParamExtractor.FILE_PATH_PATTERNS,
            },
            "priority": 1,
        },
        {
            "action": ActionType.FILE_READ,
            "patterns": [
                r"(?:读取|查看|打开|显示|看看|读一下|看一下|瞧瞧|瞅瞅)\s*(?:一下)?(?:这个)?(?:文件|文档)?",
            ],
            "param_extractors": {
                "file_path": SmartParamExtractor.FILE_PATH_PATTERNS,
            },
            "priority": 1,
        },
        {
            "action": ActionType.FILE_WRITE,
            "patterns": [
                r"(?:写入|修改|更新|编辑|更改|改|保存|存)\s*(?:一下)?",
                r"(?:把|将).*(?:写入|保存|改成|修改)",
                r"保存\s*(?:到|在)?\s*(?:桌面)?",
            ],
            "param_extractors": {
                "file_path": SmartParamExtractor.FILE_PATH_PATTERNS,
                "content": SmartParamExtractor.CONTENT_PATTERNS,
            },
            "priority": 1,
        },
        {
            "action": ActionType.FILE_DELETE,
            "patterns": [
                r"(?:删除|移除|清除|去掉|删掉|卸载|清理)\s*(?:这个)?(?:文件|文档)?",
            ],
            "param_extractors": {
                "file_path": SmartParamExtractor.FILE_PATH_PATTERNS,
            },
            "priority": 1,
            "need_confirm": True,
        },
        {
            "action": ActionType.FILE_LIST,
            "patterns": [
                r"(?:列出|显示|查看|ls|dir)\s*(?:一下)?(?:当前)?(?:目录|文件夹)?",
                r"有哪些文件",
                r"文件列表",
            ],
            "param_extractors": {},
            "priority": 1,
        },
        {
            "action": ActionType.APP_OPEN,
            "patterns": [
                r"(?:打开|启动|运行|开启)\s*\S+",
            ],
            "param_extractors": {
                "app_name": SmartParamExtractor.APP_NAME_PATTERNS,
            },
            "priority": 2,
        },
        {
            "action": ActionType.URL_OPEN,
            "patterns": [
                r"https?://",
                r"(?:打开|访问)\s*(?:网址|网站|链接)?",
            ],
            "param_extractors": {
                "url": SmartParamExtractor.URL_PATTERNS,
            },
            "priority": 0,
        },
        {
            "action": ActionType.SCREENSHOT,
            "patterns": [
                r"^(?:截图|截屏|截取)$",
                r"(?:帮我)?(?:截个?|截取?)(?:屏|图|屏幕)",
                r"拍(?:个)?(?:一)?张?(?:屏幕)?(?:照片|图)",
            ],
            "param_extractors": {},
            "priority": 0,
        },
    ]

    def __init__(self):
        self._compiled_rules = []
        for rule in self.RULES:
            compiled = {
                "action": rule["action"],
                "patterns": [re.compile(p, re.IGNORECASE) for p in rule["patterns"]],
                "param_extractors": rule.get("param_extractors", {}),
                "priority": rule.get("priority", 3),
                "need_confirm": rule.get("need_confirm", False),
            }
            self._compiled_rules.append(compiled)

        self._compiled_rules.sort(key=lambda x: x["priority"])

    def match(self, message: str) -> list[tuple[ActionType, float, dict[str, Any], bool]]:
        """匹配消息并返回候选列表"""
        candidates = []

        for rule in self._compiled_rules:
            for pattern in rule["patterns"]:
                match = pattern.search(message)
                if match:
                    params = self._extract_params(message, rule["param_extractors"])
                    confidence = self._calculate_confidence(message, match, rule)

                    candidates.append((
                        rule["action"],
                        confidence,
                        params,
                        rule.get("need_confirm", False)
                    ))
                    break

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates

    def _extract_params(self, message: str, extractors: dict[str, list[str]]) -> dict[str, Any]:
        """提取参数"""
        params = {}

        for param_name, patterns in extractors.items():
            for pattern in patterns:
                try:
                    match = re.search(pattern, message, re.IGNORECASE)
                    if match and match.groups():
                        params[param_name] = match.group(1)
                        break
                except Exception:
                    continue

        return params

    def _calculate_confidence(self, message: str, match: re.Match, rule: dict) -> float:
        """计算置信度"""
        base_confidence = 0.7

        match_coverage = len(match.group(0)) / len(message)
        base_confidence += match_coverage * 0.15

        if rule["param_extractors"]:
            has_params = any(
                re.search(p, message, re.IGNORECASE)
                for patterns in rule["param_extractors"].values()
                for p in patterns
            )
            if has_params:
                base_confidence += 0.1

        return min(1.0, base_confidence)


class IntelligentErrorHandler:
    """智能错误处理器"""

    INTENT_DESCRIPTIONS = {
        "file_create": "创建文件",
        "file_read": "读取文件",
        "file_write": "写入文件",
        "file_delete": "删除文件",
        "file_list": "列出文件",
        "app_open": "打开应用",
        "url_open": "打开网址",
        "screenshot": "截图",
    }

    SUGGESTIONS = {
        "file_create": [
            "创建一个 test.py 文件",
            "新建 README.md 文档",
            "生成配置文件 config.json",
        ],
        "file_read": [
            "读取 main.py 文件",
            "查看 README.md 内容",
            "打开 config.json",
        ],
        "file_write": [
            "写入内容到 test.py",
            "修改 config.json 配置",
            "保存到桌面",
        ],
        "file_list": [
            "列出当前目录文件",
            "显示 src 文件夹内容",
            "查看目录结构",
        ],
        "app_open": [
            "打开 VS Code",
            "启动 Chrome 浏览器",
            "运行记事本",
        ],
    }

    def handle_detection_failure(
        self,
        message: str,
        candidates: list = None
    ) -> dict[str, Any]:
        """处理检测失败"""
        if candidates and len(candidates) > 1:
            return self._create_clarification(candidates)

        return self._create_suggestions(message)

    def _create_clarification(self, candidates: list) -> dict[str, Any]:
        """创建澄清对话"""
        options = []
        for action, confidence, _params, _ in candidates[:3]:
            action_name = action.value if hasattr(action, 'value') else str(action)
            options.append({
                "label": self.INTENT_DESCRIPTIONS.get(action_name, action_name),
                "value": action_name,
                "confidence": confidence
            })

        return {
            "type": "clarification",
            "message": "我不太确定您的意思，请选择您想要执行的操作：",
            "options": options
        }

    def _create_suggestions(self, message: str) -> dict[str, Any]:
        """创建建议"""
        guessed_intents = self._guess_intents(message)

        suggestions = []
        for intent in guessed_intents[:3]:
            if intent in self.SUGGESTIONS:
                suggestions.extend(self.SUGGESTIONS[intent][:2])

        if not suggestions:
            suggestions = [
                "创建一个新文件",
                "读取文件内容",
                "列出当前目录",
                "打开应用程序",
            ]

        return {
            "type": "suggestion",
            "message": "我没有理解您的请求，您可以尝试以下操作：",
            "suggestions": suggestions[:4]
        }

    def _guess_intents(self, message: str) -> list[str]:
        """猜测可能的意图"""
        keywords_mapping = {
            "file_create": ["创建", "新建", "生成", "建立"],
            "file_read": ["读取", "查看", "打开", "显示"],
            "file_write": ["写入", "修改", "更新", "保存"],
            "file_delete": ["删除", "移除", "清除"],
            "file_list": ["列出", "显示", "目录"],
            "app_open": ["打开", "启动", "运行"],
        }

        guessed = []
        for intent, keywords in keywords_mapping.items():
            if any(kw in message for kw in keywords):
                guessed.append(intent)

        return guessed


class SmartIntentDetector:
    """智能意图检测器"""

    CONFIDENCE_HIGH = 0.8
    CONFIDENCE_MEDIUM = 0.6

    def __init__(self, llm_client=None):
        self.keyword_classifier = ActionKeywordClassifier()
        self.rule_matcher = SmartRuleMatcher()
        self.error_handler = IntelligentErrorHandler()
        self.llm_client = llm_client

    def detect(
        self,
        message: str,
        context: dict[str, Any] | None = None
    ) -> SmartIntentResult:
        """检测意图"""
        if not message or not message.strip():
            return SmartIntentResult(detected=False)

        message = message.strip()

        keyword_candidates = self.keyword_classifier.classify(message)

        rule_candidates = self.rule_matcher.match(message)

        all_candidates = self._merge_candidates(keyword_candidates, rule_candidates)

        if not all_candidates:
            return SmartIntentResult(
                detected=False,
                clarification=self.error_handler.handle_detection_failure(message)
            )

        best = all_candidates[0]
        action, confidence, params, need_confirm = best

        if (
            context
            and context.get("content")
            and action in (ActionType.FILE_WRITE, ActionType.FILE_CREATE)
            and not params.get("content")
        ):
            params["content"] = context["content"]

        if confidence >= self.CONFIDENCE_HIGH:
            return SmartIntentResult(
                detected=True,
                action=action,
                params=params,
                description=f"检测到操作: {action.value if hasattr(action, 'value') else str(action)}",
                confidence=confidence,
                method=DetectionMethod.RULE,
                need_confirm=need_confirm,
                alternatives=[(c[0].value if hasattr(c[0], 'value') else str(c[0]), c[1]) for c in all_candidates[1:3]]
            )

        if confidence >= self.CONFIDENCE_MEDIUM:
            return SmartIntentResult(
                detected=True,
                action=action,
                params=params,
                description=f"检测到操作: {action.value if hasattr(action, 'value') else str(action)}",
                confidence=confidence,
                method=DetectionMethod.RULE,
                need_confirm=True,
                alternatives=[(c[0].value if hasattr(c[0], 'value') else str(c[0]), c[1]) for c in all_candidates[1:3]]
            )

        return SmartIntentResult(
            detected=False,
            clarification=self.error_handler.handle_detection_failure(message, all_candidates)
        )

    def _merge_candidates(
        self,
        keyword_candidates: list[tuple[ActionType, float]],
        rule_candidates: list[tuple[ActionType, float, dict, bool]]
    ) -> list[tuple[ActionType, float, dict, bool]]:
        """合并关键词和规则候选"""
        merged = {}

        for action, confidence, params, need_confirm in rule_candidates:
            merged[action] = (action, confidence, params, need_confirm)

        for action, confidence in keyword_candidates:
            if action in merged:
                old = merged[action]
                merged[action] = (action, max(old[1], confidence), old[2], old[3])
            else:
                merged[action] = (action, confidence, {}, False)

        return sorted(merged.values(), key=lambda x: x[1], reverse=True)

    async def detect_with_llm_fallback(
        self,
        message: str,
        context: dict[str, Any] | None = None
    ) -> SmartIntentResult:
        """带 LLM 后备的意图检测"""
        result = self.detect(message, context)

        if result.detected and result.confidence >= self.CONFIDENCE_HIGH:
            return result

        if self.llm_client:
            llm_result = await self._llm_detect(message, context)
            if llm_result and llm_result.detected and (
                not result.detected or llm_result.confidence > result.confidence
            ):
                return llm_result

        return result

    async def _llm_detect(
        self,
        message: str,
        context: dict[str, Any] | None = None
    ) -> SmartIntentResult | None:
        """使用 LLM 进行意图检测"""
        if not self.llm_client:
            return None

        try:
            prompt = f"""分析用户意图并提取参数。

用户消息: {message}
上下文: {context or {}}

支持的意图类型:
- file_create: 创建文件 (参数: file_path, content)
- file_read: 读取文件 (参数: file_path)
- file_write: 写入文件 (参数: file_path, content)
- file_delete: 删除文件 (参数: file_path)
- file_list: 列出文件 (参数: directory)
- app_open: 打开应用 (参数: app_name)
- url_open: 打开网址 (参数: url)
- screenshot: 截图 (无参数)

返回 JSON 格式:
{{
    "intent": "意图类型",
    "params": {{}},
    "confidence": 0.0-1.0
}}

只返回 JSON，不要其他内容。"""

            if hasattr(self.llm_client, 'generate'):
                response = await asyncio.wait_for(
                    self.llm_client.generate(prompt),
                    timeout=5.0
                )
            elif hasattr(self.llm_client, 'chat'):
                response = await asyncio.wait_for(
                    self.llm_client.chat(prompt),
                    timeout=5.0
                )
            else:
                return None

            return self._parse_llm_response(response)

        except asyncio.TimeoutError:
            logger.warning("LLM 意图检测超时")
        except Exception as e:
            logger.error(f"LLM 意图检测失败: {e}")

        return None

    def _parse_llm_response(self, response: str) -> SmartIntentResult | None:
        """解析 LLM 响应"""
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                return None

            import json
            data = json.loads(json_match.group())

            intent_name = data.get("intent", "")
            action = self._get_action_from_name(intent_name)

            if not action:
                return None

            return SmartIntentResult(
                detected=True,
                action=action,
                params=data.get("params", {}),
                description=f"LLM 检测: {intent_name}",
                confidence=data.get("confidence", 0.7),
                method=DetectionMethod.LLM,
                need_confirm=data.get("confidence", 0.7) < 0.8
            )

        except Exception as e:
            logger.error(f"解析 LLM 响应失败: {e}")
            return None

    def _get_action_from_name(self, name: str) -> ActionType | None:
        """从名称获取 ActionType"""
        mapping = {
            "file_create": ActionType.FILE_CREATE,
            "file_read": ActionType.FILE_READ,
            "file_write": ActionType.FILE_WRITE,
            "file_delete": ActionType.FILE_DELETE,
            "file_list": ActionType.FILE_LIST,
            "app_open": ActionType.APP_OPEN,
            "url_open": ActionType.URL_OPEN,
            "screenshot": ActionType.SCREENSHOT,
        }
        return mapping.get(name)


def create_smart_detector(llm_client=None) -> SmartIntentDetector:
    """创建智能意图检测器"""
    return SmartIntentDetector(llm_client=llm_client)
