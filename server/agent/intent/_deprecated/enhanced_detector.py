"""
增强版意图检测器
支持 LLM 后备、智能错误恢复、同义词扩展
"""
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agent.agent_config import ActionType

logger = logging.getLogger(__name__)


class DetectionMethod(str, Enum):
    """检测方法"""
    RULE = "rule"
    FUZZY = "fuzzy"
    SEMANTIC = "semantic"
    LLM = "llm"
    CONTEXT = "context"


@dataclass
class EnhancedIntentResult:
    """增强版意图检测结果"""
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


class SynonymExpander:
    """同义词扩展器"""

    ACTION_SYNONYMS = {
        "创建": ["创建", "新建", "生成", "建立", "弄一个", "搞一个", "建一个", "写一个", "做一个"],
        "读取": ["读取", "查看", "打开", "显示", "看看", "读一下", "看一下", "展示", "列出"],
        "写入": ["写入", "修改", "更新", "编辑", "更改", "改一下", "更新一下", "保存"],
        "删除": ["删除", "移除", "清除", "去掉", "删掉", "卸载", "清理"],
        "列出": ["列出", "显示", "查看", "ls", "dir", "展示"],
        "打开": ["打开", "启动", "运行", "开启", "执行"],
        "关闭": ["关闭", "退出", "结束", "停止", "终止"],
        "截图": ["截图", "截屏", "截取", "拍照", "抓图"],
        "点击": ["点击", "单击", "按", "按下", "点击一下"],
        "输入": ["输入", "打字", "键入", "填写", "写入"],
    }

    @classmethod
    def expand(cls, text: str) -> list[str]:
        """扩展文本中的同义词"""
        expanded = [text]
        for _canonical, synonyms in cls.ACTION_SYNONYMS.items():
            for synonym in synonyms:
                if synonym in text:
                    for other_synonym in synonyms:
                        if other_synonym != synonym:
                            expanded.append(text.replace(synonym, other_synonym))
        return list(set(expanded))


class EnhancedIntentDetector:
    """增强版意图检测器"""

    def __init__(self):
        self.synonym_expander = SynonymExpander()
        self._init_patterns()

    def _init_patterns(self):
        """初始化规则模式"""
        self.patterns = [
            {
                "pattern": r"(?:把|将)\s*([\w\-./]+\.\w+)\s*(?:改成|修改成|内容改为)\s*(.+)",
                "action": ActionType.FILE_WRITE,
                "params": lambda m: {"file_path": m.group(1), "content": m.group(2)},
                "description": "修改文件内容",
            },
            {
                "pattern": r"创建(?:一个)?(?:新)?(?:文件)?\s*([\w\-./]+\.\w+)",
                "action": ActionType.FILE_CREATE,
                "params": lambda m: {"file_path": m.group(1), "content": ""},
                "description": "创建文件",
            },
            {
                "pattern": r"读取\s*([\w\-./]+\.\w+)",
                "action": ActionType.FILE_READ,
                "params": lambda m: {"file_path": m.group(1)},
                "description": "读取文件",
            },
            {
                "pattern": r"删除\s*([\w\-./]+\.\w+)",
                "action": ActionType.FILE_DELETE,
                "params": lambda m: {"file_path": m.group(1)},
                "description": "删除文件",
                "need_confirm": True,
            },
            {
                "pattern": r"批量删除\s*(\w+)\s*文件",
                "action": ActionType.FILE_BATCH_DELETE,
                "params": lambda m: {"pattern": f"*.{m.group(1)}", "batch": True},
                "description": "批量删除文件",
                "need_confirm": True,
            },
            {
                "pattern": r"删除所有\s*(\w+)\s*文件",
                "action": ActionType.FILE_BATCH_DELETE,
                "params": lambda m: {"pattern": f"*.{m.group(1)}", "batch": True},
                "description": "批量删除文件",
                "need_confirm": True,
            },
            {
                "pattern": r"清理\s*(\w+)\s*文件",
                "action": ActionType.FILE_BATCH_DELETE,
                "params": lambda m: {"pattern": f"*.{m.group(1)}", "batch": True},
                "description": "清理文件",
                "need_confirm": True,
            },
            {
                "pattern": r"列出\s*(\S*)\s*(?:的)?文件",
                "action": ActionType.FILE_LIST,
                "params": lambda m: {"directory": m.group(1) or "."},
                "description": "列出文件",
            },
            {
                "pattern": r"截图$",
                "action": ActionType.SCREENSHOT,
                "params": lambda _m: {},
                "description": "截取屏幕截图",
            },
            {
                "pattern": r"(?:点击|单击)\s*(?:坐标)?\s*\(?(\d+)\s*[,，]\s*(\d+)\)?",
                "action": ActionType.MOUSE_CLICK,
                "params": lambda m: {"x": int(m.group(1)), "y": int(m.group(2))},
                "description": "鼠标点击",
            },
            {
                "pattern": r"(?:输入|打字)\s*(.+)",
                "action": ActionType.KEYBOARD_TYPE,
                "params": lambda m: {"text": m.group(1)},
                "description": "键盘输入",
            },
            {
                "pattern": r"(?:列出|显示)(?:所有)?窗口",
                "action": ActionType.WINDOW_LIST,
                "params": lambda _m: {},
                "description": "列出所有窗口",
            },
            {
                "pattern": r"(?:识别|OCR)(?:屏幕上的)?文字",
                "action": ActionType.OCR_RECOGNIZE,
                "params": lambda _m: {},
                "description": "OCR识别文字",
            },
        ]

    def detect(self, message: str, context: dict[str, Any] = None) -> EnhancedIntentResult:
        """检测意图"""
        context = context or {}

        expanded_texts = self.synonym_expander.expand(message)

        for text in expanded_texts:
            for pattern_def in self.patterns:
                match = re.search(pattern_def["pattern"], text, re.IGNORECASE)
                if match:
                    params = pattern_def["params"](match)
                    return EnhancedIntentResult(
                        detected=True,
                        action=pattern_def["action"],
                        params=params,
                        description=pattern_def["description"],
                        confidence=0.9,
                        method=DetectionMethod.RULE,
                        need_confirm=pattern_def.get("need_confirm", False),
                    )

        return EnhancedIntentResult(
            detected=False,
            confidence=0.0,
            suggestions=["请尝试更明确的指令，如'创建test.txt'或'读取config.json'"]
        )


def create_enhanced_detector() -> EnhancedIntentDetector:
    """创建增强版意图检测器"""
    return EnhancedIntentDetector()


EnhancedIntentDetector = EnhancedIntentDetector
