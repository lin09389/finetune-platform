"""Platform-owned canonical built-in tools for the controlled tool platform."""

from .filesystem import (
    FILESYSTEM_DEFINITIONS,
    WRITE_DEFINITIONS,
    make_filesystem_handlers,
    make_write_handlers,
    resolve_workspace_path,
)
from .git import GIT_DEFINITIONS, make_git_handlers
from .registry import (
    PLATFORM_BUILTIN_ALIASES,
    PLATFORM_BUILTIN_DEFINITIONS,
    PLATFORM_BUILTIN_TOOL_NAMES,
    platform_builtin_registry,
    platform_builtin_registry_singleton,
    register_platform_builtins,
)

__all__ = [
    "FILESYSTEM_DEFINITIONS",
    "GIT_DEFINITIONS",
    "PLATFORM_BUILTIN_ALIASES",
    "PLATFORM_BUILTIN_DEFINITIONS",
    "PLATFORM_BUILTIN_TOOL_NAMES",
    "WRITE_DEFINITIONS",
    "make_filesystem_handlers",
    "make_git_handlers",
    "make_write_handlers",
    "platform_builtin_registry",
    "platform_builtin_registry_singleton",
    "register_platform_builtins",
    "resolve_workspace_path",
]
