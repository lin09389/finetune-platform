"""
意图检测器主模块
支持规则匹配、语义匹配、上下文感知、置信度评估
"""
import re
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field

from ..config import ActionType

logger = logging.getLogger(__name__)


@dataclass
class IntentResult:
    """意图检测结果"""
    detected: bool
    action: Optional[ActionType] = None
    params: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    confidence: float = 0.0
    confidence_level: str = "low"
    need_confirm: bool = False
    alternatives: List[Tuple[str, float]] = field(default_factory=list)
    method: str = "rule"


class IntentDetector:
    """
    意图检测器 - 升级版
    
    支持多种检测模式：
    1. 规则匹配（快速，高准确率）
    2. 语义匹配（中等速度，覆盖广）
    3. 上下文感知（结合历史）
    4. LLM理解（智能后备）
    """
    
    def __init__(self, llm_client=None, use_semantic: bool = True):
        self.llm_client = llm_client
        self.use_semantic = use_semantic
        
        self._init_components()
        self._init_patterns()
    
    def _init_components(self):
        """初始化组件"""
        try:
            from .confidence import ConfidenceEvaluator, MultiFactorScorer
            from .semantic_matcher import SemanticMatcher, FuzzyMatcher
            from .context_aware import ContextAwareDetector, ContextManager
            from .disambiguator import IntentDisambiguator
            from .metrics import IntentMetrics
            from .data import INTENT_TRAINING_DATA
            
            self.confidence_evaluator = ConfidenceEvaluator()
            self.multi_factor_scorer = MultiFactorScorer()
            self.semantic_matcher = SemanticMatcher(use_embedding=self.use_semantic)
            self.fuzzy_matcher = FuzzyMatcher()
            self.context_manager = ContextManager()
            self.context_aware_detector = ContextAwareDetector(self.context_manager)
            self.disambiguator = IntentDisambiguator()
            self.metrics = IntentMetrics()
            
            samples = {}
            for intent_name, data in INTENT_TRAINING_DATA.items():
                samples[intent_name] = [s.text for s in data.get("samples", [])]
            self.semantic_matcher.load_intent_samples(samples)
            
            self._components_loaded = True
            logger.info("意图检测组件已加载")
        except Exception as e:
            logger.warning(f"部分组件加载失败，使用基础模式: {e}")
            self._components_loaded = False
            self.confidence_evaluator = None
            self.semantic_matcher = None
            self.fuzzy_matcher = None
            self.context_aware_detector = None
            self.disambiguator = None
            self.metrics = None
    
    def _init_patterns(self):
        """初始化规则模式"""
        self.patterns: List[Dict[str, Any]] = [
            {
                "pattern": r"创建(?:一个)?\s*([\w\-./]+\.\w+)",
                "action": ActionType.FILE_CREATE,
                "params": lambda m: {"file_path": m.group(1), "content": ""},
                "description": "创建文件",
                "keywords": ["创建"],
                "priority": 1
            },
            {
                "pattern": r"新建(?:一个)?\s*([\w\-./]+\.\w+)",
                "action": ActionType.FILE_CREATE,
                "params": lambda m: {"file_path": m.group(1), "content": ""},
                "description": "新建文件",
                "keywords": ["新建"],
                "priority": 1
            },
            {
                "pattern": r"生成(?:一个)?\s*([\w\-./]+\.\w+)",
                "action": ActionType.FILE_CREATE,
                "params": lambda m: {"file_path": m.group(1), "content": ""},
                "description": "生成文件",
                "keywords": ["生成"],
                "priority": 1
            },
            {
                "pattern": r"创建\s*([\w\-./]+\.\w+)\s*(?:文件)?",
                "action": ActionType.FILE_CREATE,
                "params": lambda m: {"file_path": m.group(1), "content": ""},
                "description": "创建文件",
                "keywords": ["创建", "文件"],
                "priority": 2
            },
            {
                "pattern": r"读取\s*([\w\-./]+\.\w+)",
                "action": ActionType.FILE_READ,
                "params": lambda m: {"file_path": m.group(1)},
                "description": "读取文件",
                "keywords": ["读取"],
                "priority": 1
            },
            {
                "pattern": r"读取\s*([\w\-./]+)\s*文件",
                "action": ActionType.FILE_READ,
                "params": lambda m: {"file_path": m.group(1)},
                "description": "读取文件",
                "keywords": ["读取", "文件"],
                "priority": 2
            },
            {
                "pattern": r"查看\s*([\w\-./]+\.\w+)\s*(?:的内容)?",
                "action": ActionType.FILE_READ,
                "params": lambda m: {"file_path": m.group(1)},
                "description": "查看文件内容",
                "keywords": ["查看"],
                "priority": 1
            },
            {
                "pattern": r"打开\s*(\S+\.(?:txt|py|js|ts|md|json|yaml|yml|xml|html|css|log|cfg|ini|env))",
                "action": ActionType.FILE_READ,
                "params": lambda m: {"file_path": m.group(1)},
                "description": "打开文件",
                "keywords": ["打开"],
                "priority": 1
            },
            {
                "pattern": r"显示\s*(\S+\.\w+)\s*(?:的内容)?",
                "action": ActionType.FILE_READ,
                "params": lambda m: {"file_path": m.group(1)},
                "description": "显示文件内容",
                "keywords": ["显示"],
                "priority": 1
            },
            {
                "pattern": r"把\s*(\S+)\s*(?:的内容)?改成\s*(.+)",
                "action": ActionType.FILE_WRITE,
                "params": lambda m: {"file_path": m.group(1), "content": m.group(2)},
                "description": "修改文件内容",
                "keywords": ["改成", "修改"],
                "priority": 1
            },
            {
                "pattern": r"写入\s*(\S+)\s*(.+)",
                "action": ActionType.FILE_WRITE,
                "params": lambda m: {"file_path": m.group(1), "content": m.group(2)},
                "description": "写入文件",
                "keywords": ["写入"],
                "priority": 1
            },
            {
                "pattern": r"向\s*(\S+)\s*(?:中)?写入\s*(.+)",
                "action": ActionType.FILE_WRITE,
                "params": lambda m: {"file_path": m.group(1), "content": m.group(2)},
                "description": "写入文件",
                "keywords": ["写入"],
                "priority": 1
            },
            {
                "pattern": r"修改\s*(\S+\.\w+)",
                "action": ActionType.FILE_WRITE,
                "params": lambda m: {"file_path": m.group(1), "content": ""},
                "description": "修改文件",
                "keywords": ["修改"],
                "priority": 2
            },
            {
                "pattern": r"更新\s*(\S+\.\w+)",
                "action": ActionType.FILE_WRITE,
                "params": lambda m: {"file_path": m.group(1), "content": ""},
                "description": "更新文件",
                "keywords": ["更新"],
                "priority": 2
            },
            {
                "pattern": r"删除\s*(\S+\.\w+)",
                "action": ActionType.FILE_DELETE,
                "params": lambda m: {"file_path": m.group(1)},
                "description": "删除文件",
                "keywords": ["删除"],
                "need_confirm": True,
                "priority": 1
            },
            {
                "pattern": r"移除\s*(\S+\.\w+)",
                "action": ActionType.FILE_DELETE,
                "params": lambda m: {"file_path": m.group(1)},
                "description": "移除文件",
                "keywords": ["移除"],
                "need_confirm": True,
                "priority": 1
            },
            {
                "pattern": r"删除\s+(\S+)",
                "action": ActionType.FILE_DELETE,
                "params": lambda m: {"file_path": m.group(1)},
                "description": "删除",
                "keywords": ["删除"],
                "need_confirm": True,
                "priority": 2
            },
            {
                "pattern": r"列出\s*(\S*)\s*(?:的)?文件",
                "action": ActionType.FILE_LIST,
                "params": lambda m: {"directory": m.group(1) or "."},
                "description": "列出文件",
                "keywords": ["列出", "文件"],
                "priority": 1
            },
            {
                "pattern": r"显示\s*(\S*)\s*(?:的)?文件",
                "action": ActionType.FILE_LIST,
                "params": lambda m: {"directory": m.group(1) or "."},
                "description": "显示文件列表",
                "keywords": ["显示", "文件"],
                "priority": 1
            },
            {
                "pattern": r"查看\s*(\S*)\s*目录",
                "action": ActionType.FILE_LIST,
                "params": lambda m: {"directory": m.group(1) or "."},
                "description": "查看目录内容",
                "keywords": ["查看", "目录"],
                "priority": 1
            },
            {
                "pattern": r"(?:列出|显示|查看)\s*当前目录",
                "action": ActionType.FILE_LIST,
                "params": lambda m: {"directory": "."},
                "description": "列出当前目录",
                "keywords": ["当前目录"],
                "priority": 1
            },
            {
                "pattern": r"ls\s*(\S*)",
                "action": ActionType.FILE_LIST,
                "params": lambda m: {"directory": m.group(1) or "."},
                "description": "列出目录",
                "keywords": ["ls"],
                "priority": 1
            },
            {
                "pattern": r"打开\s+(VS\s*Code|Visual\s*Studio\s*Code)",
                "action": ActionType.APP_OPEN,
                "params": lambda m: {"app_name": "vscode"},
                "description": "打开 VS Code",
                "keywords": ["VS Code"],
                "priority": 1
            },
            {
                "pattern": r"打开\s+(记事本|Notepad)",
                "action": ActionType.APP_OPEN,
                "params": lambda m: {"app_name": "notepad"},
                "description": "打开记事本",
                "keywords": ["记事本", "Notepad"],
                "priority": 1
            },
            {
                "pattern": r"打开\s+(Chrome|谷歌浏览器)",
                "action": ActionType.APP_OPEN,
                "params": lambda m: {"app_name": "chrome"},
                "description": "打开 Chrome",
                "keywords": ["Chrome"],
                "priority": 1
            },
            {
                "pattern": r"打开\s*(?:Edge|edge)",
                "action": ActionType.APP_OPEN,
                "params": lambda m: {"app_name": "edge"},
                "description": "打开Edge浏览器",
                "keywords": ["Edge"],
                "priority": 1
            },
            {
                "pattern": r"打开\s*(计算器|Calculator)",
                "action": ActionType.APP_OPEN,
                "params": lambda m: {"app_name": "calculator"},
                "description": "打开计算器",
                "keywords": ["计算器"],
                "priority": 1
            },
            {
                "pattern": r"启动\s*(计算器|Calculator)",
                "action": ActionType.APP_OPEN,
                "params": lambda m: {"app_name": "calculator"},
                "description": "启动计算器",
                "keywords": ["启动", "计算器"],
                "priority": 1
            },
            {
                "pattern": r"打开\s*(\S+)",
                "action": ActionType.APP_OPEN,
                "params": lambda m: {"app_name": m.group(1)},
                "description": "打开应用",
                "keywords": ["打开"],
                "priority": 3
            },
            {
                "pattern": r"启动\s*(\S+)",
                "action": ActionType.APP_OPEN,
                "params": lambda m: {"app_name": m.group(1)},
                "description": "启动应用",
                "keywords": ["启动"],
                "priority": 3
            },
            {
                "pattern": r"(https?://\S+)",
                "action": ActionType.URL_OPEN,
                "params": lambda m: {"url": m.group(1)},
                "description": "打开网页",
                "keywords": ["http", "https"],
                "priority": 1
            },
            {
                "pattern": r"打开\s*(?:网址\s*)?(https?://\S+)",
                "action": ActionType.URL_OPEN,
                "params": lambda m: {"url": m.group(1)},
                "description": "打开网址",
                "keywords": ["打开", "网址"],
                "priority": 1
            },
            {
                "pattern": r"访问\s*(https?://\S+)",
                "action": ActionType.URL_OPEN,
                "params": lambda m: {"url": m.group(1)},
                "description": "访问网址",
                "keywords": ["访问"],
                "priority": 1
            },
            # CUA 操作 - 屏幕截图 (最高优先级)
            {
                "pattern": r"^截图$",
                "action": ActionType.SCREENSHOT,
                "params": lambda m: {"monitor": 0},
                "description": "截取屏幕截图",
                "keywords": ["截图"],
                "priority": 0
            },
            {
                "pattern": r"^截屏$",
                "action": ActionType.SCREENSHOT,
                "params": lambda m: {"monitor": 0},
                "description": "截屏",
                "keywords": ["截屏"],
                "priority": 0
            },
            {
                "pattern": r"帮我截(?:个)?(?:一)?张?(?:屏)?(?:幕)?(?:图|照片)?",
                "action": ActionType.SCREENSHOT,
                "params": lambda m: {"monitor": 0},
                "description": "截取屏幕截图",
                "keywords": ["截图", "截屏"],
                "priority": 0
            },
            {
                "pattern": r"截(?:取)?(?:个)?(?:一)?张?(?:屏幕)?截图",
                "action": ActionType.SCREENSHOT,
                "params": lambda m: {"monitor": 0},
                "description": "截取屏幕截图",
                "keywords": ["截图", "截屏"],
                "priority": 1
            },
            {
                "pattern": r"截屏",
                "action": ActionType.SCREENSHOT,
                "params": lambda m: {"monitor": 0},
                "description": "截屏",
                "keywords": ["截屏"],
                "priority": 1
            },
            {
                "pattern": r"拍(?:个)?(?:一)?张?(?:屏幕)?照片",
                "action": ActionType.SCREENSHOT,
                "params": lambda m: {"monitor": 0},
                "description": "截取屏幕",
                "keywords": ["拍", "照片"],
                "priority": 2
            },
            # CUA 操作 - 鼠标控制
            {
                "pattern": r"(?:点击|单击|左键点击?)\s*(?:坐标)?\s*\(?(\d+)\s*[,，]\s*(\d+)\)?",
                "action": ActionType.MOUSE_CLICK,
                "params": lambda m: {"x": int(m.group(1)), "y": int(m.group(2)), "button": "left"},
                "description": "鼠标点击指定位置",
                "keywords": ["点击"],
                "priority": 1
            },
            {
                "pattern": r"右键点击?\s*(?:坐标)?\s*\(?(\d+)\s*[,，]\s*(\d+)\)?",
                "action": ActionType.MOUSE_CLICK,
                "params": lambda m: {"x": int(m.group(1)), "y": int(m.group(2)), "button": "right"},
                "description": "鼠标右键点击",
                "keywords": ["右键"],
                "priority": 1
            },
            {
                "pattern": r"双击\s*(?:坐标)?\s*\(?(\d+)\s*[,，]\s*(\d+)\)?",
                "action": ActionType.MOUSE_CLICK,
                "params": lambda m: {"x": int(m.group(1)), "y": int(m.group(2)), "clicks": 2},
                "description": "鼠标双击",
                "keywords": ["双击"],
                "priority": 1
            },
            {
                "pattern": r"(?:移动|移动鼠标到)\s*(?:坐标)?\s*\(?(\d+)\s*[,，]\s*(\d+)\)?",
                "action": ActionType.MOUSE_MOVE,
                "params": lambda m: {"x": int(m.group(1)), "y": int(m.group(2))},
                "description": "移动鼠标",
                "keywords": ["移动"],
                "priority": 1
            },
            {
                "pattern": r"获取(?:当前)?鼠标位置",
                "action": ActionType.MOUSE_POSITION,
                "params": lambda m: {},
                "description": "获取鼠标位置",
                "keywords": ["鼠标位置"],
                "priority": 1
            },
            {
                "pattern": r"鼠标(?:在)?哪里",
                "action": ActionType.MOUSE_POSITION,
                "params": lambda m: {},
                "description": "获取鼠标位置",
                "keywords": ["鼠标"],
                "priority": 2
            },
            # CUA 操作 - 键盘控制
            {
                "pattern": r"(?:输入|打字|键盘输入)\s*[\"「『]([^」」\']*)[」』\"]",
                "action": ActionType.KEYBOARD_TYPE,
                "params": lambda m: {"text": m.group(1)},
                "description": "键盘输入文本",
                "keywords": ["输入"],
                "priority": 1
            },
            {
                "pattern": r"输入\s*(.+)",
                "action": ActionType.KEYBOARD_TYPE,
                "params": lambda m: {"text": m.group(1)},
                "description": "键盘输入",
                "keywords": ["输入"],
                "priority": 3
            },
            {
                "pattern": r"按下\s*(\S+)\s*键",
                "action": ActionType.KEYBOARD_PRESS,
                "params": lambda m: {"key": m.group(1)},
                "description": "按下按键",
                "keywords": ["按下", "键"],
                "priority": 1
            },
            # CUA 操作 - 窗口管理
            {
                "pattern": r"(?:列出|显示|查看)(?:所有)?(?:打开的)?窗口",
                "action": ActionType.WINDOW_LIST,
                "params": lambda m: {},
                "description": "列出所有窗口",
                "keywords": ["窗口", "列出"],
                "priority": 1
            },
            {
                "pattern": r"(?:获取|查看)(?:当前)?活动窗口",
                "action": ActionType.WINDOW_ACTIVE,
                "params": lambda m: {},
                "description": "获取活动窗口",
                "keywords": ["活动窗口"],
                "priority": 1
            },
            {
                "pattern": r"激活\s*(.+?)\s*窗口",
                "action": ActionType.WINDOW_ACTIVATE,
                "params": lambda m: {"title": m.group(1)},
                "description": "激活窗口",
                "keywords": ["激活"],
                "priority": 1
            },
            {
                "pattern": r"关闭\s*(.+?)\s*窗口",
                "action": ActionType.WINDOW_CLOSE,
                "params": lambda m: {"title": m.group(1)},
                "description": "关闭窗口",
                "keywords": ["关闭"],
                "priority": 1
            },
            {
                "pattern": r"最小化\s*(.+?)\s*窗口",
                "action": ActionType.WINDOW_MINIMIZE,
                "params": lambda m: {"title": m.group(1)},
                "description": "最小化窗口",
                "keywords": ["最小化"],
                "priority": 1
            },
            {
                "pattern": r"最大化\s*(.+?)\s*窗口",
                "action": ActionType.WINDOW_MAXIMIZE,
                "params": lambda m: {"title": m.group(1)},
                "description": "最大化窗口",
                "keywords": ["最大化"],
                "priority": 1
            },
            # CUA 操作 - OCR
            {
                "pattern": r"(?:识别|OCR)(?:屏幕)?(?:上的)?文字",
                "action": ActionType.OCR_RECOGNIZE,
                "params": lambda m: {},
                "description": "OCR识别屏幕文字",
                "keywords": ["OCR", "识别"],
                "priority": 1
            },
            {
                "pattern": r"查找(?:屏幕上的)?文字\s*[\"「『]([^」」\']*)[」』\"]",
                "action": ActionType.OCR_FIND_TEXT,
                "params": lambda m: {"text": m.group(1)},
                "description": "查找屏幕上的文字",
                "keywords": ["查找", "文字"],
                "priority": 1
            },
            # CUA 操作 - 录制
            {
                "pattern": r"开始(?:录制|记录)(?:操作)?",
                "action": ActionType.RECORD_START,
                "params": lambda m: {},
                "description": "开始录制操作",
                "keywords": ["录制", "开始"],
                "priority": 1
            },
            {
                "pattern": r"停止(?:录制|记录)",
                "action": ActionType.RECORD_STOP,
                "params": lambda m: {},
                "description": "停止录制",
                "keywords": ["停止", "录制"],
                "priority": 1
            },
            {
                "pattern": r"(?:回放|播放)(?:录制的)?(?:操作)?",
                "action": ActionType.RECORD_PLAY,
                "params": lambda m: {},
                "description": "回放录制的操作",
                "keywords": ["回放", "播放"],
                "priority": 1
            },
        ]
        
        self.patterns.sort(key=lambda x: x.get("priority", 3))
    
    def detect(
        self,
        message: str,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> IntentResult:
        """
        检测用户消息中的意图
        
        Args:
            message: 用户消息
            session_id: 会话ID（用于上下文）
            context: 额外上下文信息
            
        Returns:
            IntentResult: 检测结果
        """
        if not message or not message.strip():
            return IntentResult(detected=False)
        
        message = message.strip()
        candidates = []
        
        rule_result = self._detect_by_rules(message)
        if rule_result:
            candidates.append(rule_result)
        
        if self._components_loaded and self.semantic_matcher:
            semantic_results = self._detect_by_semantic(message)
            candidates.extend(semantic_results)
        
        if self._components_loaded and self.fuzzy_matcher:
            fuzzy_results = self._detect_by_fuzzy(message)
            candidates.extend(fuzzy_results)
        
        if not candidates:
            return IntentResult(detected=False)
        
        merged_candidates = self._merge_candidates(candidates)
        
        if session_id and self._components_loaded and self.context_aware_detector:
            merged_candidates = self._apply_context(message, session_id, merged_candidates)
        
        if len(merged_candidates) > 1 and self._components_loaded and self.disambiguator:
            disambiguated = self.disambiguator.disambiguate(
                message,
                [(c[0], c[1], c[2]) for c in merged_candidates],
                context
            )
            
            best = merged_candidates[0]
            for c in merged_candidates:
                if c[0] == disambiguated.resolved_intent:
                    best = c
                    break
            
            return IntentResult(
                detected=True,
                action=best[0],
                params=best[2],
                description=best[3] if len(best) > 3 else "",
                confidence=disambiguated.confidence,
                confidence_level="high" if disambiguated.confidence >= 0.9 else 
                               "medium" if disambiguated.confidence >= 0.7 else "low",
                need_confirm=disambiguated.need_user_confirm,
                alternatives=disambiguated.alternatives,
                method="disambiguated"
            )
        
        best = merged_candidates[0]
        confidence = best[1]
        
        if self._components_loaded and self.confidence_evaluator:
            conf_result = self.confidence_evaluator.evaluate(
                message=message,
                match_result={"pattern": best[4] if len(best) > 4 else None},
                keywords=best[5] if len(best) > 5 else None,
                params=best[2],
                intent_name=best[0].value if hasattr(best[0], 'value') else str(best[0]),
                context=context
            )
            confidence = conf_result.score
        
        need_confirm = confidence < 0.7 or (len(best) > 6 and best[6])
        
        return IntentResult(
            detected=True,
            action=best[0],
            params=best[2],
            description=best[3] if len(best) > 3 else "",
            confidence=confidence,
            confidence_level="high" if confidence >= 0.9 else 
                           "medium" if confidence >= 0.7 else "low",
            need_confirm=need_confirm,
            alternatives=[(c[0].value if hasattr(c[0], 'value') else str(c[0]), c[1]) 
                         for c in merged_candidates[1:3]],
            method=best[6] if len(best) > 6 else "rule"
        )
    
    def _detect_by_rules(self, message: str) -> Optional[Tuple]:
        """规则匹配检测"""
        for pattern_def in self.patterns:
            pattern = pattern_def["pattern"]
            match = re.search(pattern, message, re.IGNORECASE)
            
            if match:
                action = pattern_def["action"]
                params_func = pattern_def["params"]
                description = pattern_def.get("description", "")
                keywords = pattern_def.get("keywords", [])
                need_confirm = pattern_def.get("need_confirm", False)
                
                try:
                    params = params_func(match)
                except Exception:
                    continue
                
                return (action, 0.9, params, description, pattern, keywords, "rule", need_confirm)
        
        return None
    
    def _detect_by_semantic(self, message: str) -> List[Tuple]:
        """语义匹配检测"""
        results = []
        
        try:
            matches = self.semantic_matcher.find_best_match(message, top_k=3, threshold=0.4)
            
            for match in matches:
                action_name = match.intent_name
                action = self._get_action_from_name(action_name)
                if action:
                    params = self._extract_params_for_action(message, action)
                    results.append((
                        action,
                        match.similarity,
                        params,
                        match.matched_samples[0] if match.matched_samples else "",
                        None,
                        [],
                        "semantic"
                    ))
        except Exception as e:
            logger.debug(f"语义匹配失败: {e}")
        
        return results
    
    def _detect_by_fuzzy(self, message: str) -> List[Tuple]:
        """模糊匹配检测"""
        results = []
        
        try:
            matches = self.fuzzy_matcher.fuzzy_match(message)
            
            for intent_name, confidence in matches:
                action = self._get_action_from_name(intent_name)
                if action:
                    params = self._extract_params_for_action(message, action)
                    results.append((
                        action,
                        confidence,
                        params,
                        f"模糊匹配: {intent_name}",
                        None,
                        [],
                        "fuzzy"
                    ))
        except Exception as e:
            logger.debug(f"模糊匹配失败: {e}")
        
        return results
    
    def _extract_params_for_action(self, message: str, action: ActionType) -> Dict[str, Any]:
        """根据动作类型从消息中提取参数"""
        params = {}
        
        if action == ActionType.FILE_CREATE:
            patterns = [
                r"创建(?:一个)?\s*([\w\-./]+\.\w+)",
                r"新建(?:一个)?\s*([\w\-./]+\.\w+)",
                r"生成(?:一个)?\s*([\w\-./]+\.\w+)",
                r"创建\s*([\w\-./]+)\s*(?:文件)?",
            ]
            for pattern in patterns:
                match = re.search(pattern, message)
                if match:
                    params = {"file_path": match.group(1), "content": ""}
                    break
        
        elif action == ActionType.FILE_READ:
            patterns = [
                r"读取\s*([\w\-./]+\.\w+)",
                r"打开\s*([\w\-./]+\.\w+)",
                r"查看\s*([\w\-./]+\.\w+)",
                r"显示\s*([\w\-./]+\.\w+)",
            ]
            for pattern in patterns:
                match = re.search(pattern, message)
                if match:
                    params = {"file_path": match.group(1)}
                    break
        
        elif action == ActionType.FILE_WRITE:
            patterns = [
                r"写入\s*([\w\-./]+)\s+(.+)",
                r"向\s*([\w\-./]+)\s*写入\s*(.+)",
                r"把\s*(.+)\s*写入\s*([\w\-./]+)",
            ]
            for pattern in patterns:
                match = re.search(pattern, message)
                if match:
                    if "向" in pattern:
                        params = {"file_path": match.group(1), "content": match.group(2)}
                    elif "把" in pattern:
                        params = {"file_path": match.group(2), "content": match.group(1)}
                    else:
                        params = {"file_path": match.group(1), "content": match.group(2)}
                    break
        
        elif action == ActionType.FILE_DELETE:
            patterns = [
                r"删除\s*([\w\-./]+\.\w+)",
                r"移除\s*([\w\-./]+\.\w+)",
            ]
            for pattern in patterns:
                match = re.search(pattern, message)
                if match:
                    params = {"file_path": match.group(1)}
                    break
        
        elif action == ActionType.FILE_LIST:
            patterns = [
                r"列出\s*([\w\-./]+)",
                r"显示\s*([\w\-./]+)\s*目录",
            ]
            for pattern in patterns:
                match = re.search(pattern, message)
                if match:
                    params = {"directory": match.group(1)}
                    break
            if not params:
                params = {"directory": "."}
        
        elif action == ActionType.APP_OPEN:
            patterns = [
                r"打开\s*(\S+)",
                r"启动\s*(\S+)",
            ]
            for pattern in patterns:
                match = re.search(pattern, message)
                if match:
                    params = {"app_name": match.group(1)}
                    break
        
        elif action == ActionType.URL_OPEN:
            patterns = [
                r"(https?://\S+)",
                r"打开\s*(https?://\S+)",
                r"访问\s*(https?://\S+)",
            ]
            for pattern in patterns:
                match = re.search(pattern, message)
                if match:
                    params = {"url": match.group(1)}
                    break
        
        elif action == ActionType.MOUSE_CLICK:
            patterns = [
                r"(?:点击|单击)\s*\(?(\d+)\s*[,，]\s*(\d+)\)?",
                r"右键\s*\(?(\d+)\s*[,，]\s*(\d+)\)?",
                r"双击\s*\(?(\d+)\s*[,，]\s*(\d+)\)?",
            ]
            for i, pattern in enumerate(patterns):
                match = re.search(pattern, message)
                if match:
                    params = {"x": int(match.group(1)), "y": int(match.group(2))}
                    if i == 1:
                        params["button"] = "right"
                    elif i == 2:
                        params["clicks"] = 2
                    break
        
        elif action == ActionType.MOUSE_MOVE:
            pattern = r"(?:移动|移动鼠标到)\s*\(?(\d+)\s*[,，]\s*(\d+)\)?"
            match = re.search(pattern, message)
            if match:
                params = {"x": int(match.group(1)), "y": int(match.group(2))}
        
        elif action == ActionType.KEYBOARD_TYPE:
            patterns = [
                r"(?:输入|打字)\s*[\"「『]([^」」\"]*)[」』\"]",
                r"输入\s+(.+)",
            ]
            for pattern in patterns:
                match = re.search(pattern, message)
                if match:
                    params = {"text": match.group(1)}
                    break
        
        elif action == ActionType.WINDOW_ACTIVATE:
            pattern = r"激活\s*(.+?)\s*窗口"
            match = re.search(pattern, message)
            if match:
                params = {"title": match.group(1)}
        
        elif action == ActionType.WINDOW_CLOSE:
            pattern = r"关闭\s*(.+?)\s*窗口"
            match = re.search(pattern, message)
            if match:
                params = {"title": match.group(1)}
        
        return params
    
    def _get_action_from_name(self, name: str) -> Optional[ActionType]:
        """从名称获取ActionType"""
        mapping = {
            "file_create": ActionType.FILE_CREATE,
            "file_read": ActionType.FILE_READ,
            "file_write": ActionType.FILE_WRITE,
            "file_delete": ActionType.FILE_DELETE,
            "file_list": ActionType.FILE_LIST,
            "app_open": ActionType.APP_OPEN,
            "url_open": ActionType.URL_OPEN,
            # CUA 操作
            "screenshot": ActionType.SCREENSHOT,
            "screen_info": ActionType.SCREEN_INFO,
            "mouse_click": ActionType.MOUSE_CLICK,
            "mouse_move": ActionType.MOUSE_MOVE,
            "mouse_drag": ActionType.MOUSE_DRAG,
            "mouse_scroll": ActionType.MOUSE_SCROLL,
            "mouse_position": ActionType.MOUSE_POSITION,
            "keyboard_type": ActionType.KEYBOARD_TYPE,
            "keyboard_press": ActionType.KEYBOARD_PRESS,
            "keyboard_hotkey": ActionType.KEYBOARD_HOTKEY,
            "window_list": ActionType.WINDOW_LIST,
            "window_active": ActionType.WINDOW_ACTIVE,
            "window_activate": ActionType.WINDOW_ACTIVATE,
            "window_close": ActionType.WINDOW_CLOSE,
            "window_minimize": ActionType.WINDOW_MINIMIZE,
            "window_maximize": ActionType.WINDOW_MAXIMIZE,
            "ocr_recognize": ActionType.OCR_RECOGNIZE,
            "ocr_find_text": ActionType.OCR_FIND_TEXT,
            "record_start": ActionType.RECORD_START,
            "record_stop": ActionType.RECORD_STOP,
            "record_play": ActionType.RECORD_PLAY,
        }
        return mapping.get(name)
    
    def _merge_candidates(self, candidates: List[Tuple]) -> List[Tuple]:
        """合并候选结果"""
        merged = {}
        
        for c in candidates:
            action = c[0]
            if hasattr(action, 'value'):
                key = action.value
            else:
                key = str(action)
            
            if key not in merged or c[1] > merged[key][1]:
                merged[key] = c
        
        return sorted(merged.values(), key=lambda x: x[1], reverse=True)
    
    def _apply_context(
        self,
        message: str,
        session_id: str,
        candidates: List[Tuple]
    ) -> List[Tuple]:
        """应用上下文增强"""
        enhanced = []
        
        for c in candidates:
            action = c[0]
            confidence = c[1]
            params = c[2]
            
            intent_name = action.value if hasattr(action, 'value') else str(action)
            resolved_intent, resolved_params, boost = self.context_aware_detector.detect_with_context(
                message,
                session_id,
                intent_name,
                params
            )
            
            enhanced_confidence = min(confidence + boost, 1.0)
            enhanced_params = {**params, **resolved_params} if resolved_params else params
            
            enhanced.append((
                action,
                enhanced_confidence,
                enhanced_params,
                c[3] if len(c) > 3 else "",
                c[4] if len(c) > 4 else None,
                c[5] if len(c) > 5 else [],
                c[6] if len(c) > 6 else "rule"
            ))
        
        return sorted(enhanced, key=lambda x: x[1], reverse=True)
    
    def record_feedback(
        self,
        session_id: str,
        predicted_action: ActionType,
        is_correct: bool,
        actual_action: Optional[ActionType] = None
    ):
        """记录用户反馈用于改进"""
        if self._components_loaded and self.metrics:
            predicted_name = predicted_action.value if hasattr(predicted_action, 'value') else str(predicted_action)
            actual_name = actual_action.value if actual_action and hasattr(actual_action, 'value') else None
            
            self.metrics.record(
                predicted=predicted_name,
                actual=actual_name,
                is_correct=is_correct
            )
            
            if self.confidence_evaluator:
                self.confidence_evaluator.record_result(predicted_name, is_correct)
    
    def get_metrics_report(self) -> Dict[str, Any]:
        """获取性能指标报告"""
        if self._components_loaded and self.metrics:
            return self.metrics.get_report()
        return {}
    
    async def detect_with_llm(self, message: str) -> IntentResult:
        """使用 LLM 进行意图检测（后备方案）"""
        if not self.llm_client:
            return self.detect(message)
        
        return self.detect(message)
    
    def _string_to_action(self, action_str: str) -> ActionType:
        """字符串转ActionType"""
        mapping = {
            "file_create": ActionType.FILE_CREATE,
            "file_read": ActionType.FILE_READ,
            "file_write": ActionType.FILE_WRITE,
            "file_delete": ActionType.FILE_DELETE,
            "file_list": ActionType.FILE_LIST,
            "app_open": ActionType.APP_OPEN,
            "url_open": ActionType.URL_OPEN,
        }
        return mapping.get(action_str)


def create_intent_detector(
    llm_client=None,
    use_semantic: bool = True
) -> IntentDetector:
    """创建意图检测器实例"""
    return IntentDetector(llm_client=llm_client, use_semantic=use_semantic)
