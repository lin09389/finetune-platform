from __future__ import annotations

from .file_tools import FileToolsMixin
from .symbol_index_tools import AST_GREP_SYMBOL_RE, SymbolIndexToolsMixin


class SymbolToolsMixin(FileToolsMixin, SymbolIndexToolsMixin):
    """Backward-compatible shim — use FileToolsMixin and SymbolIndexToolsMixin directly."""


__all__ = ["AST_GREP_SYMBOL_RE", "SymbolToolsMixin"]
