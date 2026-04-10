"""
Automatic fixer for Python files that may have encoding-related damage.
"""

from __future__ import annotations

import ast
import os
import re


def try_read_file(filepath: str) -> tuple[str | None, str | None]:
    """Try reading a file with multiple encodings."""
    encodings = ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]
    for encoding in encodings:
        try:
            with open(filepath, encoding=encoding, errors="replace") as f:
                return f.read(), encoding
        except Exception:
            continue
    return None, None


def fix_truncated_chinese(content: str) -> str:
    """
    Fix common punctuation damage where mojibake leaves dangling `?`.
    Conservative by design to avoid changing valid source text.
    """
    text = content
    replacements = {
        r"([\u4e00-\u9fff])\?": r"\1。",
        r"([\u4e00-\u9fff])\?\"": r"\1。\"",
        r"([\u4e00-\u9fff])\?'": r"\1。'",
        r"（\?": "（",
        r"：\?": "：",
        r"，\?": "，",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)
    return text


def _fix_unbalanced_quote(line: str, quote: str) -> str:
    if line.count(quote) % 2 == 0:
        return line
    if line.strip().endswith("\\"):
        return line

    line = line.rstrip()
    if line.endswith("?"):
        return line[:-1] + "。"
    if line.endswith(f"?{quote}"):
        return line[:-2] + f"。{quote}"
    return line + quote


def fix_unterminated_strings(content: str) -> str:
    """Fix obvious unterminated string line patterns."""
    fixed_lines: list[str] = []
    for line in content.split("\n"):
        line = _fix_unbalanced_quote(line, '"')
        line = _fix_unbalanced_quote(line, "'")
        fixed_lines.append(line)
    return "\n".join(fixed_lines)


def is_valid_python(content: str) -> bool:
    """Check if content parses as valid Python."""
    try:
        ast.parse(content)
        return True
    except Exception:
        return False


def fix_file(filepath: str) -> tuple[bool, str]:
    """Fix a single file and write back if parse succeeds."""
    content, _encoding = try_read_file(filepath)
    if content is None:
        return False, "unable to read file"

    if is_valid_python(content):
        return True, "already valid"

    fixed_content = fix_unterminated_strings(fix_truncated_chinese(content))
    if not is_valid_python(fixed_content):
        return False, "auto-fix failed"

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(fixed_content)
        return True, "fixed"
    except Exception as e:
        return False, f"save failed: {e}"


def scan_and_fix_directory(directory: str) -> list[tuple[str, bool, str]]:
    """Scan recursively and fix Python files with parse/encoding issues."""
    results: list[tuple[str, bool, str]] = []
    for root, _dirs, files in os.walk(directory):
        if "venv" in root or ".venv" in root or "__pycache__" in root:
            continue

        for filename in files:
            if not filename.endswith(".py"):
                continue

            filepath = os.path.join(root, filename)
            try:
                with open(filepath, encoding="utf-8") as fp:
                    ast.parse(fp.read())
                continue
            except (SyntaxError, UnicodeDecodeError):
                pass
            except Exception:
                continue

            success, message = fix_file(filepath)
            results.append((filepath, success, message))
    return results


if __name__ == "__main__":
    server_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"Scanning: {server_dir}")
    print("=" * 60)

    results = scan_and_fix_directory(server_dir)
    if not results:
        print("No files required fixing.")
    else:
        fixed = 0
        for filepath, success, message in results:
            status = "OK" if success else "FAIL"
            print(f"[{status}] {filepath}: {message}")
            if success:
                fixed += 1

        print("=" * 60)
        print(f"Completed: {fixed}/{len(results)} files fixed")
