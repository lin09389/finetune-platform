"""
符号提取�?- 从代码中提取类、函数、组件等符号

支持语言�?- Python: class, def, method
- JavaScript/TypeScript: function, class, const arrow, React component
"""
from pathlib import Path
from typing import List, Dict, Any, Optional
import re
import logging

from .models import SymbolInfo

logger = logging.getLogger(__name__)


class SymbolExtractor:
    """代码符号提取�?""

    def __init__(self):
        """初始化符号提取器"""
        # Python 模式
        self.python_patterns = {
            "class": re.compile(r'^class\s+(\w+)(?:\([^)]*\))?\s*:', re.MULTILINE),
            "function": re.compile(r'^def\s+(\w+)\s*\(([^)]*)\)\s*(?:->.*?)?\s*:', re.MULTILINE),
            "async_function": re.compile(r'^async\s+def\s+(\w+)\s*\(([^)]*)\)\s*(?:->.*?)?\s*:', re.MULTILINE),
        }

        # JavaScript/TypeScript 模式
        self.js_patterns = {
            "class": re.compile(r'(?:export\s+)?class\s+(\w+)(?:\s+extends\s+\w+)?\s*\{', re.MULTILINE),
            "function": re.compile(r'(?:export\s+)?function\s+(\w+)\s*\(([^)]*)\)', re.MULTILINE),
            "arrow": re.compile(r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>', re.MULTILINE),
            "react_component": re.compile(r'(?:export\s+)?(?:const|function)\s+(\w+)\s*(?:\([^)]*\))?\s*(?:=>)?\s*\{', re.MULTILINE),
            "interface": re.compile(r'(?:export\s+)?interface\s+(\w+)', re.MULTILINE),
            "type": re.compile(r'(?:export\s+)?type\s+(\w+)\s*=', re.MULTILINE),
        }

    def extract(self, file_path: str, content: Optional[str] = None) -> List[SymbolInfo]:
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
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
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

    def _extract_python(self, content: str, file_path: str) -> List[SymbolInfo]:
        """提取 Python 符号"""
        symbols = []
        lines = content.split("\n")

        # 提取�?        for match in self.python_patterns["class"].finditer(content):
            class_name = match.group(1)
            line_num = content[:match.start()].count("\n") + 1

            # 提取类文档字符串
            docstring = self._extract_python_docstring(content, match.end())

            symbols.append(SymbolInfo(
                type="class",
                name=class_name,
                line=line_num,
                file_path=file_path,
                docstring=docstring
            ))

        # 提取函数
        for match in self.python_patterns["function"].finditer(content):
            func_name = match.group(1)
            params_str = match.group(2)
            line_num = content[:match.start()].count("\n") + 1

            # 解析参数
            params = self._parse_python_params(params_str)

            # 提取文档字符�?            docstring = self._extract_python_docstring(content, match.end())

            # 跳过私有方法（可选）
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

        # 提取异步函数
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

    def _extract_python_docstring(self, content: str, end_pos: int) -> Optional[str]:
        """提取 Python 函数/类的文档字符�?""
        # 查找冒号后的内容
        colon_pos = content.find(":", end_pos - 50, end_pos + 10)
        if colon_pos == -1:
            return None

        # 跳过冒号后的空白
        pos = colon_pos + 1
        while pos < len(content) and content[pos] in " \t\n":
            pos += 1

        # 检查是否是文档字符�?        if content[pos:pos+3] in ['"""', "'''"]:
            quote = content[pos:pos+3]
            end_quote = content.find(quote, pos + 3)
            if end_quote != -1:
                docstring = content[pos+3:end_quote].strip()
                # 只返回第一�?                return docstring.split("\n")[0].strip() if docstring else None

        return None

    def _parse_python_params(self, params_str: str) -> List[str]:
        """解析 Python 函数参数"""
        if not params_str.strip():
            return []

        params = []
        # 简单分割（不处理复杂类型注解）
        for param in params_str.split(","):
            param = param.strip()
            if param and param != "self" and param != "cls":
                # 去掉默认值和类型注解
                param_name = param.split(":")[0].split("=")[0].strip()
                if param_name:
                    params.append(param_name)

        return params

    def _extract_javascript(self, content: str, file_path: str) -> List[SymbolInfo]:
        """提取 JavaScript/TypeScript 符号"""
        symbols = []

        # 提取�?        for match in self.js_patterns["class"].finditer(content):
            class_name = match.group(1)
            line_num = content[:match.start()].count("\n") + 1

            symbols.append(SymbolInfo(
                type="class",
                name=class_name,
                line=line_num,
                file_path=file_path
            ))

        # 提取函数
        for match in self.js_patterns["function"].finditer(content):
            func_name = match.group(1)
            params_str = match.group(2)
            line_num = content[:match.start()].count("\n") + 1

            params = self._parse_js_params(params_str)

            # 跳过私有函数
            if func_name.startswith("_"):
                continue

            symbols.append(SymbolInfo(
                type="function",
                name=func_name,
                line=line_num,
                file_path=file_path,
                parameters=params
            ))

        # 提取箭头函数（可能是 React 组件�?        for match in self.js_patterns["arrow"].finditer(content):
            func_name = match.group(1)
            params_str = match.group(2)
            line_num = content[:match.start()].count("\n") + 1

            # React 组件通常大写开�?            is_component = func_name[0].isupper()

            params = self._parse_js_params(params_str)

            symbols.append(SymbolInfo(
                type="component" if is_component else "function",
                name=func_name,
                line=line_num,
                file_path=file_path,
                parameters=params
            ))

        # 提取接口（TypeScript�?        for match in self.js_patterns["interface"].finditer(content):
            interface_name = match.group(1)
            line_num = content[:match.start()].count("\n") + 1

            symbols.append(SymbolInfo(
                type="interface",
                name=interface_name,
                line=line_num,
                file_path=file_path
            ))

        # 提取类型别名（TypeScript�?        for match in self.js_patterns["type"].finditer(content):
            type_name = match.group(1)
            line_num = content[:match.start()].count("\n") + 1

            symbols.append(SymbolInfo(
                type="type",
                name=type_name,
                line=line_num,
                file_path=file_path
            ))

        return symbols

    def _parse_js_params(self, params_str: str) -> List[str]:
        """解析 JavaScript 函数参数"""
        if not params_str.strip():
            return []

        params = []
        # 简单分割（不处理解构和默认值）
        for param in params_str.split(","):
            param = param.strip()
            if param:
                # 去掉类型注解和默认�?                param_name = param.split(":")[0].split("=")[0].strip()
                # 处理解构参数
                if param_name.startswith("{") or param_name.startswith("["):
                    param_name = "props" if param_name.startswith("{") else "args"
                if param_name and param_name not in ["props", "args"]:
                    params.append(param_name)
                elif param_name in ["props", "args"]:
                    params.append(param_name)

        return params

    def extract_from_multiple(self, files: List[Dict[str, str]]) -> Dict[str, List[SymbolInfo]]:
        """
        从多个文件中提取符号

        Args:
            files: 文件列表，每项包�?{"path": str, "content": str}

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


# 单例实例
_extractor_instance: Optional[SymbolExtractor] = None


def get_symbol_extractor() -> SymbolExtractor:
    """获取符号提取器实�?""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = SymbolExtractor()
    return _extractor_instance
