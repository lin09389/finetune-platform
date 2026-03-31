"""
帮助系统模块
提供操作指南、命令示例和帮助信息
"""
import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class HelpCategory(str, Enum):
    """帮助类别"""
    FILE_OPERATIONS = "file_operations"
    SCREEN_OPERATIONS = "screen_operations"
    APP_OPERATIONS = "app_operations"
    SYSTEM_OPERATIONS = "system_operations"
    GETTING_STARTED = "getting_started"
    TROUBLESHOOTING = "troubleshooting"
    ADVANCED = "advanced"


@dataclass
class HelpCommand:
    """帮助命令"""
    command: str
    description: str
    examples: list[str]
    parameters: dict[str, str] = field(default_factory=dict)
    tips: list[str] = field(default_factory=list)
    related_commands: list[str] = field(default_factory=list)
    category: HelpCategory = HelpCategory.FILE_OPERATIONS


@dataclass
class HelpTopic:
    """帮助主题"""
    title: str
    content: str
    commands: list[HelpCommand] = field(default_factory=list)
    see_also: list[str] = field(default_factory=list)


FILE_OPERATIONS_HELP: list[HelpCommand] = [
    HelpCommand(
        command="读取文件",
        description="读取指定文件的内容",
        examples=[
            "读取 test.txt",
            "读取 C:\\Users\\用户名\\Desktop\\note.txt",
            "显示 config.json 的内容",
        ],
        parameters={
            "文件路径": "可以是相对路径或绝对路径",
        },
        tips=[
            "支持文本文件、代码文件、配置文件等",
            "大文件会自动分页显示",
            "二进制文件会显示提示信息",
        ],
        related_commands=["列出文件", "创建文件", "修改文件"],
        category=HelpCategory.FILE_OPERATIONS,
    ),
    HelpCommand(
        command="创建文件",
        description="创建新文件",
        examples=[
            "创建 test.txt",
            "新建一个文件 config.json",
            "生成 README.md 文件",
        ],
        parameters={
            "文件路径": "新文件的路径",
            "内容": "可选，文件的初始内容",
        },
        tips=[
            "如果文件已存在，会提示确认",
            "支持同时创建多级目录",
        ],
        related_commands=["读取文件", "修改文件"],
        category=HelpCategory.FILE_OPERATIONS,
    ),
    HelpCommand(
        command="修改文件",
        description="修改文件内容",
        examples=[
            "把 test.txt 改成 Hello World",
            "将 config.json 内容改为 {}",
            "修改 main.py 的代码",
        ],
        parameters={
            "文件路径": "要修改的文件路径",
            "新内容": "文件的新内容",
        },
        tips=[
            "修改前会自动备份原文件",
            "敏感文件需要额外确认",
        ],
        related_commands=["读取文件", "创建文件"],
        category=HelpCategory.FILE_OPERATIONS,
    ),
    HelpCommand(
        command="删除文件",
        description="删除指定文件",
        examples=[
            "删除 test.txt",
            "移除 old_file.txt",
        ],
        parameters={
            "文件路径": "要删除的文件路径",
        },
        tips=[
            "删除的文件会移动到回收站",
            "回收站位置: ~/.finetune_recycle_bin",
            "敏感文件无法删除",
        ],
        related_commands=["批量删除", "列出文件"],
        category=HelpCategory.FILE_OPERATIONS,
    ),
    HelpCommand(
        command="列出文件",
        description="列出目录中的文件和文件夹",
        examples=[
            "列出当前目录文件",
            "列出 C:\\Users\\用户名\\Desktop 的文件",
            "显示 Desktop 文件夹内容",
        ],
        parameters={
            "目录路径": "可选，默认为当前目录",
        },
        tips=[
            "支持分页显示大量文件",
            "会显示文件大小和修改时间",
        ],
        related_commands=["读取文件", "创建文件"],
        category=HelpCategory.FILE_OPERATIONS,
    ),
    HelpCommand(
        command="批量删除",
        description="批量删除指定类型的文件",
        examples=[
            "批量删除 tmp 文件",
            "删除所有 log 文件",
            "清理 temp 文件",
        ],
        parameters={
            "文件类型": "要删除的文件扩展名（不带点）",
        },
        tips=[
            "需要确认后才会执行",
            "删除的文件会移动到回收站",
        ],
        related_commands=["删除文件", "列出文件"],
        category=HelpCategory.FILE_OPERATIONS,
    ),
]


