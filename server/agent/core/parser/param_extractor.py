import re
from contextlib import suppress
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ParamType(str, Enum):
    PATH = "path"
    URL = "url"
    NUMBER = "number"
    TIME = "time"
    APP_NAME = "app_name"
    CONTENT = "content"
    COMMAND = "command"
    ENTITY = "entity"


class ExtractedParam(BaseModel):
    name: str
    value: Any
    param_type: ParamType
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    raw_text: str = ""
    position: tuple[int, int] = Field(default=(0, 0))


class ParamExtractor:
    PATH_PATTERNS = [
        (r'["\']([a-zA-Z]:\\[^\s"\']+)["\']', 0.95),
        (r'["\'](/[^\s"\']+)["\']', 0.95),
        (r'([a-zA-Z]:\\[^\s:*?"<>|]+)', 0.85),
        (r'(/[\w\-./]+)', 0.80),
        (r'([\w\-]+\.[a-zA-Z]{1,10})(?:\s|$|[，。])', 0.70),
        (r'叫[它]?[\s]*["\']?([\w\-./]+)["\']?', 0.75),
        (r'名为[：:\s]*["\']?([\w\-./]+)["\']?', 0.75),
        (r'文件名[是为]?[\s]*["\']?([\w\-./]+)["\']?', 0.80),
    ]

    URL_PATTERNS = [
        (r'(https?://[^\s<>"{}|\\^`\[\]]+)', 0.95),
        (r'(www\.[^\s<>"{}|\\^`\[\]]+\.[a-zA-Z]{2,})', 0.85),
        (r'(ftp://[^\s]+)', 0.90),
    ]

    NUMBER_PATTERNS = [
        (r'\b(\d+(?:\.\d+)?)\s*(?:个|次|条|行|秒|分钟|小时|天)\b', 0.90),
        (r'\b(\d+(?:\.\d+)?)\b', 0.80),
        (r'(第[一二三四五六七八九十百千万]+)', 0.85),
    ]

    TIME_PATTERNS = [
        (r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?(?:\s+\d{1,2}[:时]\d{1,2}(?:[:分]\d{1,2})?)?)', 0.95),
        (r'(\d{1,2}[-/月]\d{1,2}[日]?(?:\s+\d{1,2}[:时]\d{1,2})?)', 0.85),
        (r'(今天|明天|后天|大后天|昨天|前天|大前天)', 0.90),
        (r'(下周[一二三四五六七]|下个月|上个月)', 0.85),
        (r'(早上|上午|中午|下午|晚上|傍晚)\s*(\d{1,2})[:点时](\d{1,2})?', 0.80),
        (r'(\d{1,2})[:点时](\d{1,2})?(?:分)?', 0.75),
    ]

    APP_NAME_PATTERNS = [
        (r'(VS\s*Code|Visual\s*Studio\s*Code|vscode)', 0.95),
        (r'(记事本|notepad\+\+|notepad)', 0.95),
        (r'(Chrome|chrome|谷歌浏览器|Google\s*Chrome)', 0.95),
        (r'(Edge|edge|微软浏览器)', 0.95),
        (r'(Firefox|firefox|火狐浏览器)', 0.95),
        (r'(计算器|calculator|calc)', 0.95),
        (r'(PowerShell|powershell)', 0.95),
        (r'(终端|terminal|cmd|命令提示符)', 0.90),
        (r'(微信|WeChat|wechat)', 0.95),
        (r'(QQ|qq)', 0.95),
        (r'(Word|word|微软文档)', 0.90),
        (r'(Excel|excel|微软表格)', 0.90),
        (r'(PowerPoint|powerpoint|PPT|ppt)', 0.90),
        (r'(?:打开|启动|运行|开启)\s*["\']?([\w\s]+?)["\']?(?:\s|应用|软件|程序|$|[，。])', 0.75),
    ]

    CONTENT_PATTERNS = [
        (r'[：:]\s*["「『]([^」」"]*)["」』]', 0.90),
        (r'内容[是为]?\s*["「『]([^」」"]*)["」』]', 0.90),
        (r'写入\s*["「『]([^」」"]*)["」』]', 0.85),
        (r'改成\s*["「『]([^」」"]*)["」』]', 0.85),
        (r'[：:]\s*(.+)$', 0.70),
    ]

    COMMAND_PATTERNS = [
        (r'`([^`]+)`', 0.95),
        (r'["\']([^"\']+)["\']', 0.80),
        (r'「([^」]+)」', 0.90),
    ]

    RELATIVE_TIME_MAP = {
        "今天": 0,
        "明天": 1,
        "后天": 2,
        "大后天": 3,
        "昨天": -1,
        "前天": -2,
        "大前天": -3,
    }

    CHINESE_NUMBER_MAP = {
        "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
        "十": 10, "百": 100, "千": 1000, "万": 10000,
    }

    def __init__(self, working_dir: Path | None = None):
        self.working_dir = working_dir or Path.cwd()
        self._compiled_patterns = self._compile_patterns()

    def _compile_patterns(self) -> dict[str, list[tuple]]:
        compiled = {}

        compiled["path"] = [
            (re.compile(p, re.IGNORECASE), c) for p, c in self.PATH_PATTERNS
        ]
        compiled["url"] = [
            (re.compile(p, re.IGNORECASE), c) for p, c in self.URL_PATTERNS
        ]
        compiled["number"] = [
            (re.compile(p), c) for p, c in self.NUMBER_PATTERNS
        ]
        compiled["time"] = [
            (re.compile(p), c) for p, c in self.TIME_PATTERNS
        ]
        compiled["app_name"] = [
            (re.compile(p, re.IGNORECASE), c) for p, c in self.APP_NAME_PATTERNS
        ]
        compiled["content"] = [
            (re.compile(p, re.IGNORECASE | re.MULTILINE), c) for p, c in self.CONTENT_PATTERNS
        ]
        compiled["command"] = [
            (re.compile(p), c) for p, c in self.COMMAND_PATTERNS
        ]

        return compiled

    def extract_path(self, text: str, resolve_relative: bool = True) -> ExtractedParam | None:
        for pattern, confidence in self._compiled_patterns["path"]:
            match = pattern.search(text)
            if match:
                raw_value = match.group(1)
                value = raw_value.strip('"\'')

                if resolve_relative and not self._is_absolute_path(value):
                    with suppress(Exception):
                        value = str((self.working_dir / value).resolve())

                return ExtractedParam(
                    name="path",
                    value=value,
                    param_type=ParamType.PATH,
                    confidence=confidence,
                    raw_text=raw_value,
                    position=(match.start(), match.end())
                )
        return None

    def extract_url(self, text: str) -> ExtractedParam | None:
        for pattern, confidence in self._compiled_patterns["url"]:
            match = pattern.search(text)
            if match:
                raw_value = match.group(1)
                value = raw_value
                if not value.startswith(('http://', 'https://', 'ftp://')):
                    value = 'https://' + value

                return ExtractedParam(
                    name="url",
                    value=value,
                    param_type=ParamType.URL,
                    confidence=confidence,
                    raw_text=raw_value,
                    position=(match.start(), match.end())
                )
        return None

    def extract_number(self, text: str) -> ExtractedParam | None:
        for pattern, confidence in self._compiled_patterns["number"]:
            match = pattern.search(text)
            if match:
                raw_value = match.group(1)

                if self._is_chinese_number(raw_value):
                    value = self._parse_chinese_number(raw_value)
                else:
                    value = float(raw_value) if '.' in raw_value else int(raw_value)

                return ExtractedParam(
                    name="number",
                    value=value,
                    param_type=ParamType.NUMBER,
                    confidence=confidence,
                    raw_text=raw_value,
                    position=(match.start(), match.end())
                )
        return None

    def extract_time(self, text: str) -> ExtractedParam | None:
        for pattern, confidence in self._compiled_patterns["time"]:
            match = pattern.search(text)
            if match:
                raw_value = match.group(0)
                value = self._parse_time_expression(raw_value)

                return ExtractedParam(
                    name="time",
                    value=value,
                    param_type=ParamType.TIME,
                    confidence=confidence,
                    raw_text=raw_value,
                    position=(match.start(), match.end())
                )
        return None

    def extract_app_name(self, text: str) -> ExtractedParam | None:
        for pattern, confidence in self._compiled_patterns["app_name"]:
            match = pattern.search(text)
            if match:
                raw_value = match.group(1)
                value = self._normalize_app_name(raw_value)

                return ExtractedParam(
                    name="app_name",
                    value=value,
                    param_type=ParamType.APP_NAME,
                    confidence=confidence,
                    raw_text=raw_value,
                    position=(match.start(), match.end())
                )
        return None

    def extract_content(self, text: str) -> ExtractedParam | None:
        for pattern, confidence in self._compiled_patterns["content"]:
            match = pattern.search(text)
            if match:
                raw_value = match.group(1)
                value = raw_value.strip()

                return ExtractedParam(
                    name="content",
                    value=value,
                    param_type=ParamType.CONTENT,
                    confidence=confidence,
                    raw_text=raw_value,
                    position=(match.start(), match.end())
                )
        return None

    def extract_command(self, text: str) -> ExtractedParam | None:
        for pattern, confidence in self._compiled_patterns["command"]:
            match = pattern.search(text)
            if match:
                raw_value = match.group(1)
                value = raw_value.strip()

                return ExtractedParam(
                    name="command",
                    value=value,
                    param_type=ParamType.COMMAND,
                    confidence=confidence,
                    raw_text=raw_value,
                    position=(match.start(), match.end())
                )
        return None

    def extract_all(self, text: str) -> dict[str, ExtractedParam]:
        params = {}

        url_param = self.extract_url(text)
        if url_param:
            params["url"] = url_param
            text = text[:url_param.position[0]] + text[url_param.position[1]:]

        path_param = self.extract_path(text)
        if path_param:
            params["path"] = path_param

        time_param = self.extract_time(text)
        if time_param:
            params["time"] = time_param

        app_param = self.extract_app_name(text)
        if app_param:
            params["app_name"] = app_param

        number_param = self.extract_number(text)
        if number_param:
            params["number"] = number_param

        content_param = self.extract_content(text)
        if content_param:
            params["content"] = content_param

        command_param = self.extract_command(text)
        if command_param:
            params["command"] = command_param

        return params

    def extract_by_type(self, text: str, param_type: ParamType) -> ExtractedParam | None:
        extractors = {
            ParamType.PATH: self.extract_path,
            ParamType.URL: self.extract_url,
            ParamType.NUMBER: self.extract_number,
            ParamType.TIME: self.extract_time,
            ParamType.APP_NAME: self.extract_app_name,
            ParamType.CONTENT: self.extract_content,
            ParamType.COMMAND: self.extract_command,
        }

        extractor = extractors.get(param_type)
        if extractor:
            return extractor(text)
        return None

    def _is_absolute_path(self, path: str) -> bool:
        return bool(re.match(r'^[a-zA-Z]:\\', path) or path.startswith('/'))

    def _is_chinese_number(self, text: str) -> bool:
        return all(c in self.CHINESE_NUMBER_MAP or c in '第' for c in text)

    def _parse_chinese_number(self, text: str) -> int:
        text = text.replace('第', '')
        result = 0
        temp = 0

        for char in text:
            if char in self.CHINESE_NUMBER_MAP:
                num = self.CHINESE_NUMBER_MAP[char]
                if num >= 10:
                    if temp == 0:
                        temp = 1
                    result += temp * num
                    temp = 0
                else:
                    temp = num

        return result + temp

    def _parse_time_expression(self, text: str) -> str:
        text = text.strip()

        if text in self.RELATIVE_TIME_MAP:
            delta = timedelta(days=self.RELATIVE_TIME_MAP[text])
            return (datetime.now() + delta).strftime("%Y-%m-%d")

        if '下周' in text:
            weekday_map = {'一': 0, '二': 1, '三': 2, '四': 3, '五': 4, '六': 5, '日': 6, '天': 6}
            weekday = weekday_map.get(text[-1], 0)
            today = datetime.now()
            days_ahead = weekday - today.weekday() + 7
            return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

        normalized = re.sub(r'[年月]', '-', text)
        normalized = re.sub(r'日', '', normalized)
        normalized = normalized.replace('/', '-')

        if re.match(r'^\d{1,2}-\d{1,2}', normalized):
            year = datetime.now().year
            normalized = f"{year}-{normalized}"

        return normalized

    def _normalize_app_name(self, name: str) -> str:
        name = name.strip()

        normalizations = {
            'vscode': 'VS Code',
            'visual studio code': 'VS Code',
            'vs code': 'VS Code',
            'chrome': 'Chrome',
            '谷歌浏览器': 'Chrome',
            'google chrome': 'Chrome',
            'edge': 'Edge',
            '微软浏览器': 'Edge',
            'firefox': 'Firefox',
            '火狐浏览器': 'Firefox',
            '记事本': 'Notepad',
            '计算器': 'Calculator',
            '终端': 'Terminal',
            '命令提示符': 'cmd',
        }

        return normalizations.get(name.lower(), name)
