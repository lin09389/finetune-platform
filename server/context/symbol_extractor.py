"""
符号提取器
- 从代码中提取类、函数、组件等符号

支持语言：
- Python: class, def, method
- JavaScript/TypeScript: function, class, const arrow, React component
"""
import logging
import re
from pathlib import Path

from .models import SymbolInfo

logger = logging.getLogger(__name__)


class SymbolExtractor:
    """代码符号提取器"""

    def __init__(self):
        """初始化符号提取器"""
        self.python_patterns = {
            "class": re.compile(r'^class\s+(\w+)(?:\([^)]*\))?\s*:', re.MULTILINE),
            "function": re.compile(r'^def\s+(\w+)\s*\(([^)]*)\)\s*(?:->.*?)?\s*:', re.MULTILINE),
            "async_function": re.compile(r'^async\s+def\s+(\w+)\s*\(([^)]*)\)\s*(?:->.*?)?\s*:', re.MULTILINE),
        }

        self.js_patterns = {
            "class": re.compile(r'(?:export\s+)?class\s+(\w+)(?:\s+extends\s+\w+)?\s*\{', re.MULTILINE),
            "function": re.compile(r'(?:export\s+)?function\s+(\w+)\s*\(([^)]*)\)', re.MULTILINE),
            "arrow": re.compile(r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>', re.MULTILINE),
            "react_component": re.compile(r'(?:export\s+)?(?:const|function)\s+(\w+)\s*(?:\([^)]*\))?\s*(?:=>)?\s*\{', re.MULTILINE),
            "interface": re.compile(r'(?:export\s+)?interface\s+(\w+)', re.MULTILINE),
            "type": re.compile(r'(?:export\s+)?type\s+(\w+)\s*=', re.MULTILINE),
        }

    def extract(self, file_path: str, content: str | None = None) -> list[SymbolInfo]:
        """
        从文件中提取符号

        Args:
            file_path: 文件路径
            content: 文件内容（可选，不提供则从文件读取）

        Returns:
            符号列表
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        if content is None:
            try:
                with open(path, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception as e:
                logger.warning(f"读取文件失败 {file_path}: {e}")
                return []

        if ext == ".py":
            return self._extract_python(content, file_path)
        elif ext in [".js", ".ts", ".jsx", ".tsx"]:
            return self._extract_javascript(content, file_path)
        else:
            return []

    def _extract_python(self, content: str, file_path: str) -> list[SymbolInfo]:
        """提取 Python 符号"""
        symbols = []
        for match in self.python_patterns["class"].finditer(content):
            class_name = match.group(1)
            line_num = content[:match.start()].count("\n") + 1

            docstring = self._extract_python_docstring(content, match.end())

            symbols.append(SymbolInfo(
                type="class",
                name=class_name,
                line=line_num,
                file_path=file_path,
                docstring=docstring
            ))

        for match in self.python_patterns["function"].finditer(content):
            func_name = match.group(1)
            params_str = match.group(2)
            line_num = content[:match.start()].count("\n") + 1

            params = self._parse_python_params(params_str)

            docstring = self._extract_python_docstring(content, match.end())

            if func_name.startswith("_") and not func_name.startswith("__"):
                continue

            symbols.append(SymbolInfo(
                type="function",
                name=func_name,
                line=line_num,
                file_path=file_path,
                parameters=params,
                docstring=docstring
            ))

        for match in self.python_patterns["async_function"].finditer(content):
            func_name = match.group(1)
            params_str = match.group(2)
            line_num = content[:match.start()].count("\n") + 1

            params = self._parse_python_params(params_str)
            docstring = self._extract_python_docstring(content, match.end())

            if func_name.startswith("_") and not func_name.startswith("__"):
                continue

            symbols.append(SymbolInfo(
                type="async_function",
                name=func_name,
                line=line_num,
                file_path=file_path,
                parameters=params,
                docstring=docstring
            ))

        return symbols

    def _extract_python_docstring(self, content: str, end_pos: int) -> str | None:
        """提取 Python 函数/类的文档字符串"""
        colon_pos = content.find(":", end_pos - 50, end_pos + 10)
        if colon_pos == -1:
            return None

        pos = colon_pos + 1
        while pos < len(content) and content[pos] in " \t\n":
            pos += 1

        if content[pos:pos+3] in ['"""', "'''"]:
            quote = content[pos:pos+3]
            end_quote = content.find(quote, pos + 3)
            if end_quote != -1:
                docstring = content[pos+3:end_quote].strip()
                return docstring.split("\n")[0].strip() if docstring else None

        return None

    def _parse_python_params(self, params_str: str) -> list[str]:
        """解析 Python 函数参数"""
        if not params_str.strip():
            return []

        params = []
        for param in params_str.split(","):
            param = param.strip()
            if param and param != "self" and param != "cls":
                param_name = param.split(":")[0].split("=")[0].strip()
                if param_name:
                    params.append(param_name)

        return params

    def _extract_javascript(self, content: str, file_path: str) -> list[SymbolInfo]:
        """提取 JavaScript/TypeScript 符号"""
        symbols = []

        for match in self.js_patterns["class"].finditer(content):
            class_name = match.group(1)
            line_num = content[:match.start()].count("\n") + 1

            symbols.append(SymbolInfo(
                type="class",
                name=class_name,
                line=line_num,
                file_path=file_path
            ))

        for match in self.js_patterns["function"].finditer(content):
            func_name = match.group(1)
            params_str = match.group(2)
            line_num = content[:match.start()].count("\n") + 1

            params = self._parse_js_params(params_str)

            if func_name.startswith("_"):
                continue

            symbols.append(SymbolInfo(
                type="function",
                name=func_name,
                line=line_num,
                file_path=file_path,
                parameters=params
            ))

        for match in self.js_patterns["arrow"].finditer(content):
            func_name = match.group(1)
            params_str = match.group(2)
            line_num = content[:match.start()].count("\n") + 1

            is_component = func_name[0].isupper()

            params = self._parse_js_params(params_str)

            symbols.append(SymbolInfo(
                type="component" if is_component else "function",
                name=func_name,
                line=line_num,
                file_path=file_path,
                parameters=params
            ))

        for match in self.js_patterns["interface"].finditer(content):
            interface_name = match.group(1)
            line_num = content[:match.start()].count("\n") + 1

            symbols.append(SymbolInfo(
                type="interface",
                name=interface_name,
                line=line_num,
                file_path=file_path
            ))

        for match in self.js_patterns["type"].finditer(content):
            type_name = match.group(1)
            line_num = content[:match.start()].count("\n") + 1

            symbols.append(SymbolInfo(
                type="type",
                name=type_name,
                line=line_num,
                file_path=file_path
            ))

        return symbols

    def _parse_js_params(self, params_str: str) -> list[str]:
        """解析 JavaScript 函数参数"""
        if not params_str.strip():
            return []

        params = []
        for param in params_str.split(","):
            param = param.strip()
            if param:
                param_name = param.split(":")[0].split("=")[0].strip()
                if param_name.startswith("{") or param_name.startswith("["):
                    param_name = "props" if param_name.startswith("{") else "args"
                if param_name and param_name not in ["props", "args"] or param_name in ["props", "args"]:
                    params.append(param_name)

        return params

    def extract_from_multiple(self, files: list[dict[str, str]]) -> dict[str, list[SymbolInfo]]:
        """
        从多个文件中提取符号

        Args:
            files: 文件列表，每项包含 {"path": str, "content": str}

        Returns:
            文件路径到符号列表的映射
        """
        result = {}

        for file_info in files:
            path = file_info["path"]
            content = file_info.get("content")
            symbols = self.extract(path, content)
            result[path] = symbols

        return result


_extractor_instance: SymbolExtractor | None = None


def get_symbol_extractor() -> SymbolExtractor:
    """获取符号提取器实例"""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = SymbolExtractor()
    return _extractor_instance