SCREEN_OPERATIONS_HELP: list[HelpCommand] = [
    HelpCommand(
        command="截图",
        description="截取当前屏幕",
        examples=[
            "截图",
            "截屏",
            "截取屏幕",
        ],
        parameters={},
        tips=[
            "截图会保存到指定目录",
            "支持多显示器截图",
        ],
        related_commands=["识别文字", "点击坐标"],
        category=HelpCategory.SCREEN_OPERATIONS,
    ),
    HelpCommand(
        command="识别文字",
        description="使用 OCR 识别屏幕上的文字",
        examples=[
            "识别屏幕上的文字",
            "OCR 识别",
        ],
        parameters={},
        tips=[
            "支持中英文混合识别",
            "识别结果会返回文字内容",
        ],
        related_commands=["截图", "点击坐标"],
        category=HelpCategory.SCREEN_OPERATIONS,
    ),
    HelpCommand(
        command="点击坐标",
        description="在指定位置点击鼠标",
        examples=[
            "点击坐标 100, 200",
            "单击 (500, 300)",
        ],
        parameters={
            "X": "屏幕横坐标",
            "Y": "屏幕纵坐标",
        },
        tips=[
            "坐标从屏幕左上角开始",
            "建议先截图确认位置",
        ],
        related_commands=["截图", "输入文字"],
        category=HelpCategory.SCREEN_OPERATIONS,
    ),
    HelpCommand(
        command="输入文字",
        description="模拟键盘输入文字",
        examples=[
            "输入 Hello World",
            "打字 你好世界",
        ],
        parameters={
            "文字": "要输入的内容",
        },
        tips=[
            "支持中英文输入",
            "会自动切换输入法",
        ],
        related_commands=["点击坐标", "组合键"],
        category=HelpCategory.SCREEN_OPERATIONS,
    ),
    HelpCommand(
        command="列出窗口",
        description="列出当前所有打开的窗口",
        examples=[
            "列出所有窗口",
            "显示窗口列表",
        ],
        parameters={},
        tips=[
            "会显示窗口标题和进程名",
            "可用于定位目标窗口",
        ],
        related_commands=["截图", "激活窗口"],
        category=HelpCategory.SCREEN_OPERATIONS,
    ),
]


APP_OPERATIONS_HELP: list[HelpCommand] = [
    HelpCommand(
        command="打开应用",
        description="打开指定的应用程序",
        examples=[
            "打开微信",
            "打开 VS Code",
            "打开记事本",
        ],
        parameters={
            "应用名称": "应用程序名称",
        },
        tips=[
            "支持常用应用的快捷名称",
            "也可以使用完整路径",
        ],
        related_commands=["列出窗口", "关闭窗口"],
        category=HelpCategory.APP_OPERATIONS,
    ),
    HelpCommand(
        command="关闭窗口",
        description="关闭指定窗口",
        examples=[
            "关闭记事本窗口",
            "关闭当前窗口",
        ],
        parameters={
            "窗口标题": "可选，窗口标题关键词",
        },
        tips=[
            "未保存的工作可能会丢失",
            "会提示确认",
        ],
        related_commands=["列出窗口", "打开应用"],
        category=HelpCategory.APP_OPERATIONS,
    ),
]


GETTING_STARTED_HELP: list[HelpTopic] = [
    HelpTopic(
        title="快速入门",
        content="""
欢迎使用本地电脑操作助手！这个助手可以帮助您通过自然语言控制电脑。

## 基本使用

1. **直接说出您想做的事情**
   - "读取 test.txt"
   - "创建一个新文件 config.json"
   - "截图"

2. **系统会自动理解您的意图**
   - 系统会分析您的输入，识别操作类型
   - 提取必要的参数（如文件路径）

3. **确认后执行**
   - 危险操作需要您确认
   - 执行结果会实时反馈

## 安全说明

为了保护您的数据安全，系统有以下限制：
- 只能访问安全路径（桌面、文档、下载、工作目录）
- 敏感文件（如 .env, .key）需要额外确认
- 危险操作（如删除文件）会移动到回收站

## 获取帮助

- 说 "帮助" 查看所有可用命令
- 说 "帮助 文件操作" 查看特定类别的帮助
- 说 "如何读取文件" 获取具体操作指南
""",
        commands=[],
        see_also=["文件操作", "屏幕操作", "应用操作"],
    ),
]


