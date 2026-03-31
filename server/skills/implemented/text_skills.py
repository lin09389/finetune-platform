"""
文本处理技能
"""
import json
import re

from skills.base import SkillBase
from skills.models import (
    SkillCategory,
    SkillMetadata,
    SkillParameter,
    SkillParameterType,
    SkillResult,
)


class TextRegexSkill(SkillBase):
    """正则表达式匹配"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="text_regex",
            display_name="正则匹配",
            description="使用正则表达式在文本中查找匹配项",
            version="1.0.0",
            category=SkillCategory.TEXT,
            tags=["text", "regex", "search"],
            parameters=[
                SkillParameter(
                    name="text",
                    type=SkillParameterType.STRING,
                    description="要搜索的文本",
                    required=True,
                ),
                SkillParameter(
                    name="pattern",
                    type=SkillParameterType.STRING,
                    description="正则表达式模式",
                    required=True,
                ),
                SkillParameter(
                    name="flags",
                    type=SkillParameterType.STRING,
                    description="正则标志（如 IGNORECASE, MULTILINE）",
                    required=False,
                    default="",
                ),
            ],
            examples=[
                {"text": "Hello 123 World 456", "pattern": r"\d+"},
                {"text": "hello world", "pattern": "HELLO", "flags": "IGNORECASE"},
            ],
        )

    async def execute(self, **kwargs) -> SkillResult:
        text = kwargs.get("text", "")
        pattern = kwargs.get("pattern")
        flags_str = kwargs.get("flags", "")

        try:
            flags = 0
            if "IGNORECASE" in flags_str:
                flags |= re.IGNORECASE
            if "MULTILINE" in flags_str:
                flags |= re.MULTILINE
            if "DOTALL" in flags_str:
                flags |= re.DOTALL

            regex = re.compile(pattern, flags)
            matches = regex.findall(text)

            return SkillResult(
                success=True,
                data={
                    "matches": matches,
                    "count": len(matches),
                    "pattern": pattern,
                },
            )

        except re.error as e:
            return SkillResult(
                success=False,
                error=f"正则表达式错误: {str(e)}",
                error_code="REGEX_ERROR",
            )
        except Exception as e:
            return SkillResult(
                success=False,
                error=f"匹配失败: {str(e)}",
                error_code="MATCH_ERROR",
            )


class TextReplaceSkill(SkillBase):
    """文本替换"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="text_replace",
            display_name="文本替换",
            description="在文本中替换匹配的内容",
            version="1.0.0",
            category=SkillCategory.TEXT,
            tags=["text", "replace", "string"],
            parameters=[
                SkillParameter(
                    name="text",
                    type=SkillParameterType.STRING,
                    description="原始文本",
                    required=True,
                ),
                SkillParameter(
                    name="old",
                    type=SkillParameterType.STRING,
                    description="要替换的内容",
                    required=True,
                ),
                SkillParameter(
                    name="new",
                    type=SkillParameterType.STRING,
                    description="替换后的内容",
                    required=True,
                ),
                SkillParameter(
                    name="use_regex",
                    type=SkillParameterType.BOOLEAN,
                    description="是否使用正则表达式",
                    required=False,
                    default=False,
                ),
                SkillParameter(
                    name="count",
                    type=SkillParameterType.INTEGER,
                    description="替换次数（-1 表示全部）",
                    required=False,
                    default=-1,
                ),
            ],
            examples=[
                {"text": "hello world", "old": "world", "new": "Python"},
                {"text": "123-456-789", "old": "-", "new": "", "count": 1},
            ],
        )

    async def execute(self, **kwargs) -> SkillResult:
        text = kwargs.get("text", "")
        old = kwargs.get("old")
        new = kwargs.get("new", "")
        use_regex = kwargs.get("use_regex", False)
        count = kwargs.get("count", -1)

        try:
            if use_regex:
                if count == -1:
                    result = re.sub(old, new, text)
                else:
                    result = re.sub(old, new, text, count=count)
            else:
                if count == -1:
                    result = text.replace(old, new)
                else:
                    result = text.replace(old, new, count)

            return SkillResult(
                success=True,
                data={
                    "result": result,
                    "original_length": len(text),
                    "result_length": len(result),
                },
            )

        except Exception as e:
            return SkillResult(
                success=False,
                error=f"替换失败: {str(e)}",
                error_code="REPLACE_ERROR",
            )


