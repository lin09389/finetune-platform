"""Registration of platform-owned canonical built-in tools."""

from __future__ import annotations

from ..registry import ToolRegistry
from .execute import EXECUTE_DEFINITIONS
from .filesystem import FILESYSTEM_DEFINITIONS, WRITE_DEFINITIONS
from .git import GIT_DEFINITIONS

PLATFORM_BUILTIN_DEFINITIONS: tuple = (
    *FILESYSTEM_DEFINITIONS,
    *WRITE_DEFINITIONS,
    *GIT_DEFINITIONS,
    *EXECUTE_DEFINITIONS,
)

PLATFORM_BUILTIN_TOOL_NAMES: frozenset[str] = frozenset(
    definition.meta.canonical_name for definition in PLATFORM_BUILTIN_DEFINITIONS
)

PLATFORM_BUILTIN_ALIASES: frozenset[str] = frozenset(
    alias for definition in PLATFORM_BUILTIN_DEFINITIONS for alias in definition.aliases
)


def register_platform_builtins(registry: ToolRegistry) -> None:
    """Register every platform built-in definition into ``registry``."""
    for definition in PLATFORM_BUILTIN_DEFINITIONS:
        registry.register(definition)


def platform_builtin_registry() -> ToolRegistry:
    """Return a module-level frozen registry of platform built-in tools.

    Definitions are stateless (``handler=None``); per-session handlers are
    injected through the Gateway ``handlers`` map at invocation time.
    """
    registry = ToolRegistry()
    register_platform_builtins(registry)
    registry.freeze()
    return registry


_PLATFORM_BUILTIN_REGISTRY = platform_builtin_registry()


def platform_builtin_registry_singleton() -> ToolRegistry:
    return _PLATFORM_BUILTIN_REGISTRY


__all__ = [
    "PLATFORM_BUILTIN_ALIASES",
    "PLATFORM_BUILTIN_DEFINITIONS",
    "PLATFORM_BUILTIN_TOOL_NAMES",
    "platform_builtin_registry",
    "platform_builtin_registry_singleton",
    "register_platform_builtins",
]
