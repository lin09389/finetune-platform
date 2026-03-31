"""
Agent 意图检测器
从用户消息中识别操作意图
"""
import logging
import platform
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_desktop_path() -> str:
    """获取桌面路径"""
    system = platform.system()
    if system == "Windows" or system == "Darwin":
        return str(Path.home() / "Desktop")
    else:
        return str(Path.home() / "Desktop")


class ActionType(str, Enum):
    """操作类型"""
    FILE_CREATE = "file_create"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    FILE_LIST = "file_list"
    APP_OPEN = "app_open"
    URL_OPEN = "url_open"
    SCREENSHOT = "screenshot"
    MOUSE_CLICK = "mouse_click"
    MOUSE_MOVE = "mouse_move"
    KEYBOARD_TYPE = "keyboard_type"
    KEYBOARD_PRESS = "keyboard_press"


@dataclass
class IntentResult:
    """意图检测结果"""
    detected: bool
    action: ActionType | None = None
    params: dict[str, Any] | None = None
    description: str = ""
    need_confirm: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected": self.detected,
            "action": self.action.value if self.action else None,
            "params": self.params,
            "description": self.description,
            "need_confirm": self.need_confirm,
        }


class IntentDetector:
    """意图检测器"""

    PATTERNS = [
        {
            "patterns": [
                r"创建\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"新建\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"生成\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"建立一个\s*[\"']?([\w\-./]+)[\"']?",
                r"创建\s*([\w\-./]+\.[a-zA-Z]+)\s*文件",
                r"写一个\s*([\w\-./]+\.[a-zA-Z]+)",
                r"编写\s*([\w\-./]+\.[a-zA-Z]+)",
            ],
            "action": ActionType.FILE_CREATE,
            "description": "创建文件",
            "param_key": "file_path",
            "need_confirm": False,
        },
        {
            "patterns": [
                r"读取\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"打开\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"查看\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"显示\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"读一下\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
            ],
            "action": ActionType.FILE_READ,
            "description": "读取文件",
            "param_key": "file_path",
            "need_confirm": False,
        },
        {
            "patterns": [
                r"写入\s*[\"']?([\w\-./]+)[\"']?",
                r"修改\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"更新\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"把\s*[\"']?([\w\-./]+)[\"']?\s*改成",
                r"编辑\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"保存\s*到\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"保存\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"帮我保存\s*到\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"请保存\s*到\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"存\s*到\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
            ],
            "action": ActionType.FILE_WRITE,
            "description": "保存文件",
            "param_key": "file_path",
            "need_confirm": False,
        },
        {
            "patterns": [
                r"删除\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"移除\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
                r"清除\s*[\"']?([\w\-./]+\.[a-zA-Z]+)[\"']?",
            ],
            "action": ActionType.FILE_DELETE,
            "description": "删除文件",
            "param_key": "file_path",
            "need_confirm": True,
        },
        {
            "patterns": [
                r"列出\s*([\w\-./]*)\s*(?:下)?(?:文件|目录)?",
                r"显示\s*([\w\-./]*)\s*(?:下)?(?:文件|目录)?",
                r"ls\s*([\w\-./]*)",
                r"查看\s*([\w\-./]*)\s*目录",
                r"有哪些文件",
            ],
            "action": ActionType.FILE_LIST,
            "description": "列出文件",
            "param_key": "directory",
            "need_confirm": False,
        },
        {
            "patterns": [
                r"打开\s*(VS\s*Code|Visual\s*Studio\s*Code)",
                r"启动\s*(VS\s*Code|Visual\s*Studio\s*Code)",
                r"打开\s*(记事本|Notepad)",
                r"打开\s*(Chrome|谷歌浏览器)",
                r"打开\s*(Edge|edge)",
                r"打开\s*(计算器|Calculator)",
                r"启动\s*(计算器|Calculator)",
                r"打开\s*([\w\s]+?)(?:应用|软件|程序)?$",
            ],
            "action": ActionType.APP_OPEN,
            "description": "打开应用",
            "param_key": "app_name",
            "need_confirm": False,
        },
        {
            "patterns": [
                r"打开\s*(https?://\S+)",
                r"访问\s*(https?://\S+)",
                r"(https?://\S+)",
            ],
            "action": ActionType.URL_OPEN,
            "description": "打开网址",
            "param_key": "url",
            "need_confirm": False,
        },
        {
            "patterns": [
                r"截图",
                r"截屏",
                r"截取屏幕",
            ],
            "action": ActionType.SCREENSHOT,
            "description": "截取屏幕",
            "param_key": None,
            "need_confirm": False,
        },
    ]

    def __init__(self):
        self._compiled_patterns = []
        for pattern_config in self.PATTERNS:
            for pattern in pattern_config["patterns"]:
                try:
                    self._compiled_patterns.append({
                        "regex": re.compile(pattern, re.IGNORECASE),
                        "config": pattern_config,
                    })
                except re.error as e:
                    logger.warning(f"Invalid pattern {pattern}: {e}")

    def detect(self, message: str, context: dict[str, Any] | None = None) -> IntentResult:
        """
        检测消息中的意图
        
        Args:
            message: 用户消息
            context: 上下文信息（如当前对话内容、生成的文本等）
            
        Returns:
            IntentResult: 检测结果
        """
        message = message.strip()

        if not message:
            return IntentResult(detected=False)

        save_to_desktop_patterns = [
            r"保存\s*到\s*桌面",
            r"存\s*到\s*桌面",
            r"帮我保存\s*到\s*桌面",
            r"请保存\s*到\s*桌面",
            r"保存.*到\s*桌面",
        ]

        for pattern in save_to_desktop_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                filename_match = re.search(r'保存\s*(\S+)\s*到\s*桌面', message)
                if not filename_match:
                    filename_match = re.search(r'把\s*(\S+)\s*保存\s*到\s*桌面', message)

                filename = filename_match.group(1) if filename_match else None

                if not filename:
                    if context and context.get("generated_filename"):
                        filename = context["generated_filename"]
                    elif context and context.get("content_type"):
                        content_type = context["content_type"]
                        if "作文" in content_type or "文章" in content_type:
                            filename = "作文.txt"
                        elif "代码" in content_type:
                            filename = "code.txt"
                        else:
                            filename = "content.txt"
                    else:
                        filename = "content.txt"

                desktop_path = get_desktop_path()
                full_path = str(Path(desktop_path) / filename)

                content = ""
                if context and context.get("content"):
                    content = context["content"]
                else:
                    content_match = re.search(r'[:：]\s*(.+)$', message, re.DOTALL)
                    if content_match:
                        content = content_match.group(1).strip()

                return IntentResult(
                    detected=True,
                    action=ActionType.FILE_WRITE,
                    params={
                        "file_path": full_path,
                        "content": content,
                        "is_desktop": True,
                    },
                    description=f"保存文件到桌面: {filename}",
                    need_confirm=False,
                )

        for item in self._compiled_patterns:
            match = item["regex"].search(message)
            if match:
                config = item["config"]

                params = {}
                if config.get("param_key") and match.groups():
                    file_path = match.group(1).strip('"\'')

                    if "桌面" in file_path:
                        desktop_path = get_desktop_path()
                        file_path = file_path.replace("桌面", desktop_path)
                        params["is_desktop"] = True

                    params[config["param_key"]] = file_path

                if config["action"] == ActionType.FILE_WRITE:
                    content_match = re.search(r'[:：]\s*(.+)$', message, re.DOTALL)
                    if content_match:
                        params["content"] = content_match.group(1).strip()
                    elif context and context.get("content"):
                        params["content"] = context["content"]

                if config["action"] == ActionType.FILE_CREATE:
                    content_match = re.search(r'[:：]\s*(.+)$', message, re.DOTALL)
                    if content_match:
                        params["content"] = content_match.group(1).strip()

                return IntentResult(
                    detected=True,
                    action=config["action"],
                    params=params,
                    description=config["description"],
                    need_confirm=config.get("need_confirm", False),
                )

        return IntentResult(detected=False)


_intent_detector: IntentDetector | None = None


def get_intent_detector() -> IntentDetector:
    """获取意图检测器实例"""
    global _intent_detector
    if _intent_detector is None:
        _intent_detector = IntentDetector()
    return _intent_detector
