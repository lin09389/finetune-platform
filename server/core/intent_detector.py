"""
增强版意图检测器
支持多意图并行检测、置信度评分、意图澄清对话、参数提�?"""
import re
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class IntentType(str, Enum):
    """意图类型"""
    FILE_OPERATION = "file_operation"
    CODE_EXECUTION = "code_execution"
    SYSTEM_OPERATION = "system_operation"
    INFORMATION_QUERY = "information_query"
    APP_CONTROL = "app_control"
    BROWSER_OPERATION = "browser_operation"
    CUA_OPERATION = "cua_operation"
    UNKNOWN = "unknown"


class ParamType(str, Enum):
    """参数类型"""
    STRING = "string"
    NUMBER = "number"
    DATE = "date"
    PATH = "path"
    URL = "url"
    COMMAND = "command"
    ENTITY = "entity"
    BOOLEAN = "boolean"


@dataclass
class ExtractedParam:
    """提取的参�?""
    name: str
    value: Any
    param_type: ParamType
    confidence: float = 1.0
    raw_text: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "param_type": self.param_type.value,
            "confidence": self.confidence,
            "raw_text": self.raw_text
        }


@dataclass
class DetectedIntent:
    """检测到的意�?""
    intent_type: IntentType
    action: str
    params: List[ExtractedParam]
    confidence: float
    description: str
    need_clarification: bool = False
    clarification_question: str = ""
    raw_match: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_type": self.intent_type.value,
            "action": self.action,
            "params": [p.to_dict() for p in self.params],
            "confidence": self.confidence,
            "description": self.description,
            "need_clarification": self.need_clarification,
            "clarification_question": self.clarification_question,
            "raw_match": self.raw_match
        }