TROUBLESHOOTING_HELP: list[HelpTopic] = [
    HelpTopic(
        title="常见问题",
        content="""
## 文件操作问题

### 文件不存在
**问题**: 提示"文件不存在"
**解决**: 
- 检查文件名是否正确，注意大小写
- 使用"列出文件"查看目录内容
- 确认文件路径是否正确

### 权限不足
**问题**: 提示"无法访问文件"
**解决**:
- 检查文件是否被其他程序打开
- 确认您有访问该文件的权限
- 尝试关闭可能占用文件的应用

### 路径不安全
**问题**: 提示"安全限制"
**解决**:
- 只能访问安全路径内的文件
- 将文件移动到桌面、文档或下载目录

## 屏幕操作问题

### 截图失败
**问题**: 截图操作失败
**解决**:
- 检查是否有权限访问屏幕
- 确认系统未锁定

### OCR 识别不准确
**问题**: 文字识别结果不准确
**解决**:
- 确保屏幕文字清晰
- 尝试放大文字后重新识别
- 检查语言设置是否正确

## 意图识别问题

### 意图识别错误
**问题**: 系统误解了我的意思
**解决**:
- 使用更明确的表述
- 提供完整的参数信息
- 使用"反馈"功能报告问题
""",
        commands=[],
        see_also=["快速入门"],
    ),
]


