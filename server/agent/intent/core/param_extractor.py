"""
意图检测核心组件 - 统一参数提取器

整合所有参数提取逻辑，消除重复代码
"""
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ExtractedParam:
    name: str
    value: Any
    source: str
    confidence: float = 1.0


class ParamExtractor:
    """统一参数提取器"""

    FILE_EXTENSIONS = [
        ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".h", ".hpp",
        ".go", ".rs", ".rb", ".php", ".cs", ".swift", ".kt", ".scala",
        ".txt", ".md", ".json", ".yaml", ".yml", ".xml", ".html", ".css", ".scss",
        ".sql", ".sh", ".bat", ".ps1", ".env", ".ini", ".cfg", ".conf",
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf", ".doc", ".docx"
    ]

    APP_ALIASES = {
        "vscode": ["vs code", "vscode", "visual studio code", "code"],
        "notepad": ["记事本", "notepad", "notepad++"],
        "chrome": ["chrome", "谷歌浏览器", "google chrome"],
        "edge": ["edge", "microsoft edge", "微软浏览器"],
        "firefox": ["firefox", "火狐浏览器", "mozilla firefox"],
        "wechat": ["微信", "wechat"],
        "qq": ["qq", "腾讯qq"],
        "dingtalk": ["钉钉", "dingtalk"],
        "terminal": ["终端", "terminal", "cmd", "powershell", "命令行"],
        "explorer": ["资源管理器", "explorer", "文件管理器"],
    }

    def __init__(self):
        self._compile_patterns()

    def _compile_patterns(self):
        self._path_pattern = re.compile(
            r'(?:^|[\'"\s])([\w\-./\\]+\.[a-zA-Z]{1,10})(?:$|[\'"\s])'
        )
        self._url_pattern = re.compile(
            r'https?://[^\s<>"{}|\\^`\[\]]+'
        )
        self._email_pattern = re.compile(
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        )
        self._number_pattern = re.compile(
            r'-?\d+(?:\.\d+)?'
        )
        self._quoted_pattern = re.compile(
            r'["「『]([^」」\']*)[」』"]'
        )
        self._chinese_path_pattern = re.compile(
            r'[\u4e00-\u9fa5\w\-./\\]+\.[a-zA-Z]{1,10}'
        )

    def extract_path(self, text: str) -> str | None:
        matches = self._path_pattern.findall(text)
        if matches:
            for match in matches:
                if any(match.lower().endswith(ext) for ext in self.FILE_EXTENSIONS):
                    return match

        chinese_matches = self._chinese_path_pattern.findall(text)
        if chinese_matches:
            for match in chinese_matches:
                if any(match.lower().endswith(ext) for ext in self.FILE_EXTENSIONS):
                    return match

        return None

    def extract_url(self, text: str) -> str | None:
        matches = self._url_pattern.findall(text)
        return matches[0] if matches else None

    def extract_app_name(self, text: str) -> str | None:
        text_lower = text.lower()
        for canonical, aliases in self.APP_ALIASES.items():
            for alias in aliases:
                if alias.lower() in text_lower:
                    return canonical
        return None

    def extract_number(self, text: str) -> float | None:
        matches = self._number_pattern.findall(text)
        if matches:
            return float(matches[0])
        return None

    def extract_coordinate(self, text: str) -> tuple[int, int] | None:
        coord_pattern = re.compile(r'\(?(\d+)\s*[,，]\s*(\d+)\)?')
        matches = coord_pattern.findall(text)
        if matches:
            return (int(matches[0][0]), int(matches[0][1]))
        return None

    def extract_quoted_text(self, text: str) -> str | None:
        matches = self._quoted_pattern.findall(text)
        return matches[0] if matches else None

    def extract_content(self, text: str) -> str | None:
        quoted = self.extract_quoted_text(text)
        if quoted:
            return quoted

        content_patterns = [
            r'(?:内容为|内容是|内容改成|写入|添加|追加)\s*(.+?)(?:$|到|在)',
            r'(?:改成|修改成|改为)\s*(.+?)(?:$|到|在)',
        ]
        for pattern in content_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()

        return None

    def extract_key(self, text: str) -> str | None:
        key_patterns = [
            r'(?:按下|按)\s*([A-Za-z0-9]+)\s*键',
            r'(?:按下|按)\s*([A-Za-z0-9]+)',
        ]
        for pattern in key_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                key = match.group(1).upper()
                key_mapping = {
                    "ENTER": "enter",
                    "ESC": "esc",
                    "ESCAPE": "escape",
                    "TAB": "tab",
                    "SPACE": "space",
                    "BACKSPACE": "backspace",
                    "DELETE": "delete",
                    "UP": "up",
                    "DOWN": "down",
                    "LEFT": "left",
                    "RIGHT": "right",
                    "CTRL": "ctrl",
                    "ALT": "alt",
                    "SHIFT": "shift",
                    "WIN": "win",
                    "CMD": "cmd",
                }
                return key_mapping.get(key, key.lower())
        return None

    def extract_hotkey(self, text: str) -> list[str] | None:
        hotkey_patterns = [
            r'(?:按下|按)\s*([A-Za-z0-9]+)\s*(?:和|加|\\+)\s*([A-Za-z0-9]+)',
            r'([A-Za-z0-9]+)\s*\\+\s*([A-Za-z0-9]+)',
        ]
        for pattern in hotkey_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                keys = [match.group(1).upper(), match.group(2).upper()]
                key_mapping = {
                    "ENTER": "enter",
                    "ESC": "esc",
                    "ESCAPE": "escape",
                    "TAB": "tab",
                    "SPACE": "space",
                    "BACKSPACE": "backspace",
                    "DELETE": "delete",
                    "UP": "up",
                    "DOWN": "down",
                    "LEFT": "left",
                    "RIGHT": "right",
                    "CTRL": "ctrl",
                    "ALT": "alt",
                    "SHIFT": "shift",
                    "WIN": "win",
                    "CMD": "cmd",
                }
                return [key_mapping.get(k, k.lower()) for k in keys]
        return None

    def extract_window_title(self, text: str) -> str | None:
        title_patterns = [
            r'(?:激活|切换|转到|关闭|最小化|最大化)\s*(.+?)\s*窗口',
            r'(.+?)\s*窗口',
        ]
        for pattern in title_patterns:
            match = re.search(pattern, text)
            if match:
                title = match.group(1).strip()
                if title and title not in ["当前", "活动", "所有"]:
                    return title
        return None

    def extract_search_pattern(self, text: str) -> str | None:
        search_patterns = [
            r'(?:搜索|查找|寻找)\s*(?:文件)?\s*([\w\-*?\.]+)',
            r'(?:搜索|查找|寻找)\s+(.+?)(?:$|\s)',
        ]
        for pattern in search_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return None

    def extract_all(self, text: str) -> dict[str, ExtractedParam]:
        params = {}

        path = self.extract_path(text)
        if path:
            params["file_path"] = ExtractedParam(
                name="file_path", value=path, source="pattern", confidence=0.9
            )

        url = self.extract_url(text)
        if url:
            params["url"] = ExtractedParam(
                name="url", value=url, source="pattern", confidence=1.0
            )

        app_name = self.extract_app_name(text)
        if app_name:
            params["app_name"] = ExtractedParam(
                name="app_name", value=app_name, source="alias", confidence=0.9
            )

        coord = self.extract_coordinate(text)
        if coord:
            params["x"] = ExtractedParam(
                name="x", value=coord[0], source="pattern", confidence=1.0
            )
            params["y"] = ExtractedParam(
                name="y", value=coord[1], source="pattern", confidence=1.0
            )

        content = self.extract_content(text)
        if content:
            params["content"] = ExtractedParam(
                name="content", value=content, source="pattern", confidence=0.8
            )

        key = self.extract_key(text)
        if key:
            params["key"] = ExtractedParam(
                name="key", value=key, source="pattern", confidence=0.9
            )

        hotkey = self.extract_hotkey(text)
        if hotkey:
            params["keys"] = ExtractedParam(
                name="keys", value=hotkey, source="pattern", confidence=0.9
            )

        window_title = self.extract_window_title(text)
        if window_title:
            params["title"] = ExtractedParam(
                name="title", value=window_title, source="pattern", confidence=0.8
            )

        search_pattern = self.extract_search_pattern(text)
        if search_pattern:
            params["pattern"] = ExtractedParam(
                name="pattern", value=search_pattern, source="pattern", confidence=0.8
            )

        return params

    def resolve_reference(
        self,
        reference: str,
        context: dict[str, Any] | None = None
    ) -> str | None:
        if not context:
            return None

        reference_map = {
            "它": ["file_path", "url", "app_name"],
            "这个": ["file_path", "url", "app_name"],
            "那个": ["file_path", "url", "app_name"],
            "这个文件": ["file_path"],
            "那个文件": ["file_path"],
            "这个目录": ["directory"],
            "那个目录": ["directory"],
            "这个应用": ["app_name"],
            "那个应用": ["app_name"],
            "这个网址": ["url"],
            "那个网址": ["url"],
        }

        entity_types = reference_map.get(reference)
        if entity_types:
            for entity_type in entity_types:
                if entity_type in context:
                    entities = context[entity_type]
                    if isinstance(entities, list) and entities:
                        return entities[-1]
                    elif isinstance(entities, str):
                        return entities

        return None


param_extractor = ParamExtractor()