@dataclass
class MultiIntentResult:
    """多意图检测结�?""
    detected: bool
    intents: List[DetectedIntent]
    has_ambiguity: bool = False
    clarification_dialog: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "detected": self.detected,
            "intents": [i.to_dict() for i in self.intents],
            "has_ambiguity": self.has_ambiguity,
            "clarification_dialog": self.clarification_dialog
        }


@dataclass
class ClarificationDialog:
    """澄清对话"""
    dialog_id: str
    question: str
    options: List[Dict[str, Any]]
    context: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "dialog_id": self.dialog_id,
            "question": self.question,
            "options": self.options,
            "context": self.context,
            "created_at": self.created_at.isoformat()
        }


class ParameterExtractor:
    """参数提取�?""
    
    PATTERNS = {
        ParamType.PATH: [
            r'["\']?([a-zA-Z]:\\[\\\\\w\-\.\s]+)["\']?',
            r'["\']?(/[\w\-\.\s]+)["\']?',
            r'([\w\-]+\.[a-zA-Z]{1,4})',
            r'([\w\-]+/[\w\-\.]+)',
        ],
        ParamType.URL: [
            r'(https?://[\w\-\.]+(:\d+)?(/[\w\-\.\?=&%#/]*)?)',
        ],
        ParamType.NUMBER: [
            r'\b(\d+(?:\.\d+)?)\b',
            r'(\d+)\s*(?:个|次|条|�?',
        ],
        ParamType.DATE: [
            r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)',
            r'(\d{1,2}[-/月]\d{1,2}[日]?)',
            r'(今天|明天|后天|昨天|前天)',
            r'(下[一二三四五六七]|本周[一二三四五六七])',
        ],
        ParamType.COMMAND: [
            r'`([^`]+)`',
            r'"([^"]+)"',
            r'�?[^」]+)�?,
        ],
    }
    
    DATE_MAPPING = {
        "今天": 0,
        "明天": 1,
        "后天": 2,
        "昨天": -1,
        "前天": -2,
    }
    
    def extract_path(self, text: str) -> Optional[ExtractedParam]:
        """提取文件路径"""
        for pattern in self.PATTERNS[ParamType.PATH]:
            match = re.search(pattern, text)
            if match:
                path = match.group(1).strip('"\'')
                return ExtractedParam(
                    name="path",
                    value=path,
                    param_type=ParamType.PATH,
                    confidence=0.9,
                    raw_text=match.group(0)
                )
        return None
    
    def extract_url(self, text: str) -> Optional[ExtractedParam]:
        """提取 URL"""
        for pattern in self.PATTERNS[ParamType.URL]:
            match = re.search(pattern, text)
            if match:
                return ExtractedParam(
                    name="url",
                    value=match.group(1),
                    param_type=ParamType.URL,
                    confidence=0.95,
                    raw_text=match.group(0)
                )
        return None
    
    def extract_number(self, text: str) -> Optional[ExtractedParam]:
        """提取数字"""
        for pattern in self.PATTERNS[ParamType.NUMBER]:
            match = re.search(pattern, text)
            if match:
                num_str = match.group(1)
                value = float(num_str) if '.' in num_str else int(num_str)
                return ExtractedParam(
                    name="number",
                    value=value,
                    param_type=ParamType.NUMBER,
                    confidence=0.9,
                    raw_text=match.group(0)
                )
        return None
    
    def extract_date(self, text: str) -> Optional[ExtractedParam]:
        """提取日期"""
        for pattern in self.PATTERNS[ParamType.DATE]:
            match = re.search(pattern, text)
            if match:
                date_text = match.group(1)
                
                if date_text in self.DATE_MAPPING:
                    from datetime import timedelta
                    delta = timedelta(days=self.DATE_MAPPING[date_text])
                    value = (datetime.now() + delta).strftime("%Y-%m-%d")
                else:
                    date_text = re.sub(r'[年月]', '-', date_text)
                    date_text = re.sub(r'�?, '', date_text)
                    date_text = date_text.replace('/', '-')
                    value = date_text
                
                return ExtractedParam(
                    name="date",
                    value=value,
                    param_type=ParamType.DATE,
                    confidence=0.85,
                    raw_text=match.group(0)
                )
        return None
    
    def extract_command(self, text: str) -> Optional[ExtractedParam]:
        """提取命令"""
        for pattern in self.PATTERNS[ParamType.COMMAND]:
            match = re.search(pattern, text)
            if match:
                return ExtractedParam(
                    name="command",
                    value=match.group(1),
                    param_type=ParamType.COMMAND,
                    confidence=0.9,
                    raw_text=match.group(0)
                )
        return None
    
    def extract_all(self, text: str) -> List[ExtractedParam]:
        """提取所有参�?""
        params = []
        
        url = self.extract_url(text)
        if url:
            params.append(url)
            text = text.replace(url.raw_text, "")
        
        path = self.extract_path(text)
        if path:
            params.append(path)
        
        date = self.extract_date(text)
        if date:
            params.append(date)
        
        number = self.extract_number(text)
        if number:
            params.append(number)
        
        command = self.extract_command(text)
        if command:
            params.append(command)
        
        return params


class IntentClarifier:
    """意图澄清�?""
    
    CLARIFICATION_TEMPLATES = {
        "ambiguous_intent": [
            "我不太确定您的意图，您是想要�?,
            "请确认您想要执行的操作：",
            "检测到多个可能的意图，请选择�?
        ],
        "missing_param": [
            "请提供{param_name}参数",
            "缺少必要的信息：{param_name}",
            "请告诉我{param_name}是什�?
        ],
        "low_confidence": [
            "我不太确定您的意思，能否详细描述一下？",
            "请提供更多细节以便我更好地理解您的需�?,
            "能否换一种方式描述您的请求？"
        ],
        "multiple_intents": [
            "检测到您可能有多个请求，请选择优先执行的操作：",
            "您的消息包含多个意图，请确认执行顺序�?
        ]
    }
    
    PARAM_QUESTIONS = {
        "file_path": "文件路径",
        "content": "文件内容",
        "directory": "目录路径",
        "app_name": "应用名称",
        "url": "网址",
        "text": "文本内容",
        "command": "命令"
    }
    
    def __init__(self):
        self.active_dialogs: Dict[str, ClarificationDialog] = {}
    
    def create_clarification(
        self,
        intent: DetectedIntent,
        reason: str = "ambiguous_intent"
    ) -> ClarificationDialog:
        """创建澄清对话"""
        import uuid
        dialog_id = str(uuid.uuid4())[:8]
        
        templates = self.CLARIFICATION_TEMPLATES.get(reason, self.CLARIFICATION_TEMPLATES["ambiguous_intent"])
        question = templates[0]
        
        options = []
        if reason == "ambiguous_intent":
            options = [
                {"label": f"执行 {intent.description}", "value": "confirm", "action": intent.action},
                {"label": "取消操作", "value": "cancel", "action": None}
            ]
        elif reason == "missing_param":
            missing_param = self._identify_missing_param(intent)
            if missing_param:
                param_name = self.PARAM_QUESTIONS.get(missing_param, missing_param)
                question = question.format(param_name=param_name)
            options = [
                {"label": "提供参数", "value": "provide", "param": missing_param},
                {"label": "取消操作", "value": "cancel", "action": None}
            ]
        elif reason == "low_confidence":
            options = [
                {"label": "确认执行", "value": "confirm", "action": intent.action},
                {"label": "重新描述", "value": "rephrase", "action": None},
                {"label": "取消操作", "value": "cancel", "action": None}
            ]
        
        dialog = ClarificationDialog(
            dialog_id=dialog_id,
            question=question,
            options=options,
            context={
                "intent": intent.to_dict(),
                "reason": reason
            }
        )
        
        self.active_dialogs[dialog_id] = dialog
        return dialog
    
    def create_multi_intent_clarification(
        self,
        intents: List[DetectedIntent]
    ) -> ClarificationDialog:
        """创建多意图澄清对�?""
        import uuid
        dialog_id = str(uuid.uuid4())[:8]
        
        question = self.CLARIFICATION_TEMPLATES["multiple_intents"][0]
        
        options = []
        for i, intent in enumerate(intents[:5]):
            options.append({
                "label": f"{i+1}. {intent.description}",
                "value": f"intent_{i}",
                "action": intent.action,
                "intent": intent.to_dict()
            })
        options.append({"label": "全部执行", "value": "all", "action": "all"})
        options.append({"label": "取消", "value": "cancel", "action": None})
        
        dialog = ClarificationDialog(
            dialog_id=dialog_id,
            question=question,
            options=options,
            context={
                "intents": [i.to_dict() for i in intents],
                "reason": "multiple_intents"
            }
        )
        
        self.active_dialogs[dialog_id] = dialog
        return dialog
    
    def _identify_missing_param(self, intent: DetectedIntent) -> Optional[str]:
        """识别缺失的参�?""
        required_params = self._get_required_params(intent.action)
        existing_params = {p.name for p in intent.params}
        
        for param in required_params:
            if param not in existing_params:
                return param
        return None
    
    def _get_required_params(self, action: str) -> List[str]:
        """获取操作所需的参�?""
        required = {
            "file_create": ["file_path"],
            "file_read": ["file_path"],
            "file_write": ["file_path", "content"],
            "file_delete": ["file_path"],
            "file_list": [],
            "app_open": ["app_name"],
            "url_open": ["url"],
            "mouse_click": ["x", "y"],
            "keyboard_type": ["text"],
        }
        return required.get(action, [])
    
    def handle_response(
        self,
        dialog_id: str,
        response: str
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """处理用户响应"""
        dialog = self.active_dialogs.get(dialog_id)
        if not dialog:
            return False, {"error": "Dialog not found"}
        
        for option in dialog.options:
            if response == option.get("value") or response in option.get("label", ""):
                if dialog_id in self.active_dialogs:
                    del self.active_dialogs[dialog_id]
                return True, option
        
        return False, {"error": "Invalid response"}
    
    def get_dialog(self, dialog_id: str) -> Optional[ClarificationDialog]:
        """获取活跃的澄清对�?""
        return self.active_dialogs.get(dialog_id)


class EnhancedIntentDetector:
    """增强版意图检测器"""
    
    CONFIDENCE_THRESHOLD = 0.7
    
    INTENT_PATTERNS = [
        {
            "patterns": [
                r"创建\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"新建\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"生成\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"建立一个\s*[\"']?([\w\-./]+)[\"']?",
                r"创建\s*([\w\-./]+\.[a-zA-Z]+)\s*文件",
            ],
            "action": "file_create",
            "intent_type": IntentType.FILE_OPERATION,
            "description": "创建文件",
            "required_params": ["file_path"],
            "keywords": ["创建", "新建", "生成", "建立"]
        },
        {
            "patterns": [
                r"读取\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"打开\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"查看\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"显示\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
            ],
            "action": "file_read",
            "intent_type": IntentType.FILE_OPERATION,
            "description": "读取文件",
            "required_params": ["file_path"],
            "keywords": ["读取", "打开", "查看", "显示"]
        },
        {
            "patterns": [
                r"写入\s*[\"']?([\w\-./]+)[\"']?",
                r"修改\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"更新\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"把\s*[\"']?([\w\-./]+)[\"']?\s*改成",
            ],
            "action": "file_write",
            "intent_type": IntentType.FILE_OPERATION,
            "description": "写入文件",
            "required_params": ["file_path"],
            "keywords": ["写入", "修改", "更新", "改成"]
        },
        {
            "patterns": [
                r"删除\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"移除\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"清除\s*[\"']?([\w\-./]+)[\"']?",
            ],
            "action": "file_delete",
            "intent_type": IntentType.FILE_OPERATION,
            "description": "删除文件",
            "required_params": ["file_path"],
            "keywords": ["删除", "移除", "清除"],
            "dangerous": True
        },
        {
            "patterns": [
                r"列出\s*([\w\-./]*)\s*(?:�??(?:文件|目录)?",
                r"显示\s*([\w\-./]*)\s*(?:�??(?:文件|目录)?",
                r"ls\s*([\w\-./]*)",
                r"查看\s*([\w\-./]*)\s*目录",
            ],
            "action": "file_list",
            "intent_type": IntentType.FILE_OPERATION,
            "description": "列出文件",
            "required_params": [],
            "keywords": ["列出", "显示", "ls", "目录"]
        },
        {
            "patterns": [
                r"打开\s*(VS\s*Code|Visual\s*Studio\s*Code)",
                r"启动\s*(VS\s*Code|Visual\s*Studio\s*Code)",
                r"打开\s*(记事本|Notepad)",
                r"打开\s*(Chrome|谷歌浏览�?",
                r"打开\s*(Edge|edge)",
                r"打开\s*(计算器|Calculator)",
                r"启动\s*(计算器|Calculator)",
                r"打开\s*([\w\s]+?)(?:应用|软件|程序)?",
            ],
            "action": "app_open",
            "intent_type": IntentType.APP_CONTROL,
            "description": "打开应用",
            "required_params": ["app_name"],
            "keywords": ["打开", "启动", "应用", "软件"]
        },
        {
            "patterns": [
                r"(https?://\S+)",
                r"打开\s*(https?://\S+)",
                r"访问\s*(https?://\S+)",
            ],
            "action": "url_open",
            "intent_type": IntentType.BROWSER_OPERATION,
            "description": "打开网址",
            "required_params": ["url"],
            "keywords": ["http", "https", "网址", "访问"]
        },
        {
            "patterns": [
                r"截图",
                r"截屏",
                r"截取屏幕",
            ],
            "action": "screenshot",
            "intent_type": IntentType.CUA_OPERATION,
            "description": "截取屏幕",
            "required_params": [],
            "keywords": ["截图", "截屏"]
        },
        {
            "patterns": [
                r"(?:点击|单击)\s*\(?(\d+)\s*[,，]\s*(\d+)\)?",
                r"右键\s*\(?(\d+)\s*[,，]\s*(\d+)\)?",
                r"双击\s*\(?(\d+)\s*[,，]\s*(\d+)\)?",
            ],
            "action": "mouse_click",
            "intent_type": IntentType.CUA_OPERATION,
            "description": "鼠标点击",
            "required_params": ["x", "y"],
            "keywords": ["点击", "单击", "右键", "双击"]
        },
        {
            "patterns": [
                r"(?:输入|打字)\s*[\"「『]([^」」\"]*)[」』\"]",
                r"输入\s+(.+)",
            ],
            "action": "keyboard_type",
            "intent_type": IntentType.CUA_OPERATION,
            "description": "键盘输入",
            "required_params": ["text"],
            "keywords": ["输入", "打字"]
        },
    ]
    
    MULTI_INTENT_SEPARATORS = [
        r"[�?�?]\s*(?:然后|接着|�??",
        r"(?:然后|接着|�?\s*",
        r"[。]\s*",
        r"\\s+同时\\s+",
    ]
    
    def __init__(self):
        self.param_extractor = ParameterExtractor()
        self.clarifier = IntentClarifier()
        self._compile_patterns()
    
    def _compile_patterns(self):
        """编译正则表达�?""
        for intent_def in self.INTENT_PATTERNS:
            intent_def["compiled_patterns"] = [
                re.compile(p, re.IGNORECASE) for p in intent_def["patterns"]
            ]
        
        self.compiled_separators = [
            re.compile(s, re.IGNORECASE) for s in self.MULTI_INTENT_SEPARATORS
        ]
    
    def detect(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> MultiIntentResult:
        """
        检测意图（支持多意图）
        
        Args:
            message: 用户消息
            context: 上下文信�?            
        Returns:
            MultiIntentResult: 多意图检测结�?        """
        if not message or not message.strip():
            return MultiIntentResult(detected=False, intents=[])
        
        message = message.strip()
        
        sub_messages = self._split_multi_intent(message)
        
        all_intents = []
        for sub_msg in sub_messages:
            intents = self._detect_single(sub_msg, context)
            all_intents.extend(intents)
        
        if not all_intents:
            return MultiIntentResult(detected=False, intents=[])
        
        all_intents.sort(key=lambda x: x.confidence, reverse=True)
        
        has_ambiguity = any(i.need_clarification for i in all_intents)
        clarification_dialog = None
        
        if len(all_intents) > 1:
            has_ambiguity = True
            clarification_dialog = self.clarifier.create_multi_intent_clarification(all_intents).to_dict()
        elif all_intents[0].confidence < self.CONFIDENCE_THRESHOLD:
            has_ambiguity = True
            clarification_dialog = self.clarifier.create_clarification(
                all_intents[0], "low_confidence"
            ).to_dict()
        
        return MultiIntentResult(
            detected=True,
            intents=all_intents,
            has_ambiguity=has_ambiguity,
            clarification_dialog=clarification_dialog
        )
    
    def _split_multi_intent(self, message: str) -> List[str]:
        """分割多意图消�?""
        parts = [message]
        
        for separator in self.compiled_separators:
            new_parts = []
            for part in parts:
                split_result = separator.split(part)
                new_parts.extend([p.strip() for p in split_result if p.strip()])
            parts = new_parts
        
        return parts if parts else [message]
    
    def _detect_single(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> List[DetectedIntent]:
        """检测单个消息的意图"""
        detected = []
        
        for intent_def in self.INTENT_PATTERNS:
            for pattern in intent_def["compiled_patterns"]:
                match = pattern.search(message)
                if match:
                    confidence = self._calculate_confidence(
                        message, match, intent_def
                    )
                    
                    params = self._extract_params(message, match, intent_def)
                    
                    need_clarification = confidence < self.CONFIDENCE_THRESHOLD
                    clarification_question = ""
                    if need_clarification:
                        clarification_question = self._generate_clarification_question(
                            intent_def, params
                        )
                    
                    intent = DetectedIntent(
                        intent_type=intent_def["intent_type"],
                        action=intent_def["action"],
                        params=params,
                        confidence=confidence,
                        description=intent_def["description"],
                        need_clarification=need_clarification,
                        clarification_question=clarification_question,
                        raw_match=match.group(0)
                    )
                    
                    detected.append(intent)
                    break
        
        return detected
    
    def _calculate_confidence(
        self,
        message: str,
        match: re.Match,
        intent_def: Dict[str, Any]
    ) -> float:
        """计算置信�?""
        score = 0.5
        
        match_coverage = len(match.group(0)) / len(message)
        score += match_coverage * 0.2
        
        keywords = intent_def.get("keywords", [])
        matched_keywords = sum(1 for kw in keywords if kw in message)
        keyword_score = matched_keywords / len(keywords) if keywords else 0
        score += keyword_score * 0.2
        
        if intent_def.get("dangerous"):
            score *= 0.95
        
        return min(1.0, max(0.0, score))
    
    def _extract_params(
        self,
        message: str,
        match: re.Match,
        intent_def: Dict[str, Any]
    ) -> List[ExtractedParam]:
        """提取参数"""
        params = []
        
        if match.groups():
            for i, group in enumerate(match.groups()):
                if group:
                    param_name = self._get_param_name(intent_def["action"], i)
                    param_type = self._infer_param_type(group)
                    params.append(ExtractedParam(
                        name=param_name,
                        value=group,
                        param_type=param_type,
                        confidence=0.9,
                        raw_text=group
                    ))
        
        extra_params = self.param_extractor.extract_all(message)
        for param in extra_params:
            if not any(p.name == param.name for p in params):
                params.append(param)
        
        return params
    
    def _get_param_name(self, action: str, index: int) -> str:
        """根据动作和索引获取参数名"""
        param_mapping = {
            "file_create": ["file_path", "content"],
            "file_read": ["file_path"],
            "file_write": ["file_path", "content"],
            "file_delete": ["file_path"],
            "file_list": ["directory"],
            "app_open": ["app_name"],
            "url_open": ["url"],
            "mouse_click": ["x", "y", "button"],
            "keyboard_type": ["text"],
        }
        
        names = param_mapping.get(action, [])
        return names[index] if index < len(names) else f"param_{index}"
    
    def _infer_param_type(self, value: str) -> ParamType:
        """推断参数类型"""
        if re.match(r'^https?://', value):
            return ParamType.URL
        if re.match(r'^[a-zA-Z]:\\', value) or re.match(r'^/', value):
            return ParamType.PATH
        if re.match(r'^\d+$', value):
            return ParamType.NUMBER
        if re.match(r'^\d{4}[-/年]', value):
            return ParamType.DATE
        return ParamType.STRING
    
    def _generate_clarification_question(
        self,
        intent_def: Dict[str, Any],
        params: List[ExtractedParam]
    ) -> str:
        """生成澄清问题"""
        required = intent_def.get("required_params", [])
        existing = {p.name for p in params}
        missing = [r for r in required if r not in existing]
        
        if missing:
            param_names = ", ".join(missing)
            return f"请提供更多信息：缺少 {param_names}"
        
        return f"请确认您想要执行：{intent_def['description']}�?
    
    def get_clarification_dialog(
        self,
        dialog_id: str
    ) -> Optional[Dict[str, Any]]:
        """获取澄清对话"""
        dialog = self.clarifier.get_dialog(dialog_id)
        return dialog.to_dict() if dialog else None
    
    def handle_clarification_response(
        self,
        dialog_id: str,
        response: str
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """处理澄清响应"""
        return self.clarifier.handle_response(dialog_id, response)


_detector_instance: Optional[EnhancedIntentDetector] = None


def get_intent_detector() -> EnhancedIntentDetector:
    """获取意图检测器单例"""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = EnhancedIntentDetector()
    return _detector_instance
