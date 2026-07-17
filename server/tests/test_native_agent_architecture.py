from __future__ import annotations

import ast
from pathlib import Path

NATIVE_AGENT_ROOT = Path(__file__).resolve().parents[1] / "native_agent"
FORBIDDEN_NATIVE_IMPORT_PREFIXES = (
    "deepagents",
    "langgraph",
    "fastapi",
    "starlette",
    "api",
    "agent_session",
    "training",
    "training_engine",
    "training_worker",
    "client",
    "react",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def _python_files(relative_path: str = ".") -> list[Path]:
    return sorted((NATIVE_AGENT_ROOT / relative_path).rglob("*.py")) if (NATIVE_AGENT_ROOT / relative_path).exists() else []


def test_native_domain_package_has_no_framework_legacy_or_training_imports() -> None:
    offenders: dict[str, set[str]] = {}
    for path in _python_files():
        prohibited = {
            module
            for module in _imports(path)
            for prefix in FORBIDDEN_NATIVE_IMPORT_PREFIXES
            if module == prefix or module.startswith(f"{prefix}.")
        }
        if prohibited:
            offenders[str(path.relative_to(NATIVE_AGENT_ROOT))] = prohibited

    assert offenders == {}


def test_model_adapters_do_not_import_native_tool_implementations() -> None:
    prohibited = {
        module
        for path in _python_files()
        if path.name in {"model_adapters.py", "sampling_loop.py"}
        for module in _imports(path)
        if module == "native_agent.tools" or module.startswith("native_agent.tools.")
    }

    assert prohibited == set()


def test_tool_implementations_do_not_append_authoritative_session_events() -> None:
    prohibited_markers = ("append_event(", "append_session_event(", "append_authoritative_event(")
    offenders = {
        str(path.relative_to(NATIVE_AGENT_ROOT))
        for path in _python_files("tools")
        if any(marker in path.read_text(encoding="utf-8") for marker in prohibited_markers)
    }

    assert offenders == set()


def test_gateway_does_not_construct_sampling_loop_directly() -> None:
    offenders = {
        str(path.relative_to(NATIVE_AGENT_ROOT))
        for path in _python_files()
        if path.name in {"websocket.py", "gateway.py"}
        and ("SamplingLoop(" in path.read_text(encoding="utf-8") or "NativeSamplingLoop(" in path.read_text(encoding="utf-8"))
    }

    assert offenders == set()


def test_trace_subscribers_do_not_import_primary_session_repositories() -> None:
    prohibited = {
        module
        for path in _python_files()
        if path.name == "trace.py"
        for module in _imports(path)
        if "repository" in module or module.startswith("native_agent.persistence")
    }

    assert prohibited == set()
