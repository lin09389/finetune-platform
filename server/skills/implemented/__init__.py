"""
技能实现模�?
此目录包含所有具体技能的实现�?每个技能应该是一个独立的 Python 文件，包含一个或多个继承�?SkillBase 的类�?"""

from .file_skills import (
    FileReadSkill,
    FileWriteSkill,
    FileListSkill,
    FileDeleteSkill,
)
from .text_skills import (
    TextRegexSkill,
    TextReplaceSkill,
    TextSplitSkill,
    JsonParseSkill,
    JsonStringifySkill,
)
from .system_skills import (
    SystemInfoSkill,
    CommandExecuteSkill,
    DelaySkill,
    CalculatorSkill,
)
from .github_skills import (
    GitHubAnalyzerSkill,
    CodePatternSkill,
)
from .frontend_design_skills import (
    FrontendDesignSkill,
)
from .cua_skills import (
    ScreenshotSkill,
    MouseClickSkill,
    MouseMoveSkill,
    KeyboardTypeSkill,
    WindowListSkill,
    AppLaunchSkill,
    FindTextSkill,
    CUA_SKILLS,
)

__all__ = [
    # 文件技�?    "FileReadSkill",
    "FileWriteSkill",
    "FileListSkill",
    "FileDeleteSkill",
    # 文本技�?    "TextRegexSkill",
    "TextReplaceSkill",
    "TextSplitSkill",
    "JsonParseSkill",
    "JsonStringifySkill",
    # 系统技�?    "SystemInfoSkill",
    "CommandExecuteSkill",
    "DelaySkill",
    "CalculatorSkill",
    # GitHub技�?    "GitHubAnalyzerSkill",
    "CodePatternSkill",
    # 前端设计技�?    "FrontendDesignSkill",
    # CUA技�?    "ScreenshotSkill",
    "MouseClickSkill",
    "MouseMoveSkill",
    "KeyboardTypeSkill",
    "WindowListSkill",
    "AppLaunchSkill",
    "FindTextSkill",
    "CUA_SKILLS",
]

# 所有技能类列表
ALL_SKILLS = [
    FileReadSkill,
    FileWriteSkill,
    FileListSkill,
    FileDeleteSkill,
    TextRegexSkill,
    TextReplaceSkill,
    TextSplitSkill,
    JsonParseSkill,
    JsonStringifySkill,
    SystemInfoSkill,
    CommandExecuteSkill,
    DelaySkill,
    CalculatorSkill,
    GitHubAnalyzerSkill,
    CodePatternSkill,
    FrontendDesignSkill,
    ScreenshotSkill,
    MouseClickSkill,
    MouseMoveSkill,
    KeyboardTypeSkill,
    WindowListSkill,
    AppLaunchSkill,
    FindTextSkill,
]


def register_all_skills(registry):
    """注册所有技能到注册�?""
    for skill_class in ALL_SKILLS:
        registry.register(skill_class)