class TextSplitSkill(SkillBase):
    """文本分割"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="text_split",
            display_name="文本分割",
            description="按分隔符分割文本",
            version="1.0.0",
            category=SkillCategory.TEXT,
            tags=["text", "split", "string"],
            parameters=[
                SkillParameter(
                    name="text",
                    type=SkillParameterType.STRING,
                    description="要分割的文本",
                    required=True,
                ),
                SkillParameter(
                    name="separator",
                    type=SkillParameterType.STRING,
                    description="分隔符",
                    required=False,
                    default="\n",
                ),
                SkillParameter(
                    name="max_split",
                    type=SkillParameterType.INTEGER,
                    description="最大分割次数（-1 表示不限制）",
                    required=False,
                    default=-1,
                ),
                SkillParameter(
                    name="strip",
                    type=SkillParameterType.BOOLEAN,
                    description="是否去除每项首尾空白",
                    required=False,
                    default=True,
                ),
            ],
            examples=[
                {"text": "a,b,c", "separator": ","},
                {"text": "line1\nline2\nline3", "separator": "\n"},
            ],
        )

    async def execute(self, **kwargs) -> SkillResult:
        text = kwargs.get("text", "")
        separator = kwargs.get("separator", "\n")
        max_split = kwargs.get("max_split", -1)
        strip = kwargs.get("strip", True)

        try:
            if max_split == -1:
                parts = text.split(separator)
            else:
                parts = text.split(separator, max_split)

            if strip:
                parts = [p.strip() for p in parts]

            return SkillResult(
                success=True,
                data={
                    "parts": parts,
                    "count": len(parts),
                },
            )

        except Exception as e:
            return SkillResult(
                success=False,
                error=f"分割失败: {str(e)}",
                error_code="SPLIT_ERROR",
            )


class JsonParseSkill(SkillBase):
    """JSON 解析"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="json_parse",
            display_name="JSON解析",
            description="解析 JSON 字符串",
            version="1.0.0",
            category=SkillCategory.DATA,
            tags=["json", "parse", "data"],
            parameters=[
                SkillParameter(
                    name="text",
                    type=SkillParameterType.STRING,
                    description="JSON 字符串",
                    required=True,
                ),
                SkillParameter(
                    name="path",
                    type=SkillParameterType.STRING,
                    description="提取路径（如 data.items.0.name）",
                    required=False,
                    default="",
                ),
            ],
            examples=[
                {"text": '{"name": "test", "value": 123}'},
                {"text": '{"data": {"items": [1, 2, 3]}}', "path": "data.items"},
            ],
        )

    async def execute(self, **kwargs) -> SkillResult:
        text = kwargs.get("text")
        path = kwargs.get("path", "")

        try:
            data = json.loads(text)

            if path:
                keys = path.split(".")
                result = data
                for key in keys:
                    if key.isdigit():
                        result = result[int(key)]
                    else:
                        result = result[key]
            else:
                result = data

            return SkillResult(
                success=True,
                data={
                    "result": result,
                    "type": type(result).__name__,
                },
            )

        except json.JSONDecodeError as e:
            return SkillResult(
                success=False,
                error=f"JSON 解析错误: {str(e)}",
                error_code="JSON_PARSE_ERROR",
            )
        except (KeyError, IndexError, TypeError) as e:
            return SkillResult(
                success=False,
                error=f"路径访问错误: {str(e)}",
                error_code="PATH_ERROR",
            )
        except Exception as e:
            return SkillResult(
                success=False,
                error=f"解析失败: {str(e)}",
                error_code="PARSE_ERROR",
            )


class JsonStringifySkill(SkillBase):
    """JSON 序列化"""

    @classmethod
    def get_metadata(cls) -> SkillMetadata:
        return SkillMetadata(
            name="json_stringify",
            display_name="JSON序列化",
            description="将对象序列化为 JSON 字符串",
            version="1.0.0",
            category=SkillCategory.DATA,
            tags=["json", "stringify", "data"],
            parameters=[
                SkillParameter(
                    name="data",
                    type=SkillParameterType.OBJECT,
                    description="要序列化的数据",
                    required=True,
                ),
                SkillParameter(
                    name="indent",
                    type=SkillParameterType.INTEGER,
                    description="缩进空格数（0 表示压缩）",
                    required=False,
                    default=2,
                ),
                SkillParameter(
                    name="ensure_ascii",
                    type=SkillParameterType.BOOLEAN,
                    description="是否转义非 ASCII 字符",
                    required=False,
                    default=False,
                ),
            ],
            examples=[
                {"data": {"name": "测试", "value": 123}},
                {"data": [1, 2, 3], "indent": 0},
            ],
        )

    async def execute(self, **kwargs) -> SkillResult:
        data = kwargs.get("data")
        indent = kwargs.get("indent", 2)
        ensure_ascii = kwargs.get("ensure_ascii", False)

        try:
            result = json.dumps(
                data,
                indent=indent if indent > 0 else None,
                ensure_ascii=ensure_ascii,
            )

            return SkillResult(
                success=True,
                data={
                    "result": result,
                    "length": len(result),
                },
            )

        except Exception as e:
            return SkillResult(
                success=False,
                error=f"序列化失败: {str(e)}",
                error_code="STRINGIFY_ERROR",
            )
