#!/usr/bin/env python3
"""Guard critical source files against encoding regressions.

关键点（参考 docs/ux-audit-2026-07-14.md §4.1 与 §6.1 P0-5）：
- 白名单 TEXT_SUFFIXES 只覆盖真正的源码/文本扩展，排除
  ``.mdl / .msc / .safetensors / .bin / .pt`` 等 ModelScope / 权重二进制。
- SUSPICIOUS_TOKENS 显式覆盖过往事故（TrainingChart 的
  ``宸茶繛鎺``＝“已连接”）与常见 CJK mojibake 前缀。
- 追加 :func:`find_dense_mojibake` 启发式：单行内命中 CJK
  兼容字节区的字符密度超过阈值时视为可疑，用于捕获未列入
  SUSPICIOUS_TOKENS 但同样属于 UTF-8/CP936 双重解码残留。
"""

from __future__ import annotations

import codecs
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")


ROOT = Path(__file__).resolve().parent.parent

TARGETS = [
    ROOT / "client" / "src",
    ROOT / "server" / "api",
    ROOT / "server" / "agent",
    ROOT / "server" / "core",
    ROOT / "server" / "context",
    ROOT / "server" / "memory",
    ROOT / "server" / "security",
    ROOT / "server" / "gateway",
    ROOT / "server" / "heartbeat",
    ROOT / "server" / "workspace",
    ROOT / "server" / "cua",
    ROOT / "server" / "backends",
    ROOT / "server" / "tests",
    ROOT / "server" / "main.py",
    ROOT / "scripts",
    ROOT / "tests",
    ROOT / ".github" / "workflows",
    ROOT / "package.json",
    ROOT / "pyproject.toml",
    ROOT / "README.md",
    ROOT / "AGENTS.md",
]

TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".yml",
    ".yaml",
    ".md",
    ".toml",
    ".css",
    ".scss",
    ".html",
}

# 二进制/权重扩展显式排除清单（防止其被误加入 TEXT_SUFFIXES）。
BINARY_SUFFIXES = {
    ".mdl",
    ".msc",
    ".safetensors",
    ".bin",
    ".pt",
    ".pth",
    ".onnx",
    ".gguf",
    ".ckpt",
    ".traineddata",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
}

SKIP_DIR_NAMES = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".trae",
    "__pycache__",
    "backup_old_modules",
    "build",
    "data",
    "dist",
    "logs",
    "models",
    "node_modules",
    "outputs",
    "venv",
}

SUSPICIOUS_TOKENS = [
    "鏀寔",
    "妫€鏌",
    "鍒濆",
    "璇锋眰",
    "鍝嶅簲",
    "閿欒",
    "鏈嶅姟",
    "缂栫爜",
    "榛戝悕",
    "闄愬埗",
    "杩囨护",
    "寮€濮",
    "鏁版嵁",
    "瀛樺偍",
    "鍒犻櫎",
    "璁板繂",
    "浼氳瘽",
    "鍔熻兘",
    "鍙傛暟",
    "杩斿洖",
    "绫诲瀷",
    "鐘舵€",
    "璺緞",
    # 历史事故：TrainingChart.tsx 中的 “已连接” 被 GBK 二次解码为下列 mojibake。
    "宸茶繛鎺",
    "宸茶繛",
    "鎺?",
    # 高频遺留 mojibake：训练/推理页常见的“成功/失败/加载”翻译错乱。
    "鄴愧姛",
    "澵辣触",
    "锕犹浇",
    "宸插畑鄴",
    "进涜涓",
    "涓嘶弪锦",
]

# GBK/CP936→UTF-8 二次解码专属的窄区，选取原则：
# * U+9300-U+93FF：CJK 扩展 A 中的稀有汉字（鏀/鏌/鏈/鏁/鎺 等），
#   简体中文源码几乎不会出现，是 mojibake 的高保真指纹。
# * U+95A0-U+95E7：门部繁体字上半区（閠/閡/閫/閱/閲/閿/闄 等），
#   显式排除 U+95E8 起的常用简体字（门/闪/闭/间/闲/闷/闹/问 等）。
# * U+9400-U+9488：钅部繁体上半区（鍒/鍔/鍙/鎺-区衔接段），
#   同样排除 U+9489 起的常用简体字（钉/钎/钥/铁 等）。
# 触发条件：单行同时命中 _MOJIBAKE_DENSITY_THRESHOLD 个及以上稀有字符，
# 才判为疑似 mojibake，避免正常中文（"限审阅"/"密密钥"）误报。
_MOJIBAKE_HOT_CHARS = re.compile(r"[\u9300-\u93ff\u9400-\u9488\u95a0-\u95e7]")
_MOJIBAKE_DENSITY_THRESHOLD = 2


def iter_target_files() -> list[Path]:
    files: list[Path] = []

    for target in TARGETS:
        if not target.exists():
            continue

        if target.is_file():
            files.append(target)
            continue

        for path in sorted(target.rglob("*")):
            if not path.is_file():
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            suffix = path.suffix.lower()
            # 显式跳过已知二进制/权重扩展，避免 ModelScope 元数据
            # (.mdl/.msc)、权重 (.safetensors/.bin/.pt) 被误报为“无法检测编码”。
            if suffix in BINARY_SUFFIXES:
                continue
            if suffix in TEXT_SUFFIXES:
                files.append(path)

    return files


def find_content_issue(text: str, *, check_tokens: bool = True) -> tuple[int, str] | None:
    for line_no, line in enumerate(text.splitlines(), start=1):
        if "\ufffd" in line:
            return line_no, "replacement character found"

        if any("\ue000" <= ch <= "\uf8ff" for ch in line):
            return line_no, "private-use character found"

        if check_tokens:
            for token in SUSPICIOUS_TOKENS:
                if token in line:
                    return line_no, f"suspicious mojibake token '{token}' found"

            hot_hits = _MOJIBAKE_HOT_CHARS.findall(line)
            if len(hot_hits) >= _MOJIBAKE_DENSITY_THRESHOLD:
                sample = "".join(hot_hits[:6])
                return (
                    line_no,
                    f"dense mojibake-like characters ({len(hot_hits)} hits, sample: {sample!r})",
                )

    return None


def check_file(path: Path) -> list[str]:
    issues: list[str] = []
    raw = path.read_bytes()

    if raw.startswith(codecs.BOM_UTF8):
        issues.append("UTF-8 BOM found")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        issues.append(f"invalid UTF-8 bytes at offset {exc.start}")
        return issues

    if path.resolve() != Path(__file__).resolve():
        content_issue = find_content_issue(text, check_tokens=True)
        if content_issue:
            line_no, detail = content_issue
            issues.append(f"line {line_no}: {detail}")

    return issues


def main() -> int:
    files = iter_target_files()
    failures: list[tuple[Path, list[str]]] = []

    for path in files:
        issues = check_file(path)
        if issues:
            failures.append((path, issues))

    if failures:
        print("Encoding check failed.")
        print()
        for path, issues in failures:
            rel = path.relative_to(ROOT)
            print(rel)
            for issue in issues:
                print(f"  - {issue}")
        print()
        print(f"Scanned {len(files)} files, found {len(failures)} problematic files.")
        return 1

    print(f"Encoding check passed for {len(files)} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