class HelpSystem:
    """
    帮助系统
    
    提供操作指南、命令示例和帮助信息
    """

    def __init__(self):
        self._commands: dict[str, HelpCommand] = {}
        self._topics: dict[str, HelpTopic] = {}
        self._categories: dict[HelpCategory, list[HelpCommand]] = {}

        self._init_commands()
        self._init_topics()

    def _init_commands(self):
        """初始化命令帮助"""
        all_commands = (
            FILE_OPERATIONS_HELP +
            SCREEN_OPERATIONS_HELP +
            APP_OPERATIONS_HELP
        )

        for cmd in all_commands:
            self._commands[cmd.command] = cmd

            if cmd.category not in self._categories:
                self._categories[cmd.category] = []
            self._categories[cmd.category].append(cmd)

    def _init_topics(self):
        """初始化帮助主题"""
        all_topics = GETTING_STARTED_HELP + TROUBLESHOOTING_HELP

        for topic in all_topics:
            self._topics[topic.title] = topic

    def get_command_help(self, command: str) -> HelpCommand | None:
        """获取命令帮助"""
        return self._commands.get(command)

    def get_topic(self, title: str) -> HelpTopic | None:
        """获取帮助主题"""
        return self._topics.get(title)

    def get_category_commands(self, category: HelpCategory) -> list[HelpCommand]:
        """获取类别下的所有命令"""
        return self._categories.get(category, [])

    def search(self, query: str) -> list[HelpCommand]:
        """搜索命令"""
        query_lower = query.lower()
        results = []

        for cmd in self._commands.values():
            if (query_lower in cmd.command.lower() or
                query_lower in cmd.description.lower()):
                results.append(cmd)

        return results

    def get_all_commands(self) -> list[HelpCommand]:
        """获取所有命令"""
        return list(self._commands.values())

    def get_all_categories(self) -> dict[HelpCategory, list[str]]:
        """获取所有类别及其命令"""
        return {
            category: [cmd.command for cmd in commands]
            for category, commands in self._categories.items()
        }

    def format_command_help(self, command: str) -> str:
        """格式化命令帮助信息"""
        cmd = self.get_command_help(command)
        if not cmd:
            return f"未找到命令: {command}"

        lines = [
            f"📌 {cmd.command}",
            "",
            cmd.description,
            "",
            "示例:",
        ]

        for example in cmd.examples:
            lines.append(f"  • {example}")

        if cmd.parameters:
            lines.append("")
            lines.append("参数:")
            for param, desc in cmd.parameters.items():
                lines.append(f"  • {param}: {desc}")

        if cmd.tips:
            lines.append("")
            lines.append("提示:")
            for tip in cmd.tips:
                lines.append(f"  • {tip}")

        if cmd.related_commands:
            lines.append("")
            lines.append("相关命令: " + " | ".join(cmd.related_commands))

        return "\n".join(lines)

    def format_category_help(self, category: HelpCategory) -> str:
        """格式化类别帮助信息"""
        commands = self.get_category_commands(category)
        if not commands:
            return f"未找到类别: {category.value}"

        category_names = {
            HelpCategory.FILE_OPERATIONS: "文件操作",
            HelpCategory.SCREEN_OPERATIONS: "屏幕操作",
            HelpCategory.APP_OPERATIONS: "应用操作",
            HelpCategory.SYSTEM_OPERATIONS: "系统操作",
            HelpCategory.GETTING_STARTED: "快速入门",
            HelpCategory.TROUBLESHOOTING: "故障排除",
            HelpCategory.ADVANCED: "高级功能",
        }

        lines = [
            f"📚 {category_names.get(category, category.value)}",
            "",
            "可用命令:",
        ]

        for cmd in commands:
            lines.append(f"  • {cmd.command} - {cmd.description}")

        return "\n".join(lines)

    def format_overview(self) -> str:
        """格式化概览帮助信息"""
        lines = [
            "🤖 本地电脑操作助手 - 帮助",
            "",
            "我可以帮您执行以下类型的操作:",
            "",
        ]

        category_names = {
            HelpCategory.FILE_OPERATIONS: "文件操作",
            HelpCategory.SCREEN_OPERATIONS: "屏幕操作",
            HelpCategory.APP_OPERATIONS: "应用操作",
        }

        for category, name in category_names.items():
            commands = self.get_category_commands(category)
            if commands:
                lines.append(f"📁 {name}")
                for cmd in commands[:3]:
                    lines.append(f"   • {cmd.command}")
                if len(commands) > 3:
                    lines.append(f"   • ... 还有 {len(commands) - 3} 个命令")
                lines.append("")

        lines.extend([
            "💡 提示:",
            "  • 说 '帮助 文件操作' 查看特定类别",
            "  • 说 '如何读取文件' 查看具体命令帮助",
            "  • 直接说出您想做的事情即可",
        ])

        return "\n".join(lines)


_help_system: HelpSystem | None = None


def get_help_system() -> HelpSystem:
    """获取帮助系统单例"""
    global _help_system
    if _help_system is None:
        _help_system = HelpSystem()
    return _help_system


def get_command_help(command: str) -> HelpCommand | None:
    """便捷函数：获取命令帮助"""
    return get_help_system().get_command_help(command)


def search_help(query: str) -> list[HelpCommand]:
    """便捷函数：搜索帮助"""
    return get_help_system().search(query)


def format_help(query: str = None) -> str:
    """便捷函数：格式化帮助信息"""
    system = get_help_system()

    if not query:
        return system.format_overview()

    category_mapping = {
        "文件": HelpCategory.FILE_OPERATIONS,
        "文件操作": HelpCategory.FILE_OPERATIONS,
        "file": HelpCategory.FILE_OPERATIONS,
        "屏幕": HelpCategory.SCREEN_OPERATIONS,
        "屏幕操作": HelpCategory.SCREEN_OPERATIONS,
        "screen": HelpCategory.SCREEN_OPERATIONS,
        "应用": HelpCategory.APP_OPERATIONS,
        "应用操作": HelpCategory.APP_OPERATIONS,
        "app": HelpCategory.APP_OPERATIONS,
    }

    if query in category_mapping:
        return system.format_category_help(category_mapping[query])

    cmd = system.get_command_help(query)
    if cmd:
        return system.format_command_help(query)

    results = system.search(query)
    if results:
        lines = [f"搜索结果 ({len(results)} 个):", ""]
        for cmd in results[:5]:
            lines.append(f"  • {cmd.command} - {cmd.description}")
        return "\n".join(lines)

    return f"未找到相关帮助: {query}"
