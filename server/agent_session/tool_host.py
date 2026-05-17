from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class ToolHostProtocol(Protocol):
    """Structural interface that AgentToolRegistry satisfies.

    Mixins inherit from this class so that type checkers can resolve
    all cross-mixin method/attribute references without ``# type: ignore``.
    The concrete implementations live in ``AgentToolRegistry`` which is the
    only class that ever instantiates the full MRO.
    """

    repository: Any | None

    def _root(self, context: dict[str, Any]) -> Path: ...

    def _safe_path(self, root: Path, raw_path: str) -> Path: ...

    def _normalize_tool_payload(self, payload: dict[str, Any]) -> dict[str, Any]: ...
