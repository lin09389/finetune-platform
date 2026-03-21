# -*- coding: utf-8 -*-
"""
技能实现模块

此目录包含所有具体技能的实现。
每个技能应该是一个独立的 Python 文件，包含一个或多个继承自 SkillBase 的类。
"""

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
    "FileReadSkill",
    "FileWriteSkill",
    "FileListSkill",
    "FileDeleteSkill",
    "TextRegexSkill",
    "TextReplaceSkill",
    "TextSplitSkill",
    "JsonParseSkill",
    "JsonStringifySkill",
    "SystemInfoSkill",
    "CommandExecuteSkill",
    "DelaySkill",
    "CalculatorSkill",
    "GitHubAnalyzerSkill",
    "CodePatternSkill",
    "FrontendDesignSkill",
    "ScreenshotSkill",
    "MouseClickSkill",
    "MouseMoveSkill",
    "KeyboardTypeSkill",
    "WindowListSkill",
    "AppLaunchSkill",
    "FindTextSkill",
    "CUA_SKILLS",
]

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
    """注册所有技能到注册表"""
    for skill_class in ALL_SKILLS:
        registry.register(skill_class)
