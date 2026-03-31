"""
意图检测核心组件 - 统一规则模式库

整合所有检测器的规则模式，消除重复定义
"""
import hashlib
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from ..models import IntentCategory, IntentDefinition


@dataclass
class PatternRule:
    pattern: str
    action: str
    params_extractor: Callable
    description: str
    keywords: list[str]
    priority: int
    category: IntentCategory
    dangerous: bool = False
    need_confirm: bool = False
    need_context: bool = False
    compiled_pattern: re.Pattern | None = None

    def __post_init__(self):
        if self.compiled_pattern is None:
            self.compiled_pattern = re.compile(self.pattern, re.IGNORECASE)


_last_md5 = ""
_last_check_time = 0
_lock = threading.Lock()


def _get_file_md5():
    try:
        with open(__file__, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception:
        return ""


def check_reload():
    """检查并重新加载规则"""
    global _last_md5, _last_check_time
    now = time.time()
    if now - _last_check_time < 10:  # 每 10s 检查一次
        return

    current_md5 = _get_file_md5()
    if current_md5 != _last_md5:
        with _lock:
            # 在实际项目中，这里通常会加载一个外部 JSON/YAML 文件
            # 对于 Python 文件，我们需要一种方式来重新初始化全局变量
            # 这里的简单实现假设外部代码会调用此函数，并根据结果刷新引用
            _last_md5 = current_md5
            _last_check_time = now
            return True
    return False


INTENT_PATTERNS: dict[str, IntentDefinition] = {
    "file_create": IntentDefinition(
        intent_type="file_create",
        action="file_create",
        description="创建新文件",
        category=IntentCategory.FILE_OPERATION,
        required_params=["file_path"],
        optional_params=["content"],
        keywords=["创建", "新建", "生成", "建立", "写", "做", "建"],
        dangerous=False,
        priority=1
    ),
    "file_read": IntentDefinition(
        intent_type="file_read",
        action="file_read",
        description="读取文件内容",
        category=IntentCategory.FILE_OPERATION,
        required_params=["file_path"],
        keywords=["读取", "查看", "打开", "显示", "看", "读"],
        dangerous=False,
        priority=1
    ),
    "file_write": IntentDefinition(
        intent_type="file_write",
        action="file_write",
        description="写入或修改文件",
        category=IntentCategory.FILE_OPERATION,
        required_params=["file_path"],
        optional_params=["content"],
        keywords=["写入", "修改", "更新", "编辑", "保存", "存"],
        dangerous=False,
        priority=1
    ),
    "file_delete": IntentDefinition(
        intent_type="file_delete",
        action="file_delete",
        description="删除文件",
        category=IntentCategory.FILE_OPERATION,
        required_params=["file_path"],
        keywords=["删除", "移除", "清除", "删掉"],
        dangerous=True,
        priority=1
    ),
    "file_list": IntentDefinition(
        intent_type="file_list",
        action="file_list",
        description="列出目录文件",
        category=IntentCategory.FILE_OPERATION,
        required_params=[],
        optional_params=["directory"],
        keywords=["列出", "显示", "查看", "ls", "dir", "目录"],
        dangerous=False,
        priority=1
    ),
    "file_copy": IntentDefinition(
        intent_type="file_copy",
        action="file_copy",
        description="复制文件",
        category=IntentCategory.FILE_OPERATION,
        required_params=["source", "destination"],
        keywords=["复制", "拷贝"],
        dangerous=False,
        priority=1
    ),
    "file_move": IntentDefinition(
        intent_type="file_move",
        action="file_move",
        description="移动文件",
        category=IntentCategory.FILE_OPERATION,
        required_params=["source", "destination"],
        keywords=["移动", "转移"],
        dangerous=False,
        priority=1
    ),
    "file_rename": IntentDefinition(
        intent_type="file_rename",
        action="file_rename",
        description="重命名文件",
        category=IntentCategory.FILE_OPERATION,
        required_params=["old_name", "new_name"],
        keywords=["重命名", "改名"],
        dangerous=False,
        priority=1
    ),
    "file_search": IntentDefinition(
        intent_type="file_search",
        action="file_search",
        description="搜索文件",
        category=IntentCategory.FILE_OPERATION,
        required_params=["pattern"],
        keywords=["搜索", "查找", "寻找"],
        dangerous=False,
        priority=1
    ),
    "file_batch_delete": IntentDefinition(
        intent_type="file_batch_delete",
        action="file_batch_delete",
        description="批量删除文件",
        category=IntentCategory.FILE_OPERATION,
        required_params=["pattern"],
        keywords=["批量删除", "删除所有", "清理"],
        dangerous=True,
        priority=1
    ),
    "app_open": IntentDefinition(
        intent_type="app_open",
        action="app_open",
        description="打开应用程序",
        category=IntentCategory.APP_CONTROL,
        required_params=["app_name"],
        keywords=["打开", "启动", "运行", "开启"],
        dangerous=False,
        priority=1
    ),
    "app_close": IntentDefinition(
        intent_type="app_close",
        action="app_close",
        description="关闭应用程序",
        category=IntentCategory.APP_CONTROL,
        required_params=["app_name"],
        keywords=["关闭", "退出"],
        dangerous=False,
        priority=1
    ),
    "url_open": IntentDefinition(
        intent_type="url_open",
        action="url_open",
        description="打开网址",
        category=IntentCategory.BROWSER_OPERATION,
        required_params=["url"],
        keywords=["打开", "访问", "http", "https", "网址"],
        dangerous=False,
        priority=0
    ),
    "screenshot": IntentDefinition(
        intent_type="screenshot",
        action="screenshot",
        description="截取屏幕",
        category=IntentCategory.CUA_OPERATION,
        required_params=[],
        optional_params=["monitor"],
        keywords=["截图", "截屏", "截取"],
        dangerous=False,
        priority=0
    ),
    "mouse_click": IntentDefinition(
        intent_type="mouse_click",
        action="mouse_click",
        description="鼠标点击",
        category=IntentCategory.CUA_OPERATION,
        required_params=["x", "y"],
        optional_params=["button", "clicks"],
        keywords=["点击", "单击", "双击", "右键"],
        dangerous=False,
        priority=1
    ),
    "mouse_move": IntentDefinition(
        intent_type="mouse_move",
        action="mouse_move",
        description="移动鼠标",
        category=IntentCategory.CUA_OPERATION,
        required_params=["x", "y"],
        keywords=["移动", "移动鼠标"],
        dangerous=False,
        priority=1
    ),
    "mouse_position": IntentDefinition(
        intent_type="mouse_position",
        action="mouse_position",
        description="获取鼠标位置",
        category=IntentCategory.CUA_OPERATION,
        required_params=[],
        keywords=["鼠标", "位置", "光标"],
        dangerous=False,
        priority=1
    ),
    "keyboard_type": IntentDefinition(
        intent_type="keyboard_type",
        action="keyboard_type",
        description="键盘输入",
        category=IntentCategory.CUA_OPERATION,
        required_params=["text"],
        keywords=["输入", "打字", "键盘"],
        dangerous=False,
        priority=1
    ),
    "keyboard_press": IntentDefinition(
        intent_type="keyboard_press",
        action="keyboard_press",
        description="按下按键",
        category=IntentCategory.CUA_OPERATION,
        required_params=["key"],
        keywords=["按下", "按键"],
        dangerous=False,
        priority=1
    ),
    "keyboard_hotkey": IntentDefinition(
        intent_type="keyboard_hotkey",
        action="keyboard_hotkey",
        description="按下组合键",
        category=IntentCategory.CUA_OPERATION,
        required_params=["keys"],
        keywords=["组合键", "快捷键"],
        dangerous=False,
        priority=1
    ),
    "window_list": IntentDefinition(
        intent_type="window_list",
        action="window_list",
        description="列出所有窗口",
        category=IntentCategory.CUA_OPERATION,
        required_params=[],
        keywords=["窗口", "列出"],
        dangerous=False,
        priority=1
    ),
    "window_active": IntentDefinition(
        intent_type="window_active",
        action="window_active",
        description="获取活动窗口",
        category=IntentCategory.CUA_OPERATION,
        required_params=[],
        keywords=["当前窗口", "活动窗口"],
        dangerous=False,
        priority=1
    ),
    "window_activate": IntentDefinition(
        intent_type="window_activate",
        action="window_activate",
        description="激活窗口",
        category=IntentCategory.CUA_OPERATION,
        required_params=["title"],
        keywords=["激活", "切换", "转到"],
        dangerous=False,
        priority=1
    ),
    "window_close": IntentDefinition(
        intent_type="window_close",
        action="window_close",
        description="关闭窗口",
        category=IntentCategory.CUA_OPERATION,
        required_params=["title"],
        keywords=["关闭"],
        dangerous=False,
        priority=1
    ),
    "window_minimize": IntentDefinition(
        intent_type="window_minimize",
        action="window_minimize",
        description="最小化窗口",
        category=IntentCategory.CUA_OPERATION,
        required_params=["title"],
        keywords=["最小化"],
        dangerous=False,
        priority=1
    ),
    "window_maximize": IntentDefinition(
        intent_type="window_maximize",
        action="window_maximize",
        description="最大化窗口",
        category=IntentCategory.CUA_OPERATION,
        required_params=["title"],
        keywords=["最大化"],
        dangerous=False,
        priority=1
    ),
    "ocr_recognize": IntentDefinition(
        intent_type="ocr_recognize",
        action="ocr_recognize",
        description="OCR识别文字",
        category=IntentCategory.CUA_OPERATION,
        required_params=[],
        keywords=["OCR", "识别", "文字"],
        dangerous=False,
        priority=1
    ),
    "ocr_find_text": IntentDefinition(
        intent_type="ocr_find_text",
        action="ocr_find_text",
        description="查找屏幕文字",
        category=IntentCategory.CUA_OPERATION,
        required_params=["text"],
        keywords=["查找", "文字"],
        dangerous=False,
        priority=1
    ),
    "record_start": IntentDefinition(
        intent_type="record_start",
        action="record_start",
        description="开始录制操作",
        category=IntentCategory.CUA_OPERATION,
        required_params=[],
        keywords=["录制", "开始"],
        dangerous=False,
        priority=1
    ),
    "record_stop": IntentDefinition(
        intent_type="record_stop",
        action="record_stop",
        description="停止录制",
        category=IntentCategory.CUA_OPERATION,
        required_params=[],
        keywords=["停止", "录制"],
        dangerous=False,
        priority=1
    ),
    "record_play": IntentDefinition(
        intent_type="record_play",
        action="record_play",
        description="回放录制的操作",
        category=IntentCategory.CUA_OPERATION,
        required_params=[],
        keywords=["回放", "播放"],
        dangerous=False,
        priority=1
    ),
    "system_info": IntentDefinition(
        intent_type="system_info",
        action="system_info",
        description="获取系统信息",
        category=IntentCategory.SYSTEM_OPERATION,
        required_params=[],
        keywords=["系统", "信息", "配置", "状态"],
        dangerous=False,
        priority=1
    ),
    "hardware_monitor": IntentDefinition(
        intent_type="hardware_monitor",
        action="hardware_monitor",
        description="硬件监控",
        category=IntentCategory.SYSTEM_OPERATION,
        required_params=["component"],
        keywords=["CPU", "内存", "磁盘", "网络"],
        dangerous=False,
        priority=1
    ),
    "process_list": IntentDefinition(
        intent_type="process_list",
        action="process_list",
        description="列出进程",
        category=IntentCategory.SYSTEM_OPERATION,
        required_params=[],
        keywords=["进程", "任务"],
        dangerous=False,
        priority=1
    ),
}


RULE_PATTERNS: list[PatternRule] = [
    PatternRule(
        pattern=r"^(你好|您好|hi|hello|hey|嗨|哈喽|早上好|下午好|晚上好)[\s!！.。]*$",
        action="conversation",
        params_extractor=lambda m: {},
        description="问候",
        keywords=["你好", "hello", "hi"],
        priority=0,
        category=IntentCategory.CONVERSATION
    ),
    PatternRule(
        pattern=r"^(谢谢|感谢|多谢|thanks|thank you)[\s!！.。]*$",
        action="conversation",
        params_extractor=lambda m: {},
        description="感谢",
        keywords=["谢谢", "thanks"],
        priority=0,
        category=IntentCategory.CONVERSATION
    ),
    PatternRule(
        pattern=r"^(再见|拜拜|bye|goodbye|下次见)[\s!！.。]*$",
        action="conversation",
        params_extractor=lambda m: {},
        description="告别",
        keywords=["再见", "bye"],
        priority=0,
        category=IntentCategory.CONVERSATION
    ),
    PatternRule(
        pattern=r"^(你是谁|你叫什么|你的名字|自我介绍)",
        action="conversation",
        params_extractor=lambda m: {},
        description="自我介绍询问",
        keywords=["你是谁", "名字"],
        priority=0,
        category=IntentCategory.CONVERSATION
    ),
    PatternRule(
        pattern=r"^(你能做什么|你会什么|你的功能|你能帮我)",
        action="conversation",
        params_extractor=lambda m: {},
        description="能力询问",
        keywords=["功能", "能力"],
        priority=0,
        category=IntentCategory.CONVERSATION
    ),
    PatternRule(
        pattern=r"^(我想问|请问|问一下|请教)",
        action="conversation",
        params_extractor=lambda m: {},
        description="提问",
        keywords=["问", "请问"],
        priority=0,
        category=IntentCategory.CONVERSATION
    ),
    PatternRule(
        pattern=r"^(帮我|帮我看看|帮我查|帮我找)(?!.*(?:文件|目录|应用|软件|程序))",
        action="conversation",
        params_extractor=lambda m: {},
        description="请求帮助",
        keywords=["帮我"],
        priority=0,
        category=IntentCategory.CONVERSATION
    ),
    PatternRule(
        pattern=r"创建(?:一个)?(?:新)?(?:文件)?\s*([\w\-./]+\.\w+)",
        action="file_create",
        params_extractor=lambda m: {"file_path": m.group(1), "content": ""},
        description="创建文件",
        keywords=["创建", "新建"],
        priority=1,
        category=IntentCategory.FILE_OPERATION
    ),
    PatternRule(
        pattern=r"新建(?:一个)?(?:新)?(?:文件)?\s*([\w\-./]+\.\w+)",
        action="file_create",
        params_extractor=lambda m: {"file_path": m.group(1), "content": ""},
        description="新建文件",
        keywords=["新建"],
        priority=1,
        category=IntentCategory.FILE_OPERATION
    ),
    PatternRule(
        pattern=r"读取\s*([\w\-./]+\.\w+)",
        action="file_read",
        params_extractor=lambda m: {"file_path": m.group(1)},
        description="读取文件",
        keywords=["读取", "查看"],
        priority=1,
        category=IntentCategory.FILE_OPERATION
    ),
    PatternRule(
        pattern=r"读取\s*(?:文件|文档)\s*([\w\-./]+\.\w+)",
        action="file_read",
        params_extractor=lambda m: {"file_path": m.group(1)},
        description="读取文件",
        keywords=["读取", "文件"],
        priority=1,
        category=IntentCategory.FILE_OPERATION
    ),
    PatternRule(
        pattern=r"(?:读取|查看|打开)\s*(?:一下)?(?:这个)?(?:文件|文档)?\s*([\w\-./]+\.\w+)",
        action="file_read",
        params_extractor=lambda m: {"file_path": m.group(1)},
        description="读取文件",
        keywords=["读取", "查看", "打开"],
        priority=1,
        category=IntentCategory.FILE_OPERATION
    ),
    PatternRule(
        pattern=r"打开\s*([\w\-./]+\.\w+)",
        action="file_read",
        params_extractor=lambda m: {"file_path": m.group(1)},
        description="打开文件",
        keywords=["打开"],
        priority=1,
        category=IntentCategory.FILE_OPERATION
    ),
    PatternRule(
        pattern=r"查看\s*([\w\-./]+\.\w+)",
        action="file_read",
        params_extractor=lambda m: {"file_path": m.group(1)},
        description="查看文件",
        keywords=["查看"],
        priority=1,
        category=IntentCategory.FILE_OPERATION
    ),
    PatternRule(
        pattern=r"查看\s*(?:文件|文档)\s*([\w\-./]+\.\w+)",
        action="file_read",
        params_extractor=lambda m: {"file_path": m.group(1)},
        description="查看文件",
        keywords=["查看", "文件"],
        priority=1,
        category=IntentCategory.FILE_OPERATION
    ),
    PatternRule(
        pattern=r"(?:把|将)\s*([\w\-./]+\.\w+)\s*(?:改成|修改成|内容改为)\s*[\"「『]([^」」\']*)[」』\"]",
        action="file_write",
        params_extractor=lambda m: {"file_path": m.group(1), "content": m.group(2)},
        description="修改文件内容",
        keywords=["改成", "修改"],
        priority=1,
        category=IntentCategory.FILE_OPERATION
    ),
    PatternRule(
        pattern=r"(?:在|向)\s*([\w\-./]+\.\w+)\s*(?:中|里)?(?:写入|添加|追加)\s*[\"「『]([^」」\']*)[」』\"]",
        action="file_write",
        params_extractor=lambda m: {"file_path": m.group(1), "content": m.group(2)},
        description="写入文件",
        keywords=["写入", "添加"],
        priority=1,
        category=IntentCategory.FILE_OPERATION
    ),
    PatternRule(
        pattern=r"删除\s*([\w\-./]+\.\w+)",
        action="file_delete",
        params_extractor=lambda m: {"file_path": m.group(1)},
        description="删除文件",
        keywords=["删除", "移除"],
        priority=1,
        category=IntentCategory.FILE_OPERATION,
        dangerous=True,
        need_confirm=True
    ),
    PatternRule(
        pattern=r"删除\s*(?:所有|全部)?\s*\*\.(\w+)",
        action="file_batch_delete",
        params_extractor=lambda m: {"pattern": f"*.{m.group(1)}", "batch": True},
        description="批量删除文件",
        keywords=["删除", "所有", "全部"],
        priority=1,
        category=IntentCategory.FILE_OPERATION,
        dangerous=True,
        need_confirm=True
    ),
    PatternRule(
        pattern=r"(?:列出|显示|查看)?(?:当前)?目录",
        action="file_list",
        params_extractor=lambda m: {},
        description="列出目录",
        keywords=["目录", "列出"],
        priority=1,
        category=IntentCategory.FILE_OPERATION
    ),
    PatternRule(
        pattern=r"ls\s*(\S*)",
        action="file_list",
        params_extractor=lambda m: {"directory": m.group(1) or "."},
        description="列出目录",
        keywords=["ls"],
        priority=1,
        category=IntentCategory.FILE_OPERATION
    ),
    PatternRule(
        pattern=r"(?:复制|拷贝)\s*([\w\-./]+\.\w+)\s*(?:到|至)\s*([\w\-./]+)",
        action="file_copy",
        params_extractor=lambda m: {"source": m.group(1), "destination": m.group(2)},
        description="复制文件",
        keywords=["复制", "拷贝"],
        priority=1,
        category=IntentCategory.FILE_OPERATION
    ),
    PatternRule(
        pattern=r"(?:移动|转移)\s*([\w\-./]+\.\w+)\s*(?:到|至)\s*([\w\-./]+)",
        action="file_move",
        params_extractor=lambda m: {"source": m.group(1), "destination": m.group(2)},
        description="移动文件",
        keywords=["移动", "转移"],
        priority=1,
        category=IntentCategory.FILE_OPERATION
    ),
    PatternRule(
        pattern=r"(?:重命名|改名)\s*([\w\-./]+\.\w+)\s*(?:为|改成)?\s*([\w\-./]+\.\w+)",
        action="file_rename",
        params_extractor=lambda m: {"old_name": m.group(1), "new_name": m.group(2)},
        description="重命名文件",
        keywords=["重命名", "改名"],
        priority=1,
        category=IntentCategory.FILE_OPERATION
    ),
    PatternRule(
        pattern=r"(?:搜索|查找|寻找)\s*(?:文件)?\s*([\w\-*?]+)",
        action="file_search",
        params_extractor=lambda m: {"pattern": m.group(1)},
        description="搜索文件",
        keywords=["搜索", "查找"],
        priority=1,
        category=IntentCategory.FILE_OPERATION
    ),
    PatternRule(
        pattern=r"打开\s*(VS\s*Code|Visual\s*Studio\s*Code)",
        action="app_open",
        params_extractor=lambda m: {"app_name": "vscode"},
        description="打开 VS Code",
        keywords=["VS Code", "VSCode"],
        priority=1,
        category=IntentCategory.APP_CONTROL
    ),
    PatternRule(
        pattern=r"打开\s*(记事本|Notepad)",
        action="app_open",
        params_extractor=lambda m: {"app_name": "notepad"},
        description="打开记事本",
        keywords=["记事本", "Notepad"],
        priority=1,
        category=IntentCategory.APP_CONTROL
    ),
    PatternRule(
        pattern=r"打开\s*(Chrome|谷歌浏览器)",
        action="app_open",
        params_extractor=lambda m: {"app_name": "chrome"},
        description="打开 Chrome",
        keywords=["Chrome", "谷歌"],
        priority=1,
        category=IntentCategory.APP_CONTROL
    ),
    PatternRule(
        pattern=r"打开\s*(Edge|edge)",
        action="app_open",
        params_extractor=lambda m: {"app_name": "edge"},
        description="打开 Edge",
        keywords=["Edge"],
        priority=1,
        category=IntentCategory.APP_CONTROL
    ),
    PatternRule(
        pattern=r"打开\s*(微信|WeChat)",
        action="app_open",
        params_extractor=lambda m: {"app_name": "wechat"},
        description="打开微信",
        keywords=["微信", "WeChat"],
        priority=1,
        category=IntentCategory.APP_CONTROL
    ),
    PatternRule(
        pattern=r"打开\s*(钉钉|DingTalk)",
        action="app_open",
        params_extractor=lambda m: {"app_name": "dingtalk"},
        description="打开钉钉",
        keywords=["钉钉", "DingTalk"],
        priority=1,
        category=IntentCategory.APP_CONTROL
    ),
    PatternRule(
        pattern=r"打开\s*(QQ|腾讯QQ)",
        action="app_open",
        params_extractor=lambda m: {"app_name": "qq"},
        description="打开 QQ",
        keywords=["QQ", "腾讯QQ"],
        priority=1,
        category=IntentCategory.APP_CONTROL
    ),
    PatternRule(
        pattern=r"打开\s*(.+?)(?:应用|软件|程序)?$",
        action="app_open",
        params_extractor=lambda m: {"app_name": m.group(1).lower().replace(" ", "")},
        description="打开应用",
        keywords=["打开", "启动"],
        priority=2,
        category=IntentCategory.APP_CONTROL
    ),
    PatternRule(
        pattern=r"(https?://\S+)",
        action="url_open",
        params_extractor=lambda m: {"url": m.group(1)},
        description="打开网址",
        keywords=["http", "https"],
        priority=0,
        category=IntentCategory.BROWSER_OPERATION
    ),
    PatternRule(
        pattern=r"(?:访问|打开)\s*(?:网址|网站|链接)?\s*(https?://\S+)",
        action="url_open",
        params_extractor=lambda m: {"url": m.group(1)},
        description="打开网址",
        keywords=["访问", "网址"],
        priority=1,
        category=IntentCategory.BROWSER_OPERATION
    ),
    PatternRule(
        pattern=r"截图$",
        action="screenshot",
        params_extractor=lambda m: {"monitor": 0},
        description="截取屏幕截图",
        keywords=["截图", "截屏"],
        priority=0,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"截屏$",
        action="screenshot",
        params_extractor=lambda m: {"monitor": 0},
        description="截屏",
        keywords=["截屏"],
        priority=0,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"截个屏$",
        action="screenshot",
        params_extractor=lambda m: {"monitor": 0},
        description="截屏",
        keywords=["截屏"],
        priority=0,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"(?:截取|拍)(?:一张)?(?:屏幕)?截图",
        action="screenshot",
        params_extractor=lambda m: {"monitor": 0},
        description="截取屏幕截图",
        keywords=["截图", "截屏"],
        priority=0,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"(?:点击|单击)\s*(?:坐标)?\s*\(?(\d+)\s*[,，]\s*(\d+)\)?",
        action="mouse_click",
        params_extractor=lambda m: {"x": int(m.group(1)), "y": int(m.group(2)), "button": "left"},
        description="鼠标点击",
        keywords=["点击", "单击"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"双击\s*(?:坐标)?\s*\(?(\d+)\s*[,，]\s*(\d+)\)?",
        action="mouse_click",
        params_extractor=lambda m: {"x": int(m.group(1)), "y": int(m.group(2)), "clicks": 2},
        description="鼠标双击",
        keywords=["双击"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"右键(?:点击)?\s*(?:坐标)?\s*\(?(\d+)\s*[,，]\s*(\d+)\)?",
        action="mouse_click",
        params_extractor=lambda m: {"x": int(m.group(1)), "y": int(m.group(2)), "button": "right"},
        description="鼠标右键点击",
        keywords=["右键"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"(?:移动|移动鼠标到)\s*(?:坐标)?\s*\(?(\d+)\s*[,，]\s*(\d+)\)?",
        action="mouse_move",
        params_extractor=lambda m: {"x": int(m.group(1)), "y": int(m.group(2))},
        description="移动鼠标",
        keywords=["移动"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"(?:鼠标|光标)(?:现在)?(?:在)?哪里",
        action="mouse_position",
        params_extractor=lambda m: {},
        description="获取鼠标位置",
        keywords=["鼠标", "位置"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"(?:输入|打字)\s*[\"「『]([^」」\']*)[」』\"]",
        action="keyboard_type",
        params_extractor=lambda m: {"text": m.group(1)},
        description="键盘输入",
        keywords=["输入", "打字"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"(?:输入|打字)\s*(.+)",
        action="keyboard_type",
        params_extractor=lambda m: {"text": m.group(1)},
        description="键盘输入",
        keywords=["输入", "打字"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"按下\s*(\S+)\s*键",
        action="keyboard_press",
        params_extractor=lambda m: {"key": m.group(1)},
        description="按下按键",
        keywords=["按下", "键"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"(?:按下|按)\s*([A-Za-z0-9]+)\s*(?:和|加|\\+)\s*([A-Za-z0-9]+)\s*键",
        action="keyboard_hotkey",
        params_extractor=lambda m: {"keys": [m.group(1), m.group(2)]},
        description="按下组合键",
        keywords=["组合键", "快捷键"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"(?:列出|显示)(?:所有)?(?:打开的)?窗口",
        action="window_list",
        params_extractor=lambda m: {},
        description="列出所有窗口",
        keywords=["窗口", "列出"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"(?:当前|活动)(?:的)?窗口(?:是什么|是啥)",
        action="window_active",
        params_extractor=lambda m: {},
        description="获取活动窗口",
        keywords=["当前窗口", "活动窗口"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"激活\s*(.+?)\s*窗口",
        action="window_activate",
        params_extractor=lambda m: {"title": m.group(1)},
        description="激活窗口",
        keywords=["激活"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"(?:切换|转到)\s*(?:到)?\s*(.+?)\s*窗口",
        action="window_activate",
        params_extractor=lambda m: {"title": m.group(1)},
        description="切换窗口",
        keywords=["切换", "转到"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"关闭\s*(.+?)\s*窗口",
        action="window_close",
        params_extractor=lambda m: {"title": m.group(1)},
        description="关闭窗口",
        keywords=["关闭"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"(?:最小化|最小)\s*(.+?)\s*窗口",
        action="window_minimize",
        params_extractor=lambda m: {"title": m.group(1)},
        description="最小化窗口",
        keywords=["最小化"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"(?:最大化|最大)\s*(.+?)\s*窗口",
        action="window_maximize",
        params_extractor=lambda m: {"title": m.group(1)},
        description="最大化窗口",
        keywords=["最大化"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"(?:识别|OCR)(?:屏幕上的)?文字",
        action="ocr_recognize",
        params_extractor=lambda m: {},
        description="OCR识别文字",
        keywords=["OCR", "识别"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"(?:查找|寻找|找)\s*(?:屏幕上的)?(?:文字|文本)?\s*[\"「『]([^」」\']*)[」』\"]",
        action="ocr_find_text",
        params_extractor=lambda m: {"text": m.group(1)},
        description="查找屏幕文字",
        keywords=["查找", "文字"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"开始录制",
        action="record_start",
        params_extractor=lambda m: {},
        description="开始录制操作",
        keywords=["录制", "开始"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"停止录制",
        action="record_stop",
        params_extractor=lambda m: {},
        description="停止录制",
        keywords=["停止", "录制"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"(?:回放|播放)(?:录制的)?(?:操作)?",
        action="record_play",
        params_extractor=lambda m: {},
        description="回放录制的操作",
        keywords=["回放", "播放"],
        priority=1,
        category=IntentCategory.CUA_OPERATION
    ),
    PatternRule(
        pattern=r"(?:系统|电脑)(?:信息|状态|配置)",
        action="system_info",
        params_extractor=lambda m: {},
        description="获取系统信息",
        keywords=["系统", "信息"],
        priority=1,
        category=IntentCategory.SYSTEM_OPERATION
    ),
    PatternRule(
        pattern=r"(?:CPU|内存|磁盘|网络)(?:使用率|状态|信息)?",
        action="hardware_monitor",
        params_extractor=lambda m: {"component": m.group(1) if m.group(1) else "all"},
        description="硬件监控",
        keywords=["CPU", "内存", "磁盘", "网络"],
        priority=1,
        category=IntentCategory.SYSTEM_OPERATION
    ),
    PatternRule(
        pattern=r"(?:进程|任务)(?:列表|管理)",
        action="process_list",
        params_extractor=lambda m: {},
        description="列出进程",
        keywords=["进程", "任务"],
        priority=1,
        category=IntentCategory.SYSTEM_OPERATION
    ),
]

RULE_PATTERNS.sort(key=lambda x: x.priority)


def get_intent_definition(intent_type: str) -> IntentDefinition | None:
    return INTENT_PATTERNS.get(intent_type)


def get_all_patterns() -> list[PatternRule]:
    return RULE_PATTERNS


def get_patterns_by_category(category: IntentCategory) -> list[PatternRule]:
    return [p for p in RULE_PATTERNS if p.category == category]


def get_dangerous_patterns() -> list[PatternRule]:
    return [p for p in RULE_PATTERNS if p.dangerous]
