"""Process environment probes for Agent/runtime operations (Phase 4).

These checks are advisory for development and fail-soft in production: they never
raise for missing optional packages, but they surface actionable warnings so
operators prefer ``uv run --extra all`` and a single absolute app.db path.
"""

from __future__ import annotations

import importlib.util
import sys
from typing import Any


def is_virtualenv() -> bool:
    """Best-effort detection of venv / virtualenv / uv-managed environments."""
    base = getattr(sys, "base_prefix", None)
    if base is not None and sys.prefix != base:
        return True
    # uv / virtualenv sometimes set VIRTUAL_ENV
    import os

    if os.environ.get("VIRTUAL_ENV") or os.environ.get("UV_PROJECT_ENVIRONMENT"):
        return True
    return False


def package_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def probe_agent_runtime_environment() -> dict[str, Any]:
    """Return non-secret Agent runtime environment facts."""
    packages = {
        "langchain": package_available("langchain"),
        "langchain_openai": package_available("langchain_openai"),
        "langchain_deepseek": package_available("langchain_deepseek"),
        "deepagents": package_available("deepagents"),
    }
    warnings: list[str] = []
    in_venv = is_virtualenv()
    if not in_venv:
        warnings.append(
            "当前 Python 看起来不在虚拟环境中。本地开发请优先使用: "
            "uv run --extra all python -m uvicorn server.main:app --host 127.0.0.1 --port 8010"
        )
    if not packages["deepagents"]:
        warnings.append("缺少 deepagents 包；Agent Session 无法运行。请执行: uv sync --extra all")
    if not packages["langchain_openai"]:
        warnings.append(
            "缺少 langchain_openai；云端 OpenAI 兼容回退与本地 Ollama service 路径会失败。"
            "请执行: uv sync --extra all"
        )
    if not packages["langchain_deepseek"]:
        warnings.append(
            "缺少 langchain_deepseek；DeepSeek 将尝试 OpenAI 兼容回退（需已配置 API Key）。"
            "完整安装: uv sync --extra all"
        )
    if not packages["langchain"]:
        warnings.append("缺少 langchain；Agent 模型初始化会失败。请执行: uv sync --extra all")

    app_db_path = None
    checkpoint_db_path = None
    try:
        from core.storage import APP_DB_PATH, get_langgraph_checkpoint_db_path

        app_db_path = APP_DB_PATH
        checkpoint_db_path = get_langgraph_checkpoint_db_path()
    except Exception:
        pass

    return {
        "in_virtualenv": in_venv,
        "python_executable": sys.executable,
        "python_prefix": sys.prefix,
        "packages": packages,
        "warnings": warnings,
        "recommended_command": (
            "uv run --extra all python -m uvicorn server.main:app --host 127.0.0.1 --port 8010"
        ),
        "app_db_path": app_db_path,
        "langgraph_checkpoint_db_path": checkpoint_db_path,
    }


def log_agent_runtime_environment(logger: Any) -> dict[str, Any]:
    """Log probe results and return the payload."""
    payload = probe_agent_runtime_environment()
    logger.info(
        "Agent runtime environment: venv=%s python=%s app_db=%s",
        payload.get("in_virtualenv"),
        payload.get("python_executable"),
        payload.get("app_db_path"),
    )
    for warning in payload.get("warnings") or []:
        logger.warning("AGENT_ENV: %s", warning)
    return payload


__all__ = [
    "is_virtualenv",
    "log_agent_runtime_environment",
    "package_available",
    "probe_agent_runtime_environment",
]
