from __future__ import annotations

from .browser_tools import BrowserToolsMixin
from .http_tools import HttpToolsMixin, LOCAL_HTTP_HOSTS
from .page_parser import LocalPageParser


class WebToolsMixin(HttpToolsMixin, BrowserToolsMixin):
    """Backward-compatible shim — use HttpToolsMixin and BrowserToolsMixin directly."""


__all__ = ["LOCAL_HTTP_HOSTS", "LocalPageParser", "WebToolsMixin"]
